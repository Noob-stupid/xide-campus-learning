# -*- coding: utf-8 -*-
"""座位、预约、签到、结束、到期扫描。"""
import threading
from datetime import datetime

import db
from . import flow

_BOOK_LOCK = threading.RLock()


def _seat_dict(row):
    d = dict(row)
    d['features'] = [x for x in (d.get('features') or '').split(',') if x]
    return d


def seat_rows(floor_id=1, user_id=None):
    now = db.now()
    seats = [_seat_dict(r) for r in db.query('SELECT * FROM seats WHERE floor_id=? ORDER BY code', (floor_id,))]
    active = db.query(
        "SELECT r.*, u.name AS user_name FROM reservations r LEFT JOIN users u ON u.id=r.user_id "
        "WHERE r.status IN ('booked','checked_in') ORDER BY r.id DESC")
    by_seat = {}
    for r in active:
        by_seat.setdefault(r['seat_id'], []).append(dict(r))
    for s in seats:
        s['live_status'] = 'free'
        s['reservation'] = None
        if s['status'] == 'maintenance':
            s['live_status'] = 'maintenance'
            continue
        for r in by_seat.get(s['id'], []):
            if r['status'] == 'checked_in':
                s['live_status'] = 'using'
                s['reservation'] = r
                break
            if r['start_at'] <= now <= r['end_at']:
                s['live_status'] = 'booked'
                s['reservation'] = r
                break
        if s['reservation'] and user_id and s['reservation']['user_id'] == user_id:
            s['mine'] = True
    return seats


def seat_by_id(seat_id):
    r = db.one('SELECT * FROM seats WHERE id=?', (seat_id,))
    return _seat_dict(r) if r else None


def _overlap(conn, seat_id, start_at, end_at):
    row = conn.execute(
        "SELECT id FROM reservations WHERE seat_id=? AND status IN ('booked','checked_in') "
        "AND start_at < ? AND end_at > ? LIMIT 1",
        (seat_id, end_at, start_at)).fetchone()
    return row is not None


