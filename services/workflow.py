# -*- coding: utf-8 -*-
"""工作流编排（对端 A）。

契约见 docs/CONTRACT.md 第 4 节。对外接口：

    NODE_TYPES                      节点类型白名单
    start(flow_key, context, ...)   建 run，返回 run_id
    step(run_id, node_id, node_name, fn, detail=None)
                                    执行一个节点，写 workflow_steps
    finish(run_id, status='succeeded', context=None)
    get_run(run_id)                 单条 run（含 steps）；**run 不存在返回 None**
    list_runs(limit=20)             最近若干条 run（含 steps）
    flow_defs()                     五条流的静态定义（画图用）

额外（契约之外的加法，不影响上面任何语义）：
    run_flow(flow_key, context, plan, ...)
                                    把 start + 连续 step + finish 合成一次调用
    flow_keys() / flow_def(flow_key)

约定：
- 时间一律 db.now() 生成的本地时间字符串。
- ``context`` 里带 ``trigger`` 时同时写进 workflow_runs.trigger 列，便于列表页过滤。
- ``start`` 的 ``user_id`` 写进 context['user_id']（表里没有 user_id 列）。
- step 的粒度是「一个节点一次执行」，失败即整条 run 失败（fail-fast），不自动回滚已完成的
  步骤数据 —— 已写入的业务数据保留，只把 run/step 标 failed 并把异常原样抛给调用方。
"""
import copy

import db

NODE_TYPES = {'trigger', 'agent', 'tool', 'condition', 'human_review', 'notify'}

# ---------------------------------------------------------------- 五条流的静态定义

