# -*- coding: utf-8 -*-
"""苏格拉底式辅导（对端 A）。

契约见 docs/CONTRACT.md 第 5 节：

    start(topic, user_id, session_id=None) -> {tutor_id, question, options, step}
    answer(tutor_id, text) -> {done, question, explanation, check_question, resource, step}

设计：
- 3 个主题（高数极限 / 英语时态 / 编程递归）+ 1 个兜底（general，先问清卡在哪）。
- **每轮只问一个问题**；答完立刻给「解释 + 检查问题 + 一条 approved 内容」。
- 学生说「不会/不知道」不算答错，也不算通过：**承认这一步没讲清楚**，换一个更小的
  问法重问（step 不推进），并给出可执行建议。
- 状态存进程内存 ``_TUTORS``（契约允许）。重启即失效，过期或超量自动清理。
- 推荐内容严格来自 contents.status='approved'；池里没有就返回 None 并说明，不硬凑。
"""
import uuid
from datetime import datetime

import db

_TUTORS = {}
_MAX_TUTORS = 200
_TTL_MIN = 120

_GIVE_UP_WORDS = ('不会', '不知道', '不懂', '没思路', '不明白', '放弃', '跳过',
                  '直接告诉我', '给答案', '想不出', '太难了')

TOPICS = [
    {
        'key': 'math_limit',
        'name': '高数极限',
        'desc': '用「趋势」而不是「取值」理解极限，再拆 0/0 型未定式',
        'subject': '高等数学',
        'knowledge_point': '极限',
        'aliases': ('极限', '高数', '微积分', '数列', '求极限', 'math_limit'),
        'steps': [
            {
                'question': '先不谈公式：f(x)=1/x，当 x 取 10、100、1000……一直在变大时，'
                            'f(x) 是在变大还是变小？它会不会真的变成 0？',
                'options': ['越来越小，但永远不为 0', '会变成 0', '会变成负数'],
                'accept': ('越来越小', '无限接近', '趋近', '接近0', '接近 0', '不会到', '不为0', '不为 0'),
                'explanation': '对。它无限接近 0 却到不了 0 —— 这就是极限的直觉：'
                               '极限描述的不是「取到的值」，而是「越来越靠近的地方」。',
                'check_question': '用一句话说：极限说的是「到得了的点」还是「越来越靠近的点」？',
                'hint': '换个更小的问法：1/10、1/100、1/1000 分别是多少？它们离 0 有多远？',
            },
            {
                'question': '再看 f(x)=sin(x)/x（x→0）。直接代入 0 得到 0/0，看起来没意义。'
                            '这个式子在 x 越来越接近 0 时，有没有一个稳定的趋近值？',
                'options': ['有，等于 1', '没有极限', '等于 0', '说不准，得画图或变形才知道'],
                'accept': ('等于1', '= 1', '=1', '是1', '有极限', '收敛', '逼近1', '1'),
                'explanation': '有，等于 1。0/0 只是「形式未定」，不是「不存在」。'
                               '把 sin x 在 0 附近展开成 x − x³/6 + …，除以 x 得 1 − x²/6，'
                               'x→0 时自然趋近 1。',
                'check_question': '所以「代入后无意义」能不能等于「极限不存在」？为什么？',
                'hint': '先算 x=0.1：sin(0.1)=0.0998…，除以 0.1 大约是多少？再用 x=0.01 试一次。',
            },
        ],
    },
    {
        'key': 'english_tense',
        'name': '英语时态',
        'desc': '现在完成 vs 一般过去：看的是「对现在的影响」还是「过去的时间点」',
        'subject': '大学英语',
        'knowledge_point': '时态',
        'aliases': ('时态', '英语', '语法', '完成时', '四六级', 'english'),
        'steps': [
            {
                'question': '对比两句：「I have finished my homework.」和「I finished my '
                            'homework yesterday.」—— 第一句重点强调的是哪一个？',
                'options': ['动作发生在过去的具体时间', '对现在的影响（作业现在是完成状态）', '将来要完成的事'],
                'accept': ('现在', '影响', '已完成', '完成状态', '对现在'),
                'explanation': '对。现在完成时说「过去做的动作 + 对现在的影响」；'
                               '一般过去时只交代「过去某个时间点发生过」。',
                'check_question': '句子里出现 yesterday / last week 这类明确过去时间时，更该用哪个时态？',
                'hint': '把两句都翻译成中文看看：哪一句在说「作业现在是完成的」，哪一句只是在讲故事？',
            },
            {
                'question': '那「我学英语学了三年（现在还在学）」该怎么说？',
                'options': ['I learned English for 3 years.',
                            'I have learned English for 3 years.',
                            'I am learning English 3 years.'],
                'accept': ('have learned', 'have been learning', '现在完成', '完成进行', '完成时'),
                'explanation': 'I have learned English for 3 years. / I have been learning '
                               'English for 3 years. 都可以。持续到现在用完成（进行）时；'
                               '用过去时则表示「学过，现在不学了」。',
                'check_question': '如果改成「我学了三年，后来不学了」，时态要不要变？变成哪个？',
                'hint': '先判断关键区别：这件事现在还在继续，还是已经结束了？',
            },
        ],
    },
    {
        'key': 'coding_recursion',
        'name': '编程递归',
        'desc': '递归必须有出口，再看重复子问题怎么用记忆化收拾',
        'subject': '程序设计',
        'knowledge_point': '递归',
        'aliases': ('递归', '编程', '代码', '算法', 'python', 'recursion'),
        'steps': [
            {
                'question': '写阶乘：fact(n) = n * fact(n-1)。要让这个函数不会一直调用下去，'
                            '你必须在里面写什么？',
                'options': ['一个 for 循环', '终止条件（base case），比如 n<=1 时返回 1', '一个全局变量'],
                'accept': ('终止', '出口', 'base', '边界', 'n<=1', 'n == 1', 'n==1', '返回1', '返回 1'),
                'explanation': '对。必须有不依赖递归的出口（n<=1 直接返回 1），否则栈一直加深，'
                               '最后 RecursionError。递归 = 出口 + 把问题缩小的那一步。',
                'check_question': '每次递归调用，问题规模是变小还是变大？不变会怎样？',
                'hint': '先手算 fact(1) 和 fact(2)：哪一步不需要再调用自己就能直接算出结果？',
            },
            {
                'question': 'fib(n) = fib(n-1) + fib(n-2)，n=35 时跑得很慢。问题出在哪？',
                'options': ['递归深度太大', '同一个子问题被重复计算了很多次', 'Python 本身太慢'],
                'accept': ('重复', '重叠', '缓存', '记忆', 'memo', '存起来', '同一个'),
                'explanation': '对。重叠子问题被反复计算，复杂度约 O(2ⁿ)。加缓存（memo）后每个 n '
                               '只算一次，降到 O(n) —— 递归 + 记忆化就是动态规划的雏形。',
                'check_question': '如果把结果存进 dict，再遇到同样的 n 直接取，复杂度会变成多少？',
                'hint': '试着手工展开 fib(5)：fib(3) 被算了几次？fib(2) 呢？',
            },
        ],
    },
    {
        'key': 'general',
        'name': '通用拆题',
        'desc': '先把卡点圈小：是看不懂、想不到方法，还是写到一半报错',
        'subject': '',
        'knowledge_point': '',
        'aliases': ('通用', '别的', '其他', 'general'),
        'steps': [
            {
                'question': '我们先把问题圈小：你现在具体卡在哪一步 —— 看不懂题目、'
                            '想不到方法，还是写到一半报错？',
                'options': ['看不懂题目', '想不到方法', '写到一半报错'],
                'accept': ('看不懂', '想不到', '报错', '方法', '步骤', '卡', '不确定'),
                'explanation': '好，范围清楚了。卡点越具体，越容易一次解决一个。',
                'check_question': '能把那一行代码或那道题的原话贴一下吗？',
                'hint': '那我们换个问法：这道题/这段代码，你的输入是什么、期望输出是什么？',
            },
            {
                'question': '做一个最小尝试：先写下「输入是什么、期望输出是什么」，'
                            '再说说你想到的第一步。你的输入和输出分别是什么？',
                'options': ['我知道输入输出', '只知道输入', '连题目都没读懂'],
                'accept': ('输入', '输出', '知道'),
                'explanation': '很好。把输入输出钉住之后，剩下的就是「从一个例子推到另一个例子」，'
                               '卡住的地方往往是缺一个中间状态。',
                'check_question': '用一个具体的例子走一遍，你能说出中间那一步是什么吗？',
                'hint': '那就先只做一件事：把题目的例子抄下来，标出哪一步你看不懂。',
            },
        ],
    },
]