def book(user_id, seat_id, subject, goal, start_at, end_at):
    seat = seat_by_id(seat_id)
    if not seat:
        raise ValueError('座位不存在')
    if seat['status'] == 'maintenance':
        raise ValueError('该座位维护中')
    try:
        st = db.parse(start_at)
        et = db.parse(end_at)
    except Exception:
        raise ValueError('时间格式应为 YYYY-MM-DD HH:MM:SS')
    minutes = int((et - st).total_seconds() // 60)
    if minutes < 1:
        raise ValueError('预约时长至少 1 分钟')
    if minutes > 240:
        raise ValueError('单次预约最多 4 小时')
    if et <= datetime.now():
        raise ValueError('结束时间必须晚于现在')

    with _BOOK_LOCK:
        conn = db.connect()
        try:
            conn.execute('BEGIN IMMEDIATE')
            mine = conn.execute(
                "SELECT COUNT(*) c FROM reservations WHERE user_id=? AND status IN ('booked','checked_in')",
                (user_id,)).fetchone()['c']
            if mine >= 1:
                raise ValueError('你已有一条进行中的预约，请先结束或取消')
            if _overlap(conn, seat_id, start_at, end_at):
                raise ValueError('该时段已被预约，请换一个座位或时段')
            cur = conn.execute(
                'INSERT INTO reservations(user_id,seat_id,subject,goal,start_at,end_at,status,source,created_at) '
                "VALUES(?,?,?,?,?,?,'booked','web',?)",
                (user_id, seat_id, subject or '自主学习', goal or '', start_at, end_at, db.now()))
            res_id = cur.lastrowid
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    run_id = flow.start('booking', {'reservation_id': res_id, 'seat_id': seat_id,
                                    'seat_code': seat['code'], 'subject': subject},
                        user_id=user_id, title='预约 %s · %s' % (seat['code'], subject or '自主学习'))
    try:
        flow.step(run_id, 'intent', '意图与约束', lambda c: {'intent': 'book_seat', 'constraints': {'start': start_at, 'end': end_at}})
        flow.step(run_id, 'match', '座位匹配', lambda c: {'match': {'seat_code': seat['code'], 'reason': '符合你的筛选条件'}})
        flow.step(run_id, 'lock', 'Redis 锁座', lambda c: {'lock': {'token': 'local-%s' % res_id, 'ttl': 30}})
        flow.step(run_id, 'persist', 'RDS 落库', lambda c: {'reservation_id': res_id})
        flow.step(run_id, 'nav', '生成导航', lambda c: {'nav': {'from': 'entry', 'to': 's_%s' % seat['code']}})
        flow.step(run_id, 'notify', '预约通知', lambda c: _notify_book(user_id, res_id, seat['code'], start_at))
        flow.finish(run_id, 'succeeded')
    except Exception:
        pass
    return get_reservation(res_id)


def _notify_book(user_id, res_id, seat_code, start_at):
    db.execute('INSERT INTO messages(user_id,kind,title,body,payload,read,created_at) VALUES(?,?,?,?,?,0,?)',
               (user_id, 'booking', '预约成功',
                '你已预约 %s，开始时间 %s。到场后点“签到”。' % (seat_code, start_at),
                db.dumps({'reservation_id': res_id}), db.now()))
    return {'message': '预约成功'}


def get_reservation(res_id):
    r = db.one('SELECT r.*, s.code AS seat_code, s.zone, s.x, s.y, u.name AS user_name '
               'FROM reservations r JOIN seats s ON s.id=r.seat_id LEFT JOIN users u ON u.id=r.user_id '
               'WHERE r.id=?', (res_id,))
    return dict(r) if r else None


def checkin(user_id, reservation_id):
    r = db.one('SELECT * FROM reservations WHERE id=? AND user_id=?', (reservation_id, user_id))
    if not r:
        raise ValueError('预约不存在')
    if r['status'] != 'booked':
        raise ValueError('当前状态不能签到（%s）' % r['status'])
    now = db.now()
    db.execute("UPDATE reservations SET status='checked_in', checkin_at=? WHERE id=?", (now, reservation_id))
    sid = db.execute(
        'INSERT INTO study_sessions(reservation_id,user_id,seat_id,subject,started_at,status,created_at) '
        "VALUES(?,?,?,?,?,'active',?)",
        (reservation_id, user_id, r['seat_id'], r['subject'], now, now))
    run_id = flow.start('study', {'session_id': sid, 'reservation_id': reservation_id, 'subject': r['subject']},
                        user_id=user_id, title='学习 %s' % (r['subject'] or ''))
    try:
        flow.step(run_id, 'checkin', '签到开场', lambda c: {'checkin_at': now})
        flow.step(run_id, 'plan', '学习计划', lambda c: {'plan': '50 分钟专注 + 10 分钟休息'})
        flow.step(run_id, 'focus', '专注计时', lambda c: {'timer': 'started'})
        flow.finish(run_id, 'succeeded')
    except Exception:
        pass
    return get_session(sid)


def get_session(session_id):
    r = db.one('SELECT ss.*, s.code AS seat_code, u.name AS user_name FROM study_sessions ss '
               'JOIN seats s ON s.id=ss.seat_id LEFT JOIN users u ON u.id=ss.user_id WHERE ss.id=?', (session_id,))
    return dict(r) if r else None


def current_session(user_id):
    r = db.one("SELECT ss.*, s.code AS seat_code, s.zone FROM study_sessions ss JOIN seats s ON s.id=ss.seat_id "
               "WHERE ss.user_id=? AND ss.status='active' ORDER BY ss.id DESC LIMIT 1", (user_id,))
    return dict(r) if r else None


def my_reservations(user_id, limit=20):
    rows = db.query('SELECT r.*, s.code AS seat_code, s.zone FROM reservations r JOIN seats s ON s.id=r.seat_id '
                    'WHERE r.user_id=? ORDER BY r.id DESC LIMIT ?', (user_id, limit))
    return [dict(x) for x in rows]


def end(user_id, reservation_id, reason='manual'):
    r = db.one('SELECT * FROM reservations WHERE id=? AND user_id=?', (reservation_id, user_id))
    if not r:
        raise ValueError('预约不存在')
    if r['status'] not in ('booked', 'checked_in'):
        raise ValueError('当前状态不能结束')
    return _end_reservation(reservation_id, reason)


def _end_reservation(reservation_id, reason='manual'):
    r = db.one('SELECT * FROM reservations WHERE id=?', (reservation_id,))
    if not r or r['status'] not in ('booked', 'checked_in'):
        return None
    now = db.now()
    db.execute("UPDATE reservations SET status='completed', checkout_at=? WHERE id=?", (now, reservation_id))
    sess = db.one('SELECT * FROM study_sessions WHERE reservation_id=? ORDER BY id DESC LIMIT 1', (reservation_id,))
    session_id = sess['id'] if sess else None
    if sess:
        dur = max(1, db.minutes_between(sess['started_at'], now))
        db.execute("UPDATE study_sessions SET ended_at=?, duration_min=?, status='ended' WHERE id=?",
                   (now, dur, sess['id']))
    else:
        session_id = db.execute(
            'INSERT INTO study_sessions(reservation_id,user_id,seat_id,subject,started_at,ended_at,duration_min,status,created_at) '
            "VALUES(?,?,?,?,?,?,0,'ended',?)",
            (reservation_id, r['user_id'], r['seat_id'], r['subject'], r['start_at'], now, now))
    if reason == 'auto':
        db.execute('INSERT INTO messages(user_id,kind,title,body,payload,read,created_at) VALUES(?,?,?,?,?,0,?)',
                   (r['user_id'], 'session', '学习时间到', '预约时间已到，系统已自动结束本场学习，正在为你匹配学习视频。',
                    db.dumps({'reservation_id': reservation_id}), db.now()))
    try:
        from . import relay
        relay.trigger(session_id, trigger='auto' if reason == 'auto' else 'manual')
    except Exception:
        pass
    return get_session(session_id)


def sweep_expired():
    now = db.now()
    done = []
    rows = db.query("SELECT * FROM reservations WHERE status='checked_in' AND end_at <= ?", (now,))
    for r in rows:
        try:
            s = _end_reservation(r['id'], 'auto')
            done.append({'reservation_id': r['id'], 'action': 'auto_end', 'session': s})
        except Exception as e:
            done.append({'reservation_id': r['id'], 'action': 'error', 'error': str(e)})
    rows = db.query("SELECT * FROM reservations WHERE status='booked' AND end_at <= ?", (now,))
    for r in rows:
        db.execute("UPDATE reservations SET status='no_show' WHERE id=?", (r['id'],))
        done.append({'reservation_id': r['id'], 'action': 'no_show'})
    return done
