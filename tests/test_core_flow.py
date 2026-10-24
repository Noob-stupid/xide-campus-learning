# -*- coding: utf-8 -*-
"""主链路回归：导航、抢座、签到结束、到期、接棒幂等、智能体契约。"""
from datetime import datetime, timedelta

import pytest
from werkzeug.security import generate_password_hash

import db
from services import agents, navigation, relay, seats, tutor


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 'test.db'))
    db.init_db()
    now = db.now()
    for name, role in [('s1', 'student'), ('s2', 'student'), ('r1', 'reviewer')]:
        db.execute('INSERT INTO users(username,password_hash,name,role,college,avatar,cover,signature,interests,created_at) '
                   'VALUES(?,?,?,?,?,?,?,?,?,?)',
                   (name, generate_password_hash('x'), name, role, '', '', '', '', '', now))
    fid = db.execute('INSERT INTO floors(name,building,floor_no,plan_w,plan_h) VALUES(?,?,?,?,?)',
                     ('2F', '图书馆', 2, 960, 620))
    sid = db.execute('INSERT INTO seats(floor_id,code,zone,x,y,w,h,seat_type,features,status) VALUES(?,?,?,?,?,?,?,?,?,?)',
                     (fid, 'A-01', '靠窗区', 100, 100, 30, 24, 'window', 'window,power', 'free'))
    sid2 = db.execute('INSERT INTO seats(floor_id,code,zone,x,y,w,h,seat_type,features,status) VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (fid, 'A-02', '靠窗区', 162, 100, 30, 24, 'window', 'window', 'free'))
    # nav: entry -> mid -> seat
    for code, x, y, kind in [('entry', 480, 600, 'entrance'), ('mid', 480, 300, 'corridor'), ('s_A-01', 100, 100, 'seat')]:
        db.execute('INSERT INTO nav_nodes(floor_id,code,x,y,kind) VALUES(?,?,?,?,?)', (fid, code, x, y, kind))
    for a, b in [('entry', 'mid'), ('mid', 's_A-01')]:
        na = db.one('SELECT * FROM nav_nodes WHERE code=?', (a,))
        nb = db.one('SELECT * FROM nav_nodes WHERE code=?', (b,))
        dist = ((na['x'] - nb['x']) ** 2 + (na['y'] - nb['y']) ** 2) ** 0.5
        db.execute('INSERT INTO nav_edges(floor_id,from_node,to_node,distance) VALUES(?,?,?,?)', (fid, a, b, dist))
    cid = db.execute(
        'INSERT INTO contents(owner_id,title,subject,knowledge_point,description,source_type,file_path,cover_path,'
        'duration_sec,status,ai_summary,ai_risk,review_note,reviewer_id,reviewed_at,published_at,views,helpful,unhelpful,created_at) '
        'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (1, '极限的直觉', '高等数学', '极限,ε-δ', '演示', 'teacher', 'x.mp4', 'x.jpg', 180,
         'approved', '初筛通过', 0.1, '', 3, now, now, 0, 0, 0, now))
    return {'fid': fid, 'sid': sid, 'sid2': sid2, 'cid': cid}


def _window(minutes=60, checked_in=False):
    start = datetime.now() - timedelta(minutes=5)
    end = start + timedelta(minutes=minutes)
    return start.strftime('%Y-%m-%d %H:%M:%S'), end.strftime('%Y-%m-%d %H:%M:%S')


def test_navigation_path(env):
    r = navigation.plan_path(env['fid'], 'entry', 's_A-01')
    assert r['ok'] is True
    assert [p['code'] for p in r['path']] == ['entry', 'mid', 's_A-01']
    assert r['minutes'] >= 1


def test_booking_conflict_prevents_oversell(env):
    start, end = _window(60)
    r = seats.book(1, env['sid'], '高等数学', '复习', start, end)
    assert r['status'] == 'booked'
    with pytest.raises(ValueError):
        seats.book(2, env['sid'], '高等数学', '复习', start, end)
    assert db.one('SELECT COUNT(*) c FROM reservations')['c'] == 1


def test_checkin_end_triggers_relay(env):
    start, end = _window(60)
    r = seats.book(1, env['sid'], '高等数学', '复习极限', start, end)
    sess = seats.checkin(1, r['id'])
    assert sess['status'] == 'active'
    out = seats.end(1, r['id'])
    assert out['status'] == 'relayed'
    pushes = db.query('SELECT * FROM relay_pushes WHERE session_id=?', (sess['id'],))
    assert len(pushes) == 1
    assert pushes[0]['content_id'] == env['cid']
    assert '主题匹配' in pushes[0]['reason']


def test_auto_expiry_triggers_relay_and_is_idempotent(env):
    start, end = _window(60)
    r = seats.book(1, env['sid'], '高等数学', '复习', start, end)
    sess = seats.checkin(1, r['id'])
    # 把结束时间改到过去，模拟预约到期
    db.execute('UPDATE reservations SET end_at=? WHERE id=?', (db.now(), r['id']))
    done = seats.sweep_expired()
    assert any(x['action'] == 'auto_end' for x in done)
    assert db.one('SELECT status FROM reservations WHERE id=?', (r['id'],))['status'] == 'completed'
    first = db.one('SELECT COUNT(*) c FROM relay_pushes WHERE session_id=?', (sess['id'],))['c']
    assert first == 1
    # 再次触发必须幂等
    out = relay.trigger(sess['id'])
    assert out.get('idempotent') is True
    assert db.one('SELECT COUNT(*) c FROM relay_pushes WHERE session_id=?', (sess['id'],))['c'] == 1


def test_relay_trigger_claims_session_atomically(env):
    start, end = _window(60)
    r = seats.book(1, env['sid'], '高等数学', '复习', start, end)
    sess = seats.checkin(1, r['id'])
    # 模拟另一个线程已抢占（status='relaying'）但尚未写入 relay_pushes
    db.execute("UPDATE study_sessions SET status='relaying' WHERE id=?", (sess['id'],))
    with pytest.raises(ValueError):
        relay.trigger(sess['id'])
    assert db.one('SELECT COUNT(*) c FROM relay_pushes WHERE session_id=?', (sess['id'],))['c'] == 0
    # 抢占方失败回滚后，场次回到 ended，可再次正常推送且只推一次
    db.execute("UPDATE study_sessions SET status='ended' WHERE id=?", (sess['id'],))
    out = relay.trigger(sess['id'])
    assert out['ok'] is True
    assert db.one('SELECT COUNT(*) c FROM relay_pushes WHERE session_id=?', (sess['id'],))['c'] == 1
    assert db.one('SELECT status FROM study_sessions WHERE id=?', (sess['id'],))['status'] == 'relayed'


def test_agent_contract(env):
    out = agents.ask('找个靠窗安静的位置学高数', 1)
    for key in ('intent', 'reply', 'slots', 'data', 'suggestions', 'tool_calls', 'agent'):
        assert key in out
    assert out['intent'] == 'find_seat'
    assert out['data'].get('seats')


def test_tutor_two_rounds(env):
    first = tutor.start('高数极限', 1)
    assert first['question']
    second = tutor.answer(first['tutor_id'], '逼近但不到')
    assert second.get('explanation')
    assert second.get('check_question') or second.get('done')