_FLOWS = [
    {
        'key': 'plan',
        'name': '学习计划编排',
        'desc': '学生说出目标 → 解析 → 找空位 → 生成计划 → 推送',
        'entry': 'plan_trigger',
        'nodes': [
            {'id': 'plan_trigger', 'name': '提出学习目标', 'type': 'trigger',
             'desc': '学生输入科目、时长、时段与座位偏好'},
            {'id': 'plan_parse', 'name': '目标解析', 'type': 'agent',
             'desc': '抽出科目、时长、时段、偏好，落到 context'},
            {'id': 'plan_seats', 'name': '查询空闲座位', 'type': 'tool',
             'desc': '按偏好（靠窗/电源/安静）过滤 free 座位'},
            {'id': 'plan_check', 'name': '有匹配座位？', 'type': 'condition',
             'desc': '有匹配座位才继续，否则走候补建议'},
            {'id': 'plan_build', 'name': '生成学习计划', 'type': 'agent',
             'desc': '给出一段「时段 + 座位 + 目标 + 时长」的可执行计划'},
            {'id': 'plan_wait', 'name': '候补建议', 'type': 'agent',
             'desc': '无空位时给换时段 / 等待名单 / 换楼层建议'},
            {'id': 'plan_notify', 'name': '推送计划', 'type': 'notify',
             'desc': '写 messages 一条计划卡给学生'},
        ],
        'edges': [
            {'from': 'plan_trigger', 'to': 'plan_parse'},
            {'from': 'plan_parse', 'to': 'plan_seats'},
            {'from': 'plan_seats', 'to': 'plan_check'},
            {'from': 'plan_check', 'to': 'plan_build', 'label': '有'},
            {'from': 'plan_check', 'to': 'plan_wait', 'label': '无'},
            {'from': 'plan_build', 'to': 'plan_notify'},
            {'from': 'plan_wait', 'to': 'plan_notify'},
        ],
    },
    {
        'key': 'booking',
        'name': '落座前：预约与导航',
        'desc': '预约请求 → 规则校验 → 写预约 → 生成导航 → 提醒签到',
        'entry': 'booking_trigger',
        'nodes': [
            {'id': 'booking_trigger', 'name': '预约请求', 'type': 'trigger',
             'desc': '学生选座并发起预约（seat_id/subject/goal/时段）'},
            {'id': 'booking_rules', 'name': '规则校验', 'type': 'tool',
             'desc': '校验时长上下限、进行中预约数、时段冲突、座位状态'},
            {'id': 'booking_check', 'name': '规则通过？', 'type': 'condition',
             'desc': '通过才写库，否则回拒绝原因'},
            {'id': 'booking_create', 'name': '创建预约', 'type': 'tool',
             'desc': '写 reservations，status=booked'},
            {'id': 'booking_nav', 'name': '生成导航路径', 'type': 'tool',
             'desc': 'nav_nodes/nav_edges 最短路，从入口到座位'},
            {'id': 'booking_remind', 'name': '提醒签到', 'type': 'notify',
             'desc': '推送「预约成功 + 导航 + 15 分钟内签到」提醒'},
            {'id': 'booking_reject', 'name': '拒绝并说明原因', 'type': 'notify',
             'desc': '规则不通过时告诉学生卡在哪一条，并给替选'},
        ],
        'edges': [
            {'from': 'booking_trigger', 'to': 'booking_rules'},
            {'from': 'booking_rules', 'to': 'booking_check'},
            {'from': 'booking_check', 'to': 'booking_create', 'label': '通过'},
            {'from': 'booking_check', 'to': 'booking_reject', 'label': '不通过'},
            {'from': 'booking_create', 'to': 'booking_nav'},
            {'from': 'booking_nav', 'to': 'booking_remind'},
        ],
    },
    {
        'key': 'study',
        'name': '落座中：签到与辅导',
        'desc': '签到 → 开学习场次 → 苏格拉底辅导 → 记卡点 → 到期提醒',
        'entry': 'study_trigger',
        'nodes': [
            {'id': 'study_trigger', 'name': '签到落座', 'type': 'trigger',
             'desc': '学生在座位上签到，预约转 checked_in'},
            {'id': 'study_session', 'name': '开学习场次', 'type': 'tool',
             'desc': '写 study_sessions，status=active'},
            {'id': 'study_tutor', 'name': '苏格拉底辅导', 'type': 'agent',
             'desc': '按科目给 2–3 轮提问式辅导（services/tutor）'},
            {'id': 'study_stuck_check', 'name': '是否卡住？', 'type': 'condition',
             'desc': '识别「不会 / 卡住」信号，决定是否记卡点'},
            {'id': 'study_record', 'name': '记录卡点', 'type': 'tool',
             'desc': '写 study_sessions.stuck_points，供离座后接棒推送使用'},
            {'id': 'study_timer', 'name': '计时与到期检查', 'type': 'tool',
             'desc': '算已学时长与剩余时长，判断是否到 end_at'},
            {'id': 'study_notify', 'name': '到期提醒', 'type': 'notify',
             'desc': '推送到期提醒，引导「结束学习 → 接收棒」'},
        ],
        'edges': [
            {'from': 'study_trigger', 'to': 'study_session'},
            {'from': 'study_session', 'to': 'study_tutor'},
            {'from': 'study_tutor', 'to': 'study_stuck_check'},
            {'from': 'study_stuck_check', 'to': 'study_record', 'label': '卡住'},
            {'from': 'study_stuck_check', 'to': 'study_timer', 'label': '顺利'},
            {'from': 'study_record', 'to': 'study_timer'},
            {'from': 'study_timer', 'to': 'study_notify'},
        ],
    },
    {
        'key': 'relay',
        'name': '离座后：接棒推送',
        'desc': '学习结束/到期 → 从已过审内容池匹配 → 推送 → 反馈回流',
        'entry': 'relay_trigger',
        'nodes': [
            {'id': 'relay_trigger', 'name': '学习结束或到期', 'type': 'trigger',
             'desc': '主动结束、签到到期、预约超时三种入口'},
            {'id': 'relay_match', 'name': '匹配已过审内容', 'type': 'agent',
             'desc': '按 subject/knowledge_point/卡点/时长打分（services/content）'},
            {'id': 'relay_check', 'name': '池内有可用内容？', 'type': 'condition',
             'desc': '有则推送，无则告知并记录空池'},
            {'id': 'relay_push', 'name': '写接棒推送', 'type': 'tool',
             'desc': '写 relay_pushes + messages'},
            {'id': 'relay_notify', 'name': '推送接棒内容', 'type': 'notify',
             'desc': '只推给本人，带「为什么推给你」的理由'},
            {'id': 'relay_empty', 'name': '告知内容池暂无', 'type': 'notify',
             'desc': '空池时不硬凑推荐，改约老师交棒'},
            {'id': 'relay_feedback', 'name': '打开与反馈', 'type': 'trigger',
             'desc': '记录 opened_at 与「有用 / 没用」'},
            {'id': 'relay_learn', 'name': '反馈回流', 'type': 'agent',
             'desc': '反馈写回评分权重，下一轮推送更准'},
        ],
        'edges': [
            {'from': 'relay_trigger', 'to': 'relay_match'},
            {'from': 'relay_match', 'to': 'relay_check'},
            {'from': 'relay_check', 'to': 'relay_push', 'label': '有'},
            {'from': 'relay_check', 'to': 'relay_empty', 'label': '无'},
            {'from': 'relay_push', 'to': 'relay_notify'},
            {'from': 'relay_notify', 'to': 'relay_feedback'},
            {'from': 'relay_feedback', 'to': 'relay_learn'},
            {'from': 'relay_learn', 'to': 'relay_match', 'label': '权重更新'},
        ],
    },
    {
        'key': 'content',
        'name': '交棒上传：抽帧审核入池',
        'desc': '上传 → 抽帧 → AI 初筛 → 人工帧级复核 → 入池',
        'entry': 'content_trigger',
        'nodes': [
            {'id': 'content_trigger', 'name': '学生/教师上传', 'type': 'trigger',
             'desc': '交棒视频 + 标题/科目/知识点/来源类型'},
            {'id': 'content_extract', 'name': '抽帧', 'type': 'tool',
             'desc': 'cv2 按 FRAME_INTERVAL_SEC 抽帧写 content_frames（services/content）'},
            {'id': 'content_screen', 'name': 'AI 初筛', 'type': 'agent',
             'desc': '给 ai_risk / ai_summary / 可疑帧标 reasons'},
            {'id': 'content_check', 'name': '有可疑帧？', 'type': 'condition',
             'desc': '有可疑帧走人工帧级复核，否则直接待复核'},
            {'id': 'content_review', 'name': '帧级人工复核', 'type': 'human_review',
             'desc': 'reviewer 逐帧 cleared/flagged，写 reviews'},
            {'id': 'content_publish', 'name': '入池', 'type': 'tool',
             'desc': 'approve → status=approved + published_at；reject → rejected'},
            {'id': 'content_result', 'name': '通知上传者', 'type': 'notify',
             'desc': '告知入池结果与拒绝原因'},
        ],
        'edges': [
            {'from': 'content_trigger', 'to': 'content_extract'},
            {'from': 'content_extract', 'to': 'content_screen'},
            {'from': 'content_screen', 'to': 'content_check'},
            {'from': 'content_check', 'to': 'content_review', 'label': '有可疑帧'},
            {'from': 'content_check', 'to': 'content_publish', 'label': '无'},
            {'from': 'content_review', 'to': 'content_publish'},
            {'from': 'content_publish', 'to': 'content_result'},
        ],
    },
]

