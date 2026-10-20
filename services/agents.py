# -*- coding: utf-8 -*-
"""对话智能体（对端 A）：规则意图路由 + 只读查库 + 可执行建议。

契约见 docs/CONTRACT.md 第 5 节：

    ask(text, user_id, session_id=None) -> {intent, reply, slots, data,
                                            suggestions, tool_calls, agent}

- intent ∈ find_seat | book_seat | my_session | stuck | recommend_content | rules | greeting | unknown
- 不依赖 Flask，不写业务表（预约/场次的创建属于主会话的 /api/bookings 等路由）。
  本模块只做两件事：**读库回答** + 写一条 agent_logs 审计记录（失败不影响回答）。

``data`` 里的键按意图固定（见各 ``_intent_*`` 函数 docstring），前端可直接用。
顺手多给的键（``agent_name`` / ``agent_role``）只是展示用，不属于契约。
"""
import re
from datetime import datetime, timedelta

import config
import db

INTENTS = ('find_seat', 'book_seat', 'my_session', 'stuck',
           'recommend_content', 'rules', 'greeting', 'unknown')

# 意图 → (展示名, 角色, 默认建议)
_AGENT_META = {
    'find_seat': ('座位管家', 'seating', ['帮我约第一个', '要带电源的', '三层还有空位吗']),
    'book_seat': ('预约助手', 'booking', ['按这个时间约', '改成两小时', '换个靠窗的']),
    'my_session': ('学习陪伴', 'session', ['我卡住了', '推荐一条视频', '我现在能结束吗']),
    'stuck': ('辅导老师', 'tutor', ['开始辅导：高数极限', '先记下这个卡点', '推荐一条对症视频']),
    'recommend_content': ('内容推荐官', 'content', ['换一批', '只看 10 分钟以内的', '这条为什么推给我']),
    'rules': ('规则助手', 'rules', ['我还有几次预约', '怎么签到', '超时了会怎样']),
    'greeting': ('小习', 'greeter', ['找座位', '帮我约座位', '我卡住了']),
    'unknown': ('小习', 'fallback', ['找座位', '帮我约座位', '我卡住了', '推荐视频']),
}

# 关键词表：**顺序即优先级**（先命中先赢）
_ROUTING = (
    ('my_session', ('我的场次', '当前场次', '场次', '这场', '还在学', '学多久', '学了多久',
                    '多久了', '还有多久', '坐了多久', '剩余时间', '还剩', '还要多久',
                    '签到', '我的预约', '我坐哪', '我在哪')),
    ('stuck', ('卡住', '卡壳', '不会', '不懂', '没思路', '听不懂', '搞不懂', '学不下',
               '太难', '崩溃', '放弃了', '怎么办啊')),
    ('rules', ('规则', '能约多久', '可以约多久', '多长', '时长上限', '限制', '取消',
               '违约', '爽约', '扣', '罚', '规定', '怎么算')),
    ('book_seat', ('预约', '订座', '帮我约', '帮我订', '占座', '订一个', '约一个',
                   '锁定', 'book')),
    ('recommend_content', ('推荐', '视频', '资料', '课程', '看点什么', '学点什么',
                           '有什么内容', '交棒')),
    ('find_seat', ('座位', '空位', '位置', '哪有', '找座', '靠窗', '电源', '插座',
                   '安静', '自习', '楼层', 'seat')),
)

_GREETING_WORDS = ('你好', '您好', 'hi', 'hello', '嗨', '在吗', '在么', '早上好',
                   '中午好', '下午好', '晚上好', '小习')

_PREFER = (('window', ('靠窗', '窗户', '窗边')), ('power', ('电源', '插座', '充电')),
           ('quiet', ('安静', '静一点', '别吵')))

_SUBJECTS = (('高等数学', ('高数', '数学', '极限', '微积分', '线代', '概率')),
             ('大学英语', ('英语', '四六级', '单词', '时态', '语法')),
             ('程序设计', ('编程', '代码', '递归', '算法', 'python', 'java', 'c语言')),
             ('大学物理', ('物理', '力学', '电磁')),
             ('思政', ('政治', '毛概', '马原', '形势与政策')))


# ---------------------------------------------------------------- 解析小工具

