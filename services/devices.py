# -*- coding: utf-8 -*-
"""空间感知层：ESP32 占位传感器接入 + 管理端模拟器。

原则：设备状态只补充“此刻有没有人”，不覆盖预约状态。
"""
import db


def ensure_tables():
    db.execute('''CREATE TABLE IF NOT EXISTS devices(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT UNIQUE NOT NULL,
        seat_id INTEGER,
        sensor_type TEXT DEFAULT 'ir',
        last_seen TEXT,
        online INTEGER DEFAULT 0,
        config TEXT DEFAULT ''
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS seat_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seat_id INTEGER,
        device_id TEXT,
        occupied INTEGER DEFAULT 0,
        created_at TEXT
    )''')


def register(device_id, seat_code, sensor_type='ir'):
    ensure_tables()
    seat = db.one('SELECT * FROM seats WHERE code=?', (seat_code,))
    if not seat:
        raise ValueError('座位不存在: %s' % seat_code)
    old = db.one('SELECT * FROM devices WHERE device_id=?', (device_id,))
    if old:
        db.execute('UPDATE devices SET seat_id=?,sensor_type=?,last_seen=?,online=1 WHERE device_id=?',
                   (seat['id'], sensor_type, db.now(), device_id))
    else:
        db.execute('INSERT INTO devices(device_id,seat_id,sensor_type,last_seen,online) VALUES(?,?,?,?,1)',
                   (device_id, seat['id'], sensor_type, db.now()))
    return {'ok': True, 'device_id': device_id, 'seat_code': seat_code}


def report(device_id, seat_code=None, occupied=False):
    ensure_tables()
    dev = db.one('SELECT * FROM devices WHERE device_id=?', (device_id,))
    if not dev and seat_code:
        register(device_id, seat_code)
        dev = db.one('SELECT * FROM devices WHERE device_id=?', (device_id,))
    if not dev:
        raise ValueError('设备未注册')
    seat_id = dev['seat_id']
    db.execute('UPDATE devices SET last_seen=?,online=1 WHERE device_id=?', (db.now(), device_id))
    db.execute('INSERT INTO seat_events(seat_id,device_id,occupied,created_at) VALUES(?,?,?,?)',
               (seat_id, device_id, 1 if occupied else 0, db.now()))
    return {'ok': True, 'seat_id': seat_id, 'occupied': bool(occupied)}


def simulate(seat_code, occupied):
    ensure_tables()
    seat = db.one('SELECT * FROM seats WHERE code=?', (seat_code,))
    if not seat:
        raise ValueError('座位不存在: %s' % seat_code)
    return report('SIM-%s' % seat_code, seat_code, occupied)


def status(floor_id=1):
    ensure_tables()
    rows = db.query('SELECT d.*, s.code AS seat_code, s.zone FROM devices d LEFT JOIN seats s ON s.id=d.seat_id '
                    'WHERE s.floor_id=?', (floor_id,))
    out = []
    for r in rows:
        d = dict(r)
        d['online'] = bool(d['online'])
        out.append(d)
    return out


def device_occupied_map(floor_id=1):
    ensure_tables()
    rows = db.query('SELECT seat_id, occupied, created_at FROM seat_events ORDER BY id DESC LIMIT 200')
    seen = {}
    for r in rows:
        if r['seat_id'] not in seen:
            seen[r['seat_id']] = bool(r['occupied'])
    return seen