_TOPIC_BY_KEY = {t['key']: t for t in TOPICS}


# ---------------------------------------------------------------- 内部工具

def _hit(text, words):
    low = str(text or '').lower()
    return any(w in low for w in words)


def _resolve_topic(topic):
    raw = str(topic or '').strip().lower()
    if raw in _TOPIC_BY_KEY:
        return _TOPIC_BY_KEY[raw]
    for t in TOPICS:
        if any(a in raw for a in t['aliases']):
            return t
    return _TOPIC_BY_KEY['general']


def _prune():
    """清掉过期与超量的会话，避免内存常驻。"""
    now = datetime.now()
    dead = []
    for tid, st in _TUTORS.items():
        try:
            age_min = (now - datetime.strptime(st['created_at'], '%Y-%m-%d %H:%M:%S')).total_seconds() / 60
        except Exception:
            age_min = _TTL_MIN + 1
        if age_min > _TTL_MIN:
            dead.append(tid)
    for tid in dead:
        _TUTORS.pop(tid, None)
    if len(_TUTORS) > _MAX_TUTORS:
        for tid, _ in sorted(_TUTORS.items(), key=lambda kv: kv[1]['created_at'])[:len(_TUTORS) - _MAX_TUTORS]:
            _TUTORS.pop(tid, None)


