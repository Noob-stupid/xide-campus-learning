# -*- coding: utf-8 -*-
"""轻量工作流引擎：节点顺序执行 + 运行轨迹落库。

与 AgentArts 概念对齐：flow / node / run / step / context。
先跑通串行节点；分支由节点函数返回 next 或 status 控制。
"""
import traceback

import db

FLOWS = {
    'plan': {
        'title': '学习计划流',
        'nodes': [
            {'id': 'goal', 'name': '目标理解', 'type': 'agent'},
            {'id': 'decompose', 'name': '拆解学习任务', 'type': 'agent'},
            {'id': 'schedule', 'name': '排期与预约', 'type': 'tool'},
            {'id': 'remind', 'name': '提醒设置', 'type': 'notify'},
        ],
        'edges': [['goal', 'decompose'], ['decompose', 'schedule'], ['schedule', 'remind']],
    },
    'booking': {
        'title': '预约履约流',
        'nodes': [
            {'id': 'intent', 'name': '意图与约束', 'type': 'agent'},
            {'id': 'match', 'name': '座位匹配', 'type': 'agent'},
            {'id': 'lock', 'name': 'Redis 锁座', 'type': 'tool'},
            {'id': 'persist', 'name': 'RDS 落库', 'type': 'tool'},
            {'id': 'nav', 'name': '生成导航', 'type': 'tool'},
            {'id': 'notify', 'name': '预约通知', 'type': 'notify'},
        ],
        'edges': [['intent', 'match'], ['match', 'lock'], ['lock', 'persist'], ['persist', 'nav'], ['nav', 'notify']],
    },
    'study': {
        'title': '学习辅导流',
        'nodes': [
            {'id': 'checkin', 'name': '签到开场', 'type': 'tool'},
            {'id': 'plan', 'name': '学习计划', 'type': 'agent'},
            {'id': 'focus', 'name': '专注计时', 'type': 'tool'},
            {'id': 'stuck', 'name': '卡住了（苏格拉底）', 'type': 'agent'},
            {'id': 'resource', 'name': '推荐学习视频', 'type': 'agent'},
            {'id': 'end', 'name': '结束学习', 'type': 'trigger'},
        ],
        'edges': [['checkin', 'plan'], ['plan', 'focus'], ['focus', 'stuck'], ['stuck', 'resource'], ['resource', 'end']],
    },
    'relay': {
        'title': '接棒推送流',
        'nodes': [
            {'id': 'trigger', 'name': '结束/到期事件', 'type': 'trigger'},
            {'id': 'context', 'name': '聚合场次上下文', 'type': 'tool'},
            {'id': 'recall', 'name': '候选内容检索', 'type': 'tool'},
            {'id': 'rank', 'name': '匹配与排序', 'type': 'agent'},
            {'id': 'decide', 'name': '推送决策', 'type': 'condition'},
            {'id': 'push', 'name': '推送接力卡', 'type': 'notify'},
        ],
        'edges': [['trigger', 'context'], ['context', 'recall'], ['recall', 'rank'], ['rank', 'decide'], ['decide', 'push']],
    },
    'content': {
        'title': '交棒审核流',
        'nodes': [
            {'id': 'upload', 'name': '上传接收', 'type': 'trigger'},
            {'id': 'frames', 'name': '关键帧抽取', 'type': 'tool'},
            {'id': 'prescreen', 'name': 'AI 初筛', 'type': 'agent'},
            {'id': 'human', 'name': '人工帧级复核', 'type': 'human_review'},
            {'id': 'publish', 'name': '入接力池', 'type': 'tool'},
        ],
        'edges': [['upload', 'frames'], ['frames', 'prescreen'], ['prescreen', 'human'], ['human', 'publish']],
    },
}


def start(flow_key, context=None, user_id=None, title='', trigger=''):
    flow = FLOWS.get(flow_key)
    if not flow:
        raise ValueError('unknown flow: %s' % flow_key)
    ctx = dict(context or {})
    ctx.setdefault('_user_id', user_id)
    return db.execute(
        'INSERT INTO workflow_runs(flow_key,title,trigger,status,context,started_at) VALUES(?,?,?,?,?,?)',
        (flow_key, title or flow['title'], trigger, 'running', db.dumps(ctx), db.now()),
    )


def _load(run_id):
    row = db.one('SELECT * FROM workflow_runs WHERE id=?', (run_id,))
    return dict(row) if row else None


def step(run_id, node_id, node_name, fn, detail=None):
    """执行一个节点；fn(context) 返回 dict 合并进上下文。失败则标记并抛出。"""
    run = _load(run_id)
    if not run:
        raise ValueError('run not found: %s' % run_id)
    ctx = db.loads(run.get('context'), {}) or {}
    step_id = db.execute(
        'INSERT INTO workflow_steps(run_id,node_id,node_name,status,detail,started_at) VALUES(?,?,?,?,?,?)',
        (run_id, node_id, node_name, 'running', db.dumps(detail or {}), db.now()),
    )
    try:
        out = fn(ctx) if fn else {}
        if out is None:
            out = {}
        if not isinstance(out, dict):
            out = {'result': out}
        ctx.update(out)
        db.execute('UPDATE workflow_steps SET status=?,detail=?,finished_at=? WHERE id=?',
                   ('succeeded', db.dumps({'input': detail or {}, 'output': out}), db.now(), step_id))
        db.execute('UPDATE workflow_runs SET context=? WHERE id=?', (db.dumps(ctx), run_id))
        return out
    except Exception as e:
        db.execute('UPDATE workflow_steps SET status=?,detail=?,finished_at=? WHERE id=?',
                   ('failed', db.dumps({'input': detail or {}, 'error': str(e),
                                        'trace': traceback.format_exc()[-800:]}), db.now(), step_id))
        db.execute('UPDATE workflow_runs SET status=?,finished_at=? WHERE id=?', ('failed', db.now(), run_id))
        raise


def finish(run_id, status='succeeded', context=None):
    run = _load(run_id)
    if not run:
        return
    ctx = db.loads(run.get('context'), {}) or {}
    if context:
        ctx.update(context)
    db.execute('UPDATE workflow_runs SET status=?,context=?,finished_at=? WHERE id=?',
               (status, db.dumps(ctx), db.now(), run_id))


def get_run(run_id):
    run = _load(run_id)
    if not run:
        return None
    run['context'] = db.loads(run.get('context'), {}) or {}
    steps = db.query('SELECT * FROM workflow_steps WHERE run_id=? ORDER BY id', (run_id,))
    run['steps'] = []
    for s in steps:
        d = dict(s)
        d['detail'] = db.loads(d.get('detail'), {}) or {}
        run['steps'].append(d)
    return run


def list_runs(limit=30, flow_key=None):
    if flow_key:
        rows = db.query('SELECT * FROM workflow_runs WHERE flow_key=? ORDER BY id DESC LIMIT ?', (flow_key, limit))
    else:
        rows = db.query('SELECT * FROM workflow_runs ORDER BY id DESC LIMIT ?', (limit,))
    out = []
    for r in rows:
        d = dict(r)
        d['context'] = db.loads(d.get('context'), {}) or {}
        d['step_count'] = db.one('SELECT COUNT(*) c FROM workflow_steps WHERE run_id=?', (d['id'],))['c']
        out.append(d)
    return out


def flow_defs():
    return [{'key': k, **v} for k, v in FLOWS.items()]