def _norm(text):
    return str(text or '').strip()


def _low(text):
    return _norm(text).lower()


def _hit(text, words):
    low = _low(text)
    return [w for w in words if w in low]


def _detect(text):
    """返回 (intent, 命中的关键词列表)。"""
    low = _low(text)
    if not low:
        return 'unknown', []
    # 问候：短句且就是问候本身
    greet = _hit(low, _GREETING_WORDS)
    if greet and len(re.sub(r'\s+', '', low)) <= 12:
        return 'greeting', greet
    for intent, words in _ROUTING:
        hits = _hit(low, words)
        if hits:
            return intent, hits
    return 'unknown', []


def _subject_of(text):
    for subject, words in _SUBJECTS:
        if _hit(text, words):
            return subject
    return ''


def _prefer_of(text):
    for kind, words in _PREFER:
        if _hit(text, words):
            return kind
    return ''


_SEAT_CODE_RE = re.compile(r'([A-Za-z]{1,3}\d{1,4})')
_TIME_RE = re.compile(r'(?<!\d)(\d{1,2})\s*[:：]\s*(\d{2})(?!\d)')
_HOUR_RE = re.compile(r'(?<!\d)(\d{1,2})\s*[点时]\s*(半|(\d{1,2})\s*分?)?')
_DUR_HOUR_RE = re.compile(r'(\d+(?:\.\d+)?)\s*(?:个)?\s*小时')
_DUR_MIN_RE = re.compile(r'(\d{1,3})\s*分钟')


def _parse_seat_code(text):
    m = _SEAT_CODE_RE.search(_norm(text))
    return m.group(1).upper() if m else ''


def _parse_window(text):
    """从一句话里抽时段。返回 (start_at, end_at, duration_min, 是否明确给了时间)。"""
    now = datetime.now()
    low = _low(text)
    day = now
    if '后天' in low:
        day = now + timedelta(days=2)
    elif '明天' in low:
        day = now + timedelta(days=1)

    hour = minute = None
    explicit = False
    m = _TIME_RE.search(low)
    if m:
        hour, minute, explicit = int(m.group(1)), int(m.group(2)), True
    else:
        m = _HOUR_RE.search(low)
        if m:
            hour, explicit = int(m.group(1)), True
            minute = 30 if m.group(2) == '半' else (int(m.group(3)) if m.group(3) else 0)
            if '下午' in low or '晚上' in low:
                if hour < 12:
                    hour += 12

    if hour is None:
        start = (now + timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)
        if start <= now:
            start = now.replace(second=0, microsecond=0) + timedelta(hours=1)
    else:
        hour = max(0, min(23, hour))
        minute = max(0, min(59, minute or 0))
        start = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if start < now - timedelta(minutes=1):
            start += timedelta(days=1)  # 说「19:00」但已过点 → 顺延到明天

    duration = 0
    m = _DUR_HOUR_RE.search(low)
    if m:
        duration = int(float(m.group(1)) * 60)
    elif '一个半小时' in low or '1个半小时' in low:
        duration = 90
    else:
        m = _DUR_MIN_RE.search(low)
        if m:
            duration = int(m.group(1))
    if not duration:
        duration = 90
    duration = max(int(config.MIN_DURATION_MIN), min(int(config.MAX_DURATION_MIN), duration))
    end = start + timedelta(minutes=duration)
    fmt = '%Y-%m-%d %H:%M:%S'
    return start.strftime(fmt), end.strftime(fmt), duration, explicit