_FLOW_BY_KEY = {f['key']: f for f in _FLOWS}


# ---------------------------------------------------------------- 小工具

def _json_safe(obj):
    """把任意返回值转成可 dumps 的样子（sqlite3.Row / datetime 等）。"""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v) for v in obj]
    try:  # sqlite3.Row 之类
        return _json_safe(dict(obj))
    except Exception:
        return str(obj)


def _dumps(obj):
    return db.dumps(_json_safe(obj))


def _load_run_row(run_id):
    return db.one('SELECT * FROM workflow_runs WHERE id=?', (run_id,))


def _parsed_step(row):
    d = dict(row)
    d['detail'] = db.loads(d.get('detail'), {}) or {}
    return d


def _flow_name(flow_key):
    f = _FLOW_BY_KEY.get(flow_key)
    return f['name'] if f else '自定义流程'


# ---------------------------------------------------------------- 对外接口

def flow_defs():
    """五条流的静态定义（深拷贝，调用方随便改不影响内部）。"""
    return copy.deepcopy(_FLOWS)


def flow_keys():
    return [f['key'] for f in _FLOWS]


def flow_def(flow_key):
    f = _FLOW_BY_KEY.get(flow_key)
    return copy.deepcopy(f) if f else None


def start(flow_key, context, user_id=None, title=''):
    """创建一条 run（status='running'），返回 run_id。"""
    flow_key = str(flow_key or '').strip() or 'plan'
    ctx = dict(context or {})
    if user_id is not None:
        ctx.setdefault('user_id', user_id)
    trigger = str(ctx.get('trigger', '') or '')
    run_id = db.execute(
        'INSERT INTO workflow_runs(flow_key,title,trigger,status,context,started_at)'
        ' VALUES(?,?,?,?,?,?)',
        (flow_key, title or _flow_name(flow_key), trigger, 'running',
         _dumps(ctx), db.now()))
    return int(run_id)