def _resource(topic):
    """从 approved 池里挑一条对症内容；没有就返回 None。"""
    if not (topic.get('subject') or topic.get('knowledge_point')):
        return None
    sql = ("SELECT id, title, subject, knowledge_point, duration_sec, source_type,"
           "       cover_path, helpful, views"
           "  FROM contents WHERE status='approved'")
    args = []
    if topic.get('knowledge_point'):
        sql += " AND (knowledge_point LIKE ? OR title LIKE ? OR description LIKE ?)"
        args += ['%%%s%%' % topic['knowledge_point']] * 3
    elif topic.get('subject'):
        sql += " AND subject=?"
        args.append(topic['subject'])
    sql += " ORDER BY helpful DESC, views DESC, id DESC LIMIT 1"
    try:
        row = db.one(sql, tuple(args))
    except Exception:
        return None
    if row is None:
        return None
    data = dict(row)
    return {
        'id': data['id'],
        'title': data['title'],
        'subject': data.get('subject') or '',
        'knowledge_point': data.get('knowledge_point') or '',
        'duration_sec': data.get('duration_sec') or 0,
        'source_type': data.get('source_type') or '',
        'cover_path': data.get('cover_path') or '',
        'reason': '与你这个知识点「%s」对得上，且已通过人工审核' % (data.get('knowledge_point') or topic.get('knowledge_point') or topic.get('subject')),
    }


def _expired(tutor_id):
    return {
        'tutor_id': str(tutor_id or ''),
        'done': True,
        'question': '',
        'explanation': '这个辅导会话已经过期了（重启服务或超过 %d 分钟会失效）。我们再开一个新的吧。' % _TTL_MIN,
        'check_question': '',
        'resource': None,
        'step': 0,
        'error': 'tutor_not_found',
    }


# ---------------------------------------------------------------- 对外接口

def list_topics():
    """加法：给前端的主题选择器用。"""
    return [{'key': t['key'], 'name': t['name'], 'desc': t['desc'],
             'subject': t['subject'], 'knowledge_point': t['knowledge_point'],
             'steps': len(t['steps'])} for t in TOPICS]


def start(topic, user_id, session_id=None):
    """开一轮辅导：返回 {tutor_id, question, options, step}。"""
    _prune()
    t = _resolve_topic(topic)
    tutor_id = uuid.uuid4().hex
    step0 = t['steps'][0]
    _TUTORS[tutor_id] = {
        'topic': t['key'],
        'user_id': user_id,
        'session_id': session_id,
        'step': 0,
        'done': False,
        'history': [],
        'created_at': db.now(),
    }
    return {
        'tutor_id': tutor_id,
        'topic': t['key'],
        'topic_name': t['name'],
        'subject': t['subject'],
        'question': step0['question'],
        'options': list(step0['options']),
        'step': 0,
        'total_steps': len(t['steps']),
    }


