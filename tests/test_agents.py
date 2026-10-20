# -*- coding: utf-8 -*-
"""services/agents.py + services/tutor.py 的测试（对端 A）。

跑法：
    cd D:\\华为ICT\\zhixue-space && python -m pytest -q
每个用例用 tmp_path 下的独立 SQLite 文件 + 一份最小演示数据（学生 / 三个座位 / 一条进行中
预约 / 一条进行中场次 / 一条已过审内容 / 一条待审内容）。
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if 'ZX_DATA_DIR' not in os.environ:
    os.environ['ZX_DATA_DIR'] = tempfile.mkdtemp(prefix='zx-test-')

import pytest

import config
import db
from services import agents, tutor

FMT = '%Y-%m-%d %H:%M:%S'
REQUIRED_KEYS = {'intent', 'reply', 'slots', 'data', 'suggestions', 'tool_calls', 'agent'}


# ---------------------------------------------------------------- fixture

@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 'zhixue.db'))
    db.init_db()
    now = db.now()
    now_dt = datetime.now()

    uid = db.execute(
        'INSERT INTO users(username,password_hash,name,role,college,created_at)'
        ' VALUES(?,?,?,?,?,?)',
        ('student', 'x', '李小习', 'student', '计算机与信息技术学院', now))
    fid = db.execute('INSERT INTO floors(name,building,floor_no) VALUES(?,?,?)',
                     ('三层自习区', '图书馆', 3))
    seat = db.execute(
        "INSERT INTO seats(floor_id,code,zone,x,y,seat_type,features,status)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (fid, 'A12', '安静区', 10, 20, 'window', '靠窗,插座', 'free'))
    db.execute(
        "INSERT INTO seats(floor_id,code,zone,x,y,seat_type,features,status)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (fid, 'B07', '普通区', 60, 80, 'normal', '', 'free'))
    db.execute(
        "INSERT INTO seats(floor_id,code,zone,x,y,seat_type,features,status)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (fid, 'C09', '普通区', 90, 90, 'normal', '', 'maintenance'))
    seat_busy = db.one("SELECT id FROM seats WHERE code='C09'")['id']
    seat_free2 = db.one("SELECT id FROM seats WHERE code='B07'")['id']

    start_at = (now_dt - timedelta(minutes=30)).strftime(FMT)
    end_at = (now_dt + timedelta(minutes=78)).strftime(FMT)
    rid = db.execute(
        'INSERT INTO reservations(user_id,seat_id,subject,goal,start_at,end_at,'
        'checkin_at,status,source,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
        (uid, seat, '高等数学', '刷完极限', start_at, end_at, start_at, 'checked_in', 'web', now))
    sid = db.execute(
        'INSERT INTO study_sessions(reservation_id,user_id,seat_id,subject,started_at,'
        'duration_min,status,stuck_points,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
        (rid, uid, seat, '高等数学', start_at, 42, 'active', '', now))

    cid = db.execute(
        "INSERT INTO contents(owner_id,title,subject,knowledge_point,description,source_type,"
        "status,duration_sec,published_at,created_at,views,helpful)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (uid, '极限的ε-δ直观讲法', '高等数学', '极限', '把 0/0 讲成趋势', 'teacher',
         'approved', 720, now, now, 10, 3))
    db.execute(
        "INSERT INTO contents(owner_id,title,subject,knowledge_point,source_type,status,"
        "duration_sec,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (uid, '待审：极限速览', '高等数学', '极限', 'student', 'pending_review', 300, now))

    return {
        'user_id': uid,
        'floor_id': fid,
        'seat_id': seat,
        'seat_free_id': seat_free2,
        'seat_busy_id': seat_busy,
        'reservation_id': rid,
        'session_id': sid,
        'content_id': cid,
    }


# ---------------------------------------------------------------- agents: 形状与路由

def test_ask_returns_contract_keys(seeded):
    r = agents.ask('你好', seeded['user_id'])
    assert REQUIRED_KEYS <= set(r)
    assert r['intent'] in agents.INTENTS
    assert isinstance(r['reply'], str) and r['reply']
    assert isinstance(r['slots'], dict)
    assert isinstance(r['data'], dict)
    assert isinstance(r['suggestions'], list) and r['suggestions']
    assert isinstance(r['tool_calls'], list) and r['tool_calls']
    assert all('tool' in c and 'ok' in c for c in r['tool_calls'])


@pytest.mark.parametrize('text, intent', [
    ('你好呀', 'greeting'),
    ('有没有靠窗的空位', 'find_seat'),
    ('帮我预约明天下午的座位', 'book_seat'),
    ('我现在这个场次还有多久', 'my_session'),
    ('我卡住了，高数极限不懂', 'stuck'),
    ('推荐点高数视频', 'recommend_content'),
    ('能约多长时间', 'rules'),
    ('今天天气怎么样', 'unknown'),
    ('asdfghjkl', 'unknown'),
])
def test_routing(seeded, text, intent):
    assert agents.ask(text, seeded['user_id'])['intent'] == intent


def test_greeting_uses_username(seeded):
    r = agents.ask('你好', seeded['user_id'])
    assert r['data']['user']['name'] == '李小习'
    assert '李小习' in r['reply']
    assert r['agent'] == 'greeter'


def test_unknown_gives_actionable_hints(seeded):
    r = agents.ask('asdfghjkl', seeded['user_id'])
    assert r['intent'] == 'unknown'
    assert '有空位' in r['reply']
    assert r['suggestions']
    assert r['tool_calls'][0]['ok'] is False


def test_empty_text_is_unknown_not_crash(seeded):
    r = agents.ask('', seeded['user_id'])
    assert r['intent'] == 'unknown' and r['reply']


# ---------------------------------------------------------------- agents: 各意图的数据

def test_find_seat_only_returns_free(seeded):
    r = agents.ask('有没有靠窗的空位', seeded['user_id'])
    assert r['intent'] == 'find_seat'
    seats = r['data']['seats']
    assert seats, '应该有空位'
    assert all(s['status'] == 'free' for s in seats)
    codes = {s['code'] for s in seats}
    assert 'A12' in codes
    assert 'C09' not in codes                       # maintenance 座位不能出现
    assert r['data']['prefer'] == 'window'
    assert r['data']['free_total'] >= 1
    assert r['slots']['seat_code'] == 'A12'
    assert 'A12' in r['reply']
    assert any('query_seats' == c['tool'] for c in r['tool_calls'])


def test_find_seat_with_power_preference(seeded):
    r = agents.ask('有没有带电源的座位', seeded['user_id'])
    assert r['intent'] == 'find_seat'
    assert r['data']['prefer'] == 'power'
    assert r['data']['seats'] == []          # 数据集里没有 power 座位 → 空，并且如实说占满
    assert '占满' in r['reply']


def test_my_session_reports_active_state(seeded):
    r = agents.ask('我的场次还剩多久', seeded['user_id'])
    assert r['intent'] == 'my_session'
    assert r['data']['session']['id'] == seeded['session_id']
    assert r['data']['reservation']['id'] == seeded['reservation_id']
    assert r['data']['remaining_min'] > 0
    assert r['data']['elapsed_min'] >= 29
    assert 'A12' in r['reply']


def test_my_session_without_data(seeded):
    r = agents.ask('我的场次还剩多久', 99999)
    assert r['intent'] == 'my_session'
    assert r['data']['session'] is None
    assert r['data']['reservation'] is None
    assert r['data']['remaining_min'] == 0
    assert '没有进行中的预约' in r['reply']


def test_recommend_content_only_approved(seeded):
    r = agents.ask('推荐点高数视频', seeded['user_id'])
    assert r['intent'] == 'recommend_content'
    titles = [c['title'] for c in r['data']['contents']]
    assert '极限的ε-δ直观讲法' in titles
    assert '待审：极限速览' not in titles
    assert r['data']['subject'] == '高等数学'
    assert '极限的ε-δ直观讲法' in r['reply']


def test_book_seat_returns_draft_and_does_not_write(seeded):
    before = len(db.query('SELECT id FROM reservations'))
    r = agents.ask('帮我约明天 19:00 的 A12 座位', seeded['user_id'])

    assert r['intent'] == 'book_seat'
    assert len(db.query('SELECT id FROM reservations')) == before   # 只给草稿，不写库

    draft = r['data']['draft']
    assert draft['seat_id'] == seeded['seat_id']
    assert draft['seat_code'] == 'A12'
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    assert draft['start_at'].startswith(tomorrow)
    assert ':19:00:00' in draft['start_at'] or '19:00:00' in draft['start_at']
    assert config.MIN_DURATION_MIN <= draft['duration_min'] <= config.MAX_DURATION_MIN
    assert r['data']['rule']['has_active_reservation'] is True
    assert '已经有一个进行中的预约' in r['reply']


def test_book_seat_rejects_maintenance_seat(seeded):
    r = agents.ask('帮我约 C09', seeded['user_id'])
    assert r['intent'] == 'book_seat'
    assert r['data']['draft'] is None
    assert '不可约' in r['reply']
    assert r['data']['seat']['code'] == 'C09'


def test_book_seat_without_code_offers_candidates(seeded):
    r = agents.ask('帮我预约一个座位', seeded['user_id'])
    assert r['intent'] == 'book_seat'
    assert r['data']['draft'] is None
    assert r['data']['candidates']
    assert r['slots']['seat_code']


def test_stuck_reads_current_subject(seeded):
    r = agents.ask('我卡住了，高数极限不懂', seeded['user_id'])
    assert r['intent'] == 'stuck'
    assert r['data']['subject'] == '高等数学'
    assert r['data']['knowledge_point'] == '极限'
    assert r['data']['session']['id'] == seeded['session_id']
    assert any('辅导' in s for s in r['suggestions'])


def test_rules_come_from_config(seeded):
    r = agents.ask('能约多长时间', seeded['user_id'])
    assert r['intent'] == 'rules'
    rules = r['data']['rules']
    assert rules['max_duration_min'] == config.MAX_DURATION_MIN
    assert rules['min_duration_min'] == config.MIN_DURATION_MIN
    assert rules['checkin_timeout_min'] == config.CHECKIN_TIMEOUT_MIN
    assert str(config.MAX_DURATION_MIN) in r['reply']


def test_rules_cancel_topic(seeded):
    r = agents.ask('怎么取消预约', seeded['user_id'])
    assert r['intent'] == 'rules'
    assert r['data']['topic'] == 'cancel'
    assert '取消' in r['reply']


def test_find_seat_gives_reason(seeded):
    """PRODUCT §3：座位推荐必须给「为什么」。"""
    r = agents.ask('有没有靠窗的空位', seeded['user_id'])
    top = r['data']['seats'][0]
    assert top['reason']
    assert '靠窗' in top['reason']
    assert '空闲' in top['reason']


def test_recommend_gives_reason(seeded):
    """PRODUCT §3：接棒推荐必须给「为什么」，且理由里带审核状态。"""
    r = agents.ask('推荐点高数视频', seeded['user_id'])
    top = r['data']['contents'][0]
    assert top['reason']
    assert '人工帧级复核' in top['reason']
    assert '为什么推给你' in r['reply']


def test_recommend_empty_pool_does_not_fabricate(seeded):
    """池里没有就直接说没有，不硬凑一条假内容（PRODUCT §6）。"""
    db.execute("DELETE FROM contents WHERE status='approved'")
    r = agents.ask('推荐点高数视频', seeded['user_id'])
    assert r['intent'] == 'recommend_content'
    assert r['data']['contents'] == []
    assert '不硬凑' in r['reply']
    assert '《' not in r['reply']


def test_stuck_scopes_to_three_topics(seeded):
    """辅导只做 2–3 个主题，不做题库/通用聊天（PRODUCT §6）。"""
    r = agents.ask('我卡住了', seeded['user_id'])
    assert r['intent'] == 'stuck'
    assert 2 <= len(r['data']['tutor_topics']) <= 3
    assert set(r['data']['tutor_topics']) == {'高数极限', '英语时态', '编程递归'}


def test_ask_writes_agent_log(seeded):
    agents.ask('有空位吗', seeded['user_id'])
    row = db.one('SELECT * FROM agent_logs WHERE user_id=? ORDER BY id DESC LIMIT 1',
                 (seeded['user_id'],))
    assert row is not None
    assert row['intent'] == 'find_seat'
    assert row['input'] == '有空位吗'
    assert 'query_seats' in (row['tool_calls'] or '')
    assert row['created_at']


# ---------------------------------------------------------------- tutor

def test_tutor_two_rounds_then_done(seeded):
    tutor.reset_all()
    s = tutor.start('高数极限', seeded['user_id'], seeded['session_id'])
    assert s['tutor_id'] and s['step'] == 0
    assert s['question'] and s['options']
    assert s['topic'] == 'math_limit'

    a1 = tutor.answer(s['tutor_id'], '越来越小，但永远不为 0')
    assert a1['done'] is False
    assert a1['step'] == 1
    assert a1['explanation'] and a1['check_question'] and a1['question']
    assert a1['question'] != s['question']        # 每轮只问一个问题，且是新的

    a2 = tutor.answer(s['tutor_id'], '有，等于 1')
    assert a2['done'] is True
    assert a2['step'] == 2
    assert a2['question'] == ''
    assert a2['check_question']
    assert a2['resource'] is not None
    assert a2['resource']['id'] == seeded['content_id']   # 推荐的是 approved 内容

    # 收尾后再问，不会把状态搞乱
    a3 = tutor.answer(s['tutor_id'], '再问一句')
    assert a3['done'] is True


def test_tutor_admits_when_student_stuck(seeded):
    tutor.reset_all()
    s = tutor.start('编程递归', seeded['user_id'])
    a = tutor.answer(s['tutor_id'], '我不会，完全不知道')
    assert a['done'] is False
    assert a['step'] == 0                          # 不推进，不假装他会了
    assert '承认' in a['explanation']
    assert a['question'] and a['question'] != s['question']   # 换成更小的问法
    assert a['verdict'] == 'gave_up'


def test_tutor_partial_answer_still_advances(seeded):
    tutor.reset_all()
    s = tutor.start('英语时态', seeded['user_id'])
    a1 = tutor.answer(s['tutor_id'], '嗯……大概是过去发生的事吧')
    assert a1['done'] is False and a1['step'] == 1
    assert a1['verdict'] == 'partial'
    a2 = tutor.answer(s['tutor_id'], 'I have learned English for 3 years.')
    assert a2['done'] is True and a2['verdict'] == 'correct'


def test_tutor_empty_answer_repeats_question(seeded):
    tutor.reset_all()
    s = tutor.start('高数极限', seeded['user_id'])
    a = tutor.answer(s['tutor_id'], '   ')
    assert a['done'] is False and a['step'] == 0
    assert a['question'] == s['question']
    assert a['verdict'] == 'empty'


def test_tutor_expired_session(seeded):
    tutor.reset_all()
    a = tutor.answer('no-such-tutor', '随便说点')
    assert a['done'] is True
    assert a.get('error') == 'tutor_not_found'


def test_tutor_topics_and_alias(seeded):
    keys = {t['key'] for t in tutor.list_topics()}
    assert {'math_limit', 'english_tense', 'coding_recursion'} <= keys
    assert tutor.start('递归', seeded['user_id'])['topic'] == 'coding_recursion'
    assert tutor.start('完全陌生的主题', seeded['user_id'])['topic'] == 'general'


def test_tutor_resource_none_when_pool_empty(seeded):
    """编程递归没有对症的 approved 内容时，返回 None 而不是硬凑一条。"""
    tutor.reset_all()
    s = tutor.start('编程递归', seeded['user_id'])
    tutor.answer(s['tutor_id'], '终止条件，比如 n<=1 返回 1')
    a = tutor.answer(s['tutor_id'], '同一子问题被重复算了很多次')
    assert a['done'] is True
    assert a['resource'] is None