def step(run_id, node_id, node_name, fn, detail=None):
    """执行一个节点。

    写 workflow_steps(running) → 调 fn(context 副本) → 写 succeeded/failed。
    fn 返回 dict 合并进 run.context；抛异常则本步骤 failed、run 标 failed、
    异常向上抛出（已完成的步骤与其写入的业务数据不回滚）。
    """
    row = _load_run_row(run_id)
    if row is None:
        raise LookupError('workflow run 不存在: %s' % (run_id,))
    if row['status'] != 'running':
        raise ValueError('run %s 当前状态为 %s，不能再执行步骤' % (run_id, row['status']))

    detail_json = _dumps(detail or {})
    step_id = db.execute(
        'INSERT INTO workflow_steps(run_id,node_id,node_name,status,detail,started_at)'
        ' VALUES(?,?,?,?,?,?)',
        (run_id, str(node_id), str(node_name), 'running', detail_json, db.now()))
    ctx = db.loads(row['context'], {}) or {}

    try:
        result = fn(dict(ctx))
    except Exception as exc:
        failed_detail = dict(detail or {})
        failed_detail['error'] = '%s: %s' % (type(exc).__name__, exc)
        db.execute(
            'UPDATE workflow_steps SET status=?, detail=?, finished_at=? WHERE id=?',
            ('failed', _dumps(failed_detail), db.now(), step_id))
        db.execute('UPDATE workflow_runs SET status=?, finished_at=? WHERE id=?',
                   ('failed', db.now(), run_id))
        raise

    merged = dict(ctx)
    if isinstance(result, dict):
        merged.update(result)
    done_detail = dict(detail or {})
    done_detail['result'] = result
    db.execute('UPDATE workflow_steps SET status=?, detail=?, finished_at=? WHERE id=?',
               ('succeeded', _dumps(done_detail), db.now(), step_id))
    db.execute('UPDATE workflow_runs SET context=? WHERE id=?', (_dumps(merged), run_id))
    return {
        'run_id': int(run_id),
        'step_id': int(step_id),
        'node_id': str(node_id),
        'node_name': str(node_name),
        'status': 'succeeded',
        'detail': _json_safe(done_detail),
        'result': _json_safe(result),
        'context': _json_safe(merged),
    }


def finish(run_id, status='succeeded', context=None):
    """收尾一条 run。已失败的 run 不会被 'succeeded' 覆盖（避免掩盖失败）。"""
    row = _load_run_row(run_id)
    if row is None:
        raise LookupError('workflow run 不存在: %s' % (run_id,))
    status = str(status or 'succeeded')
    if row['status'] == 'failed' and status == 'succeeded':
        status = 'failed'
    ctx = db.loads(row['context'], {}) or {}
    if context:
        ctx.update(context)
    db.execute('UPDATE workflow_runs SET status=?, context=?, finished_at=? WHERE id=?',
               (status, _dumps(ctx), db.now(), run_id))


def get_run(run_id):
    """单条 run；不存在返回 None（路由层据此 404）。"""
    row = _load_run_row(run_id)
    if row is None:
        return None
    data = dict(row)
    data['context'] = db.loads(data.get('context'), {}) or {}
    steps = db.query('SELECT * FROM workflow_steps WHERE run_id=? ORDER BY id', (run_id,))
    data['steps'] = [_parsed_step(s) for s in steps]
    data['step_count'] = len(data['steps'])
    data['ok_steps'] = len([s for s in data['steps'] if s['status'] == 'succeeded'])
    return data


def list_runs(limit=20):
    """最近 limit 条 run（新→旧），带 steps 与进度统计。"""
    try:
        limit = max(1, int(limit))
    except (TypeError, ValueError):
        limit = 20
    rows = db.query('SELECT * FROM workflow_runs ORDER BY id DESC LIMIT ?', (limit,))
    out = []
    for row in rows:
        data = dict(row)
        data['context'] = db.loads(data.get('context'), {}) or {}
        steps = db.query('SELECT * FROM workflow_steps WHERE run_id=? ORDER BY id', (data['id'],))
        data['steps'] = [_parsed_step(s) for s in steps]
        data['step_count'] = len(data['steps'])
        data['ok_steps'] = len([s for s in data['steps'] if s['status'] == 'succeeded'])
        out.append(data)
    return out


def run_flow(flow_key, context, plan, user_id=None, title=''):
    """加法：一次跑完一条流。

    plan 是 [(node_id, node_name, fn), ...] 顺序表；任一步失败 → run 标 failed
    并把异常抛出（此时返回不了 run_id，调用方可用 list_runs() 找到那条失败记录）。
    全部成功 → finish('succeeded') 并返回 run_id。
    """
    run_id = start(flow_key, context, user_id=user_id, title=title)
    for item in plan:
        node_id, node_name = item[0], item[1]
        fn = item[2]
        detail = item[3] if len(item) > 3 else None
        step(run_id, node_id, node_name, fn, detail)
    finish(run_id, 'succeeded')
    return run_id


if __name__ == '__main__':
    # 从项目根跑：python -m services.workflow（本模块与其它 services 一样用扁平 import）
    db.init_db()
    for f in flow_defs():
        print('%-9s %s  %d 节点 / %d 边' % (f['key'], f['name'], len(f['nodes']), len(f['edges'])))