def answer(tutor_id, text):
    """回答一个问题：返回 {done, question, explanation, check_question, resource, step}。"""
    state = _TUTORS.get(tutor_id)
    if state is None:
        return _expired(tutor_id)
    topic = _TOPIC_BY_KEY.get(state['topic']) or _TOPIC_BY_KEY['general']
    steps = topic['steps']
    txt = str(text or '').strip()
    state['step'] = min(state['step'], len(steps) - 1)
    current = steps[state['step']]

    if state['done']:
        return {
            'tutor_id': tutor_id,
            'done': True,
            'question': '',
            'explanation': '这轮已经收尾了。要再来一轮别的知识点，直接说主题就行。',
            'check_question': current['check_question'],
            'resource': _resource(topic),
            'step': state['step'],
            'verdict': 'finished',
        }

    if not txt:
        return {
            'tutor_id': tutor_id,
            'done': False,
            'question': current['question'],
            'explanation': '我先等你的想法 —— 随便说一句都行，说错也没关系。',
            'check_question': '',
            'resource': None,
            'step': state['step'],
            'verdict': 'empty',
        }

    # 1) 说不会：承认+换更小的问法，不推进（不假装他学会了）
    if _hit(txt, _GIVE_UP_WORDS) and not _hit(txt, current['accept']):
        state['history'].append({'text': txt, 'verdict': 'gave_up', 'step': state['step']})
        return {
            'tutor_id': tutor_id,
            'done': False,
            'question': current['hint'],
            'explanation': '这一步是我没讲清楚，先承认：换个更小的问法我们再来一次。'
                           '你也可以把它记成卡点，结束后我推一条对症的视频给你。',
            'check_question': '',
            'resource': _resource(topic),
            'step': state['step'],
            'verdict': 'gave_up',
        }

    # 2) 作答：判断是否命中要点，然后推进
    matched = _hit(txt, current['accept'])
    state['history'].append({'text': txt, 'verdict': 'correct' if matched else 'partial',
                             'step': state['step']})
    prefix = '' if matched else '你的思路有一部分对，不过更关键的是：'
    explanation = prefix + current['explanation']
    if not matched:
        try:
            from . import llm
            _ai_hint = llm.tutor_hint(topic, current, txt)
            if _ai_hint:
                explanation = '先别急，我们换个更小的角度：' + _ai_hint
        except Exception:
            pass
    state['step'] += 1

    if state['step'] >= len(steps):
        state['done'] = True
        return {
            'tutor_id': tutor_id,
            'done': True,
            'question': '',
            'explanation': explanation + ' 这一轮就到这里 —— 能用自己的话把刚才两句讲一遍，才算真的会。',
            'check_question': current['check_question'],
            'resource': _resource(topic),
            'step': state['step'],
            'verdict': 'correct' if matched else 'partial',
        }

    nxt = steps[state['step']]
    return {
        'tutor_id': tutor_id,
        'done': False,
        'question': nxt['question'],
        'explanation': explanation,
        'check_question': current['check_question'],
        'resource': _resource(topic),
        'step': state['step'],
        'verdict': 'correct' if matched else 'partial',
    }


def get(tutor_id):
    """加法：查看会话状态（调试/前端恢复用）。"""
    state = _TUTORS.get(tutor_id)
    if state is None:
        return None
    out = dict(state)
    out['history'] = list(state['history'])
    return out


def reset_all():
    """加法：测试用，清空内存会话。"""
    _TUTORS.clear()


if __name__ == '__main__':
    # 从项目根跑：python -m services.tutor
    db.init_db()
    for t in list_topics():
        print('%-16s %s（%d 轮）' % (t['key'], t['name'], t['steps']))
    s = start('高数极限', None)
    print('\nQ0:', s['question'])
    a = answer(s['tutor_id'], '越来越小，但永远不为 0')
    print('A0:', a['explanation'][:60], '| Q1:', a['question'][:40])
    b = answer(s['tutor_id'], '有，等于 1')
    print('done:', b['done'], '| resource:', (b['resource'] or {}).get('title'))