def _remaining_min(end_at):
    try:
        end = db.parse(end_at)
    except Exception:
        return 0
    return max(0, int((end - datetime.now()).total_seconds() // 60))


_SEAT_TYPE_CN = {'window': '靠窗', 'power': '带电源', 'quiet': '安静区', 'normal': '普通区'}


def _seat_reason(seat):
    """座位推荐的「为什么」（PRODUCT §3：座位推荐必须给理由）。"""
    bits = []
    kind = (seat.get('seat_type') or 'normal')
    if kind in _SEAT_TYPE_CN:
        bits.append(_SEAT_TYPE_CN[kind])
    zone = (seat.get('zone') or '').strip()
    if zone and zone not in bits:
        bits.append(zone)
    feats = [f for f in (seat.get('features') or '').split(',') if f.strip()]
    if feats:
        bits.append('·'.join(f.strip() for f in feats))
    bits.append('当前空闲')
    return '，'.join(bits)


def _content_reason(content, subject='', keyword=''):
    """接力推荐的「为什么」（PRODUCT §3：接棒推荐必须给理由）。"""
    bits = []
    kp = (content.get('knowledge_point') or '')
    if keyword and keyword in kp:
        bits.append('正好对上你卡的「%s」' % keyword)
    elif subject and (content.get('subject') or '') == subject:
        bits.append('和你这门课同科目')
    elif kp:
        bits.append('知识点「%s」相邻' % kp)
    src = {'student': '同学交棒', 'teacher': '老师交棒', 'platform': '平台精选'}
    bits.append(src.get(content.get('source_type') or '', '同学交棒'))
    bits.append('已通过人工帧级复核')
    sec = content.get('duration_sec') or 0
    if sec:
        bits.append('约 %d 分钟' % max(1, int(sec // 60)))
    return '，'.join(bits)


# ---------------------------------------------------------------- 只读查询

def _user(user_id):
    if not user_id:
        return None
    return db.one('SELECT id,name,role,college FROM users WHERE id=?', (user_id,))


def _free_seats(prefer='', limit=5):
    sql = ("SELECT s.id, s.code, s.zone, s.seat_type, s.features, s.status,"
           "       f.name AS floor_name, f.floor_no"
           "  FROM seats s LEFT JOIN floors f ON f.id = s.floor_id"
           " WHERE s.status='free'")
    args = []
    if prefer:
        sql += " AND s.seat_type = ?"
        args.append(prefer)
    sql += " ORDER BY s.floor_id, s.code LIMIT ?"
    args.append(int(limit))
    return [dict(r) for r in db.query(sql, tuple(args))]


def _free_total(prefer=''):
    sql = "SELECT COUNT(*) AS n FROM seats WHERE status='free'"
    args = []
    if prefer:
        sql += " AND seat_type = ?"
        args.append(prefer)
    row = db.one(sql, tuple(args))
    return int(row['n']) if row else 0


def _seat_by_code(code):
    if not code:
        return None
    return db.one(
        "SELECT s.*, f.name AS floor_name, f.floor_no FROM seats s"
        " LEFT JOIN floors f ON f.id = s.floor_id"
        " WHERE UPPER(s.code)=?", (code.upper(),))


def _active_reservation(user_id):
    if not user_id:
        return None
    return db.one(
        "SELECT r.*, s.code AS seat_code, s.zone, f.name AS floor_name"
        "  FROM reservations r"
        "  LEFT JOIN seats s ON s.id = r.seat_id"
        "  LEFT JOIN floors f ON f.id = s.floor_id"
        " WHERE r.user_id=? AND r.status IN ('booked','checked_in')"
        " ORDER BY r.id DESC LIMIT 1", (user_id,))


def _active_session(user_id):
    if not user_id:
        return None
    return db.one(
        "SELECT ss.*, s.code AS seat_code, f.name AS floor_name"
        "  FROM study_sessions ss"
        "  LEFT JOIN seats s ON s.id = ss.seat_id"
        "  LEFT JOIN floors f ON f.id = s.floor_id"
        " WHERE ss.user_id=? AND ss.status='active'"
        " ORDER BY ss.id DESC LIMIT 1", (user_id,))


def _approved_contents(subject='', keyword='', limit=3):
    sql = ("SELECT id, title, subject, knowledge_point, description, duration_sec,"
           "       source_type, views, helpful, cover_path, published_at"
           "  FROM contents WHERE status='approved'")
    args = []
    if subject:
        sql += " AND subject=?"
        args.append(subject)
    if keyword:
        sql += " AND (knowledge_point LIKE ? OR title LIKE ? OR description LIKE ?)"
        args += ['%%%s%%' % keyword] * 3
    sql += " ORDER BY helpful DESC, views DESC, id DESC LIMIT ?"
    args.append(int(limit))
    return [dict(r) for r in db.query(sql, tuple(args))]


def _log(user_id, session_id, intent, text, reply, tool_calls):
    try:
        db.execute(
            'INSERT INTO agent_logs(user_id,session_id,intent,input,output,tool_calls,created_at)'
            ' VALUES(?,?,?,?,?,?,?)',
            (user_id, session_id, intent, _norm(text), reply,
             db.dumps([c.get('tool') for c in tool_calls]), db.now()))
    except Exception:
        pass  # 审计写失败不能拖垮回答


def _tool(name, ok=True, summary='', **args):
    return {'tool': name, 'ok': bool(ok), 'summary': summary, 'args': args}


# ---------------------------------------------------------------- 各意图的作答

def _intent_greeting(text, user_id, session_id):
    """data: {user:{id,name,role}}"""
    user = _user(user_id)
    calls = [_tool('query_user', ok=bool(user), summary='读取当前学生信息', user_id=user_id)]
    name = (dict(user)['name'] if user else '同学')
    reply = '嗨，%s！今天想学点什么？我可以帮你找座位、看当前场次，或者陪你过一遍卡住的知识点。' % name
    return {
        'reply': reply,
        'slots': {'user_name': name},
        'data': {'user': dict(user) if user else None},
        'suggestions': ['有空位吗', '我现在学了多久', '推荐一条视频'],
        'tool_calls': calls,
    }


def _intent_find_seat(text, user_id, session_id):
    """data: {prefer, free_total, seats:[...]}; slots: {prefer, seat_code}"""
    prefer = _prefer_of(text)
    seats = [dict(s, reason=_seat_reason(s)) for s in _free_seats(prefer, limit=5)]
    total = _free_total(prefer)
    calls = [_tool('query_seats', ok=True, summary='按偏好取空闲座位', prefer=prefer, total=total)]
    labels = {'window': '靠窗', 'power': '带电源', 'quiet': '安静区'}
    head = labels.get(prefer, '')
    if not seats:
        reply = ('%s座位现在都占满了。要不要我看看别的楼层，或者排一个候补？'
                 % (head + '的' if head else ''))
    else:
        first = seats[0]
        where = '%s %s' % (first.get('floor_name') or '', first['code'])
        reply = ('%s现在有 %d 个空位，先给你一个：%s（%s）。要我按 90 分钟帮你约上吗？'
                 % (head + '座位' if head else '自习区', total,
                    where.strip(), first.get('zone') or '普通区'))
    return {
        'reply': reply,
        'slots': {'prefer': prefer, 'seat_code': seats[0]['code'] if seats else ''},
        'data': {'prefer': prefer, 'free_total': total, 'seats': seats},
        'suggestions': ([('帮我约 %s' % seats[0]['code'])] if seats else []) +
                       ['要带电源的', '三层还有空位吗', '我现在有预约吗'],
        'tool_calls': calls,
    }


def _parse_subject_goal(text):
    return _subject_of(text), ''


def _intent_book_seat(text, user_id, session_id):
    """data: {seat, draft, rule}; slots: {seat_code, start_at, end_at, duration_min}"""
    code = _parse_seat_code(text)
    row = _seat_by_code(code) if code else None
    seat = dict(row) if row is not None else None
    start_at, end_at, duration, explicit = _parse_window(text)
    subject, goal = _parse_subject_goal(text)
    active = _active_reservation(user_id)
    calls = [_tool('query_seat', ok=bool(seat), summary='按座位号定位座位', code=code),
             _tool('parse_time_window', ok=True, summary='解析时段与时长',
                   start_at=start_at, end_at=end_at, duration_min=duration),
             _tool('query_reservations', ok=True, summary='检查进行中的预约',
                   has_active=bool(active))]

    if seat is not None and seat['status'] != 'free':
        reply = ('%s 号座位现在不可约（%s）。要不要我换一个同区域的空位？'
                 % (seat['code'], '维护中' if seat['status'] == 'maintenance' else seat['status']))
        return {
            'reply': reply,
            'slots': {'seat_code': seat['code']},
            'data': {'seat': dict(seat), 'draft': None, 'rule': {'max_active': config.MAX_ACTIVE_RESERVATIONS}},
            'suggestions': ['有没有别的空位', '换个座位'],
            'tool_calls': calls,
        }

    if not seat:
        seats = _free_seats(_prefer_of(text), limit=3)
        if seats:
            reply = ('没听清座位号。我按你的偏好挑了 %s，说一句「就这个」我就记下来。'
                     % '、'.join(s['code'] for s in seats))
        else:
            reply = '没听清座位号，而且现在没有空位了。等有人释放，我第一时间提醒你。'
        return {
            'reply': reply,
            'slots': {'seat_code': seats[0]['code'] if seats else ''},
            'data': {'seat': None, 'draft': None,
                     'rule': {'max_active': config.MAX_ACTIVE_RESERVATIONS},
                     'candidates': seats},
            'suggestions': [('帮我约 %s' % seats[0]['code'])] if seats else ['有空位吗'],
            'tool_calls': calls,
        }

    draft = {
        'seat_id': seat['id'],
        'seat_code': seat['code'],
        'seat_type': seat.get('seat_type') or 'normal',
        'floor_name': seat.get('floor_name') or '',
        'subject': subject,
        'goal': goal,
        'start_at': start_at,
        'end_at': end_at,
        'duration_min': duration,
        'source': 'agent',
    }
    rule = {
        'max_active': config.MAX_ACTIVE_RESERVATIONS,
        'min_duration_min': config.MIN_DURATION_MIN,
        'max_duration_min': config.MAX_DURATION_MIN,
        'has_active_reservation': bool(active),
    }
    when = ('%s 起' % start_at[5:16]) if explicit else ('默认从 %s 起' % start_at[5:16])
    reply = ('草稿好了：%s %s，%s，共 %d 分钟。回「照这个约」我就提交（同一时间只能有 1 个进行中的预约）。'
             % ((seat.get('floor_name') or '').strip(), seat['code'], when, duration))
    if active:
        reply += '注意你现在已经有一个进行中的预约，先结束它才能再约。'
    return {
        'reply': reply,
        'slots': {'seat_code': seat['code'], 'start_at': start_at,
                  'end_at': end_at, 'duration_min': duration, 'subject': subject},
        'data': {'seat': dict(seat), 'draft': draft, 'rule': rule},
        'suggestions': ['照这个约', '改成两小时', '换个靠窗的'],
        'tool_calls': calls,
    }


def _intent_my_session(text, user_id, session_id):
    """data: {reservation, session, remaining_min, elapsed_min}"""
    res = _active_reservation(user_id)
    sess = _active_session(user_id)
    calls = [_tool('query_reservations', ok=bool(res), summary='查进行中的预约', user_id=user_id),
             _tool('query_study_sessions', ok=bool(sess), summary='查进行中的学习场次', user_id=user_id)]

    if not res and not sess:
        reply = '你现在没有进行中的预约。要不要我先帮你找一个空位？'
        return {
            'reply': reply,
            'slots': {},
            'data': {'reservation': None, 'session': None, 'remaining_min': 0, 'elapsed_min': 0},
            'suggestions': ['有空位吗', '帮我约个座位', '推荐的视频'],
            'tool_calls': calls,
        }

    remaining = _remaining_min(res['end_at']) if res else 0
    elapsed = 0
    if sess:
        try:
            elapsed = db.minutes_between(sess['started_at'], db.now())
        except Exception:
            elapsed = int(sess['duration_min'] or 0)
    seat_code = (dict(res)['seat_code'] if res else None) or (dict(sess)['seat_code'] if sess else None)
    parts = []
    if seat_code:
        parts.append('你在 %s%s' % ((dict(res)['floor_name'] if res else dict(sess)['floor_name']) or '', seat_code))
    if sess:
        parts.append('已学 %d 分钟' % elapsed)
    if res:
        parts.append('还剩 %d 分钟（%s 到期）' % (remaining, res['end_at'][11:16]))
    reply = '，'.join(parts) + '。'
    if res and not res['checkin_at'] and res['status'] == 'booked':
        reply += '别忘了先在座位页签到 —— 超过 %d 分钟没签到会记爽约。' % config.CHECKIN_TIMEOUT_MIN
    elif remaining and remaining <= 10:
        reply += '快到点了，结束后我会把接棒内容推给你。'
    return {
        'reply': reply,
        'slots': {'seat_code': seat_code or ''},
        'data': {
            'reservation': dict(res) if res else None,
            'session': dict(sess) if sess else None,
            'remaining_min': remaining,
            'elapsed_min': elapsed,
        },
        'suggestions': ['我卡住了', '推荐一条视频', '现在就结束'],
        'tool_calls': calls,
    }


def _intent_stuck(text, user_id, session_id):
    """data: {subject, knowledge_point, stuck_points, tutor_topics}"""
    sess = _active_session(user_id)
    subject = (dict(sess)['subject'] if sess else '') or _subject_of(text)
    stuck = (dict(sess)['stuck_points'] if sess else '') or ''
    keyword = ''
    for word in ('极限', '时态', '递归', '求导', '积分', '矩阵', '语法'):
        if word in _low(text):
            keyword = word
            break
    calls = [_tool('query_study_sessions', ok=bool(sess), summary='查当前场次与卡点',
                   subject=subject, has_stuck=bool(stuck)),
             _tool('query_contents', ok=True, summary='按知识点找对症内容', keyword=keyword)]
    replies = ['卡住很正常，说明正在往难的地方走。',
               '这一步卡住不丢人，我们先把它拆小。']
    reply = replies[len(_norm(text)) % 2]
    if subject:
        reply += '你现在在学「%s」，' % subject
    else:
        reply += ''
    reply += ('要不要我用三步提问带你想一遍（一次只问一个问题）？'
              '或者我先把卡点记下来，结束时推一条对症的视频给你。')
    return {
        'reply': reply,
        'slots': {'subject': subject, 'knowledge_point': keyword},
        'data': {
            'subject': subject,
            'knowledge_point': keyword,
            'stuck_points': stuck,
            'session': dict(sess) if sess else None,
            'tutor_topics': ['高数极限', '英语时态', '编程递归'],
        },
        'suggestions': ([('开始辅导：%s' % (keyword or '高数极限'))] if keyword else ['开始辅导：高数极限']) +
                       ['先记下这个卡点', '推荐一条对症视频'],
        'tool_calls': calls,
    }


def _intent_recommend_content(text, user_id, session_id):
    """data: {subject, keyword, contents:[...]}"""
    sess = _active_session(user_id)
    subject = _subject_of(text) or ((dict(sess)['subject'] if sess else '') or '')
    keyword = ''
    for word in ('极限', '时态', '递归', '求导', '积分'):
        if word in _low(text):
            keyword = word
            break
    rows = [dict(r, reason=_content_reason(r, subject, keyword))
            for r in _approved_contents(subject=subject, keyword=keyword, limit=3)]
    calls = [_tool('query_contents', ok=True, summary='从接力池（已过审）取推荐',
                   subject=subject, keyword=keyword, count=len(rows))]
    if not rows:
        reply = ('接力池里暂时没有%s对症的已过审内容 —— 我不硬凑一条。'
                 '等老师交棒入池后，我第一时间推给你。'
                 % (('「%s」' % (keyword or subject)) if (keyword or subject) else ''))
        suggestions = ['换个科目看看', '看看全部推荐', '我卡住了']
    else:
        top = rows[0]
        mins = int((top['duration_sec'] or 0) // 60)
        reply = ('从接力池给你挑了 %d 条，最对症的是《%s》（%s%s）。'
                 '为什么推给你：%s。'
                 % (len(rows), top['title'],
                    ('%d 分钟' % mins) if mins else '短视频',
                    ('·' + top['knowledge_point']) if top['knowledge_point'] else '',
                    top['reason']))
        suggestions = ['换一批', '只看 10 分钟以内的', '这条为什么推给我']
    return {
        'reply': reply,
        'slots': {'subject': subject, 'knowledge_point': keyword},
        'data': {'subject': subject, 'keyword': keyword, 'contents': rows},
        'suggestions': suggestions,
        'tool_calls': calls,
    }


def _intent_rules(text, user_id, session_id):
    """data: {rules:{...}}"""
    rules = {
        'min_duration_min': config.MIN_DURATION_MIN,
        'max_duration_min': config.MAX_DURATION_MIN,
        'max_active_reservations': config.MAX_ACTIVE_RESERVATIONS,
        'checkin_timeout_min': config.CHECKIN_TIMEOUT_MIN,
    }
    calls = [_tool('query_rules', ok=True, summary='读 config 里的预约规则', **rules)]
    topic = ''
    if _hit(text, ('取消', '退', '撤销')):
        topic = 'cancel'
        reply = ('预约开始前可以在「我的预约」里取消；已签到的不算取消，按结束处理。'
                 '爽约（预约了没签到、也没取消）会记一次违规。')
    elif _hit(text, ('签到', '迟到')):
        topic = 'checkin'
        reply = ('到座位后 15 分钟内签到有效（%d 分钟）。超时自动记爽约并释放座位，'
                 '你可以在座位页重新约一个。' % config.CHECKIN_TIMEOUT_MIN)
    else:
        topic = 'duration'
        reply = ('单次最长 %d 分钟、最短 %d 分钟；同一时间只能有 %d 个进行中的预约；'
                 '签到时限 %d 分钟。' % (config.MAX_DURATION_MIN, config.MIN_DURATION_MIN,
                                     config.MAX_ACTIVE_RESERVATIONS, config.CHECKIN_TIMEOUT_MIN))
    return {
        'reply': reply,
        'slots': {'topic': topic},
        'data': {'rules': rules, 'topic': topic},
        'suggestions': ['怎么签到', '超时了会怎样', '我现在有预约吗'],
        'tool_calls': calls,
    }


def _intent_unknown(text, user_id, session_id):
    """data: {intents:[...]}"""
    return {
        'reply': ('这句话我还没学会。你可以直接说「有空位吗」「帮我约 A12」「我现在学了多久」'
                  '「我卡住了」「推荐一条视频」这类话。'),
        'slots': {},
        'data': {'intents': list(INTENTS)},
        'suggestions': ['有空位吗', '帮我约个座位', '我卡住了', '推荐视频'],
        'tool_calls': [_tool('route_intent', ok=False, summary='没有命中任何规则意图', text=_norm(text)[:80])],
    }


_HANDLERS = {
    'greeting': _intent_greeting,
    'find_seat': _intent_find_seat,
    'book_seat': _intent_book_seat,
    'my_session': _intent_my_session,
    'stuck': _intent_stuck,
    'recommend_content': _intent_recommend_content,
    'rules': _intent_rules,
    'unknown': _intent_unknown,
}


# ---------------------------------------------------------------- 入口

def ask(text, user_id, session_id=None):
    """一句话 → 结构化答复。永不抛异常（内部异常降级成 unknown + 提示）。"""
    intent, hits = _detect(text)
    handler = _HANDLERS.get(intent) or _intent_unknown
    try:
        body = handler(text, user_id, session_id)
    except Exception as exc:  # 查库异常也别让对话挂掉
        intent = 'unknown'
        body = {
            'reply': '我这边查数据出了点问题（%s），稍后再试一下？' % type(exc).__name__,
            'slots': {},
            'data': {'error': '%s: %s' % (type(exc).__name__, exc)},
            'suggestions': ['有空位吗', '推荐视频'],
            'tool_calls': [_tool('internal', ok=False, summary='处理意图时出错', intent=intent)],
        }
    name, role, default_suggestions = _AGENT_META.get(intent, ('小习', 'fallback', []))
    tool_calls = body.get('tool_calls') or []
    result = {
        'intent': intent,
        'reply': body.get('reply', ''),
        'slots': body.get('slots') or {},
        'data': body.get('data') or {},
        'suggestions': body.get('suggestions') or default_suggestions,
        'tool_calls': tool_calls,
        'agent': role,
        'agent_name': name,
        'matched_keywords': hits,
    }
    _log(user_id, session_id, intent, text, result['reply'], tool_calls)
    return result


if __name__ == '__main__':
    # 从项目根跑：python -m services.agents
    db.init_db()
    for q in ('你好', '有空位吗', '帮我约明天19:00的A12两小时', '我现在学了多久',
              '我卡住了，极限不会', '推荐点高数视频', '能约多久', '随便说点啥'):
        r = ask(q, None)
        print('%-28s → %-18s %s' % (q, r['intent'], r['reply'][:48]))
