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


def _protocol_config(dev):
    dev = dict(dev)
    seat = db.one('SELECT * FROM seats WHERE id=?', (dev['seat_id'],)) if dev.get('seat_id') else None
    if not seat:
        return {}
    return {
        'seat_id': int(seat['id']),
        'seat_code': seat['code'],
        'report_interval_ms': 5000,
        'ir_active_high': True,
    }


def register_protocol(device_id):
    """CodeArts/硬件沙盒 zhizuo-sensor 协议：开机注册。

    演示环境没有在后台手动绑定座位，首次注册自动绑定第一张空闲座位；
    真机/生产应改为管理员显式绑定，避免设备报错座位。
    """
    ensure_tables()
    if not device_id:
        raise ValueError('device_id 不能为空')
    dev = db.one('SELECT * FROM devices WHERE device_id=?', (device_id,))
    is_new = False
    if not dev:
        seat = db.one("SELECT * FROM seats WHERE status='free' ORDER BY id LIMIT 1")
        if not seat:
            seat = db.one('SELECT * FROM seats ORDER BY id LIMIT 1')
        seat_id = seat['id'] if seat else None
        db.execute('INSERT INTO devices(device_id,seat_id,sensor_type,last_seen,online,config) VALUES(?,?,?,?,1,?)',
                   (device_id, seat_id, 'ir', db.now(), ''))
        dev = db.one('SELECT * FROM devices WHERE device_id=?', (device_id,))
        is_new = True
    else:
        db.execute('UPDATE devices SET last_seen=?,online=1 WHERE device_id=?', (db.now(), device_id))
        dev = db.one('SELECT * FROM devices WHERE device_id=?', (device_id,))
    return {'registered': True, 'is_new': is_new, 'config': _protocol_config(dev)}


def protocol_config(device_id):
    ensure_tables()
    dev = db.one('SELECT * FROM devices WHERE device_id=?', (device_id,))
    if not dev:
        return {'registered': False, 'config': {}}
    db.execute('UPDATE devices SET last_seen=?,online=1 WHERE device_id=?', (db.now(), device_id))
    return {'registered': True, 'config': _protocol_config(dev)}


def protocol_report(device_id, seat_id=None, ir_front=0, ir_back=0):
    """zhizuo-sensor 上报：两块 PIR 都为 1 才算有人；连续 2 次无人释放。"""
    ensure_tables()
    dev = db.one('SELECT * FROM devices WHERE device_id=?', (device_id,))
    if not dev:
        if seat_id is None:
            raise ValueError('设备未注册')
        seat = db.one('SELECT * FROM seats WHERE id=?', (int(seat_id),))
        if not seat:
            raise ValueError('座位不存在')
        db.execute('INSERT INTO devices(device_id,seat_id,sensor_type,last_seen,online,config) VALUES(?,?,?,?,1,?)',
                   (device_id, int(seat_id), 'ir', db.now(), ''))
        dev = db.one('SELECT * FROM devices WHERE device_id=?', (device_id,))
    seat_id = dev['seat_id'] or (int(seat_id) if seat_id is not None else None)
    if not seat_id:
        raise ValueError('设备未绑定座位')
    front = 1 if int(ir_front or 0) else 0
    back = 1 if int(ir_back or 0) else 0
    occupied = bool(front and back)
    key = 'sensor_empty_%s' % seat_id
    empty = 0 if occupied else int(db.get_setting(key, '0') or 0) + 1
    db.set_setting(key, str(empty))
    if occupied or empty >= 2:
        report(device_id, None, occupied)
    status = 'occupied' if occupied else ('free' if empty >= 2 else 'pending_release')
    return {'seat_id': int(seat_id), 'status': status, 'consecutive_empty': empty}
