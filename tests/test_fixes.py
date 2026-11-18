# -*- coding: utf-8 -*-
"""B1-B6 修复的回归测试。

覆盖：
- B1 智能体推荐座位排除实时占用（预约 + 设备）
- B2 接棒反馈幂等，计数不重复累加
- B3 签到时限（15 分钟）与到期扫描释放
- B4 预约时长下限/上限与 config 一致
- B5 未安装 opencv 时占位帧仍可生成
- B6 审核通过前可疑帧必须逐帧给出结论
"""
import os
from datetime import datetime, timedelta

import pytest

import config
import db
from services import agents, content, devices, relay, seats

FMT = '%Y-%m-%d %H:%M:%S'


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 'test.db'))
    monkeypatch.setattr(config, 'DATA_DIR', str(tmp_path))
    monkeypatch.setattr(config, 'MEDIA_DIR', str(tmp_path / 'media'))
    monkeypatch.setattr(config, 'UPLOAD_DIR', str(tmp_path / 'uploads'))
    os.makedirs(config.MEDIA_DIR, exist_ok=True)
    db.init_db()

    now = db.now()
    uid = db.execute(
        "INSERT INTO users(username,password_hash,name,role,college,created_at) "
        "VALUES('s1','x','学生甲','student','',?)", (now,))
    uid2 = db.execute(
        "INSERT INTO users(username,password_hash,name,role,college,created_at) "
        "VALUES('s2','x','学生乙','student','',?)", (now,))
    fid = db.execute(
        "INSERT INTO floors(name,building,floor_no,plan_w,plan_h) VALUES('2F','图书馆',2,960,620)")
    seat1 = db.execute(
        "INSERT INTO seats(floor_id,code,zone,x,y,w,h,seat_type,features,status) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (fid, 'A-01', '靠窗区', 100, 100, 30, 24, 'window', 'window', 'free'))
    seat2 = db.execute(
        "INSERT INTO seats(floor_id,code,zone,x,y,w,h,seat_type,features,status) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (fid, 'B-01', '普通区', 200, 100, 30, 24, 'normal', '', 'free'))
    return {'uid': uid, 'uid2': uid2, 'fid': fid, 'seat1': seat1, 'seat2': seat2}


def _book(env, user, seat, start, end):
    return seats.book(user, seat, '高等数学', '复习', start.strftime(FMT), end.strftime(FMT))


# ---------------------------------------------------------------- B1
def test_agents_exclude_reserved_seat(env):
    start = datetime.now() - timedelta(minutes=5)
    _book(env, env['uid2'], env['seat2'], start, start + timedelta(minutes=60))

    r = agents.ask('有空位吗', env['uid'])
    codes = {s['code'] for s in r['data']['seats']}
    assert 'A-01' in codes
    assert 'B-01' not in codes          # 已被别人预约，不能再当空位推荐
    assert r['data']['free_total'] == 1


# ---------------------------------------------------------------- B2
def test_feedback_is_idempotent(env):
    now = db.now()
    cid = db.execute(
        "INSERT INTO contents(owner_id,title,status,helpful,unhelpful,created_at) "
        "VALUES(?,?, 'approved',0,0,?)", (env['uid'], '极限视频', now))
    sess = db.execute(
        "INSERT INTO study_sessions(reservation_id,user_id,seat_id,subject,started_at,status,created_at) "
        "VALUES(0,?,?, '高等数学',?,'relayed',?)",
        (env['uid'], env['seat1'], now, now))
    pid = db.execute(
        "INSERT INTO relay_pushes(session_id,user_id,content_id,reason,created_at) "
        "VALUES(?,?,?,?,?)", (sess, env['uid'], cid, '主题匹配', now))

    relay.feedback(pid, env['uid'], 'helpful')
    relay.feedback(pid, env['uid'], 'helpful')       # 重复点击不应再 +1
    row = db.one('SELECT helpful, unhelpful FROM contents WHERE id=?', (cid,))
    assert (row['helpful'], row['unhelpful']) == (1, 0)

    relay.feedback(pid, env['uid'], 'unhelpful')     # 改主意：旧计数回退，新计数 +1
    row = db.one('SELECT helpful, unhelpful FROM contents WHERE id=?', (cid,))
    assert (row['helpful'], row['unhelpful']) == (0, 1)

    relay.feedback(pid, env['uid'], 'helpful')
    row = db.one('SELECT helpful, unhelpful FROM contents WHERE id=?', (cid,))
    assert (row['helpful'], row['unhelpful']) == (1, 0)


# ---------------------------------------------------------------- B3
def test_checkin_deadline_and_sweep(env):
    start = datetime.now() - timedelta(minutes=20)
    end = start + timedelta(minutes=60)
    r = _book(env, env['uid'], env['seat1'], start, end)

    with pytest.raises(ValueError):
        seats.checkin(env['uid'], r['id'])

    done = seats.sweep_expired()
    assert any(x.get('action') == 'no_show_checkin' for x in done)
    assert db.one('SELECT status FROM reservations WHERE id=?', (r['id'],))['status'] == 'no_show'


def test_checkin_within_deadline(env):
    start = datetime.now() - timedelta(minutes=5)
    r = _book(env, env['uid'], env['seat1'], start, start + timedelta(minutes=60))
    sess = seats.checkin(env['uid'], r['id'])
    assert sess['status'] == 'active'


# ---------------------------------------------------------------- B4
def test_booking_duration_bounds(env):
    start = datetime.now() + timedelta(minutes=1)

    with pytest.raises(ValueError):
        _book(env, env['uid'], env['seat1'], start, start + timedelta(minutes=20))
    with pytest.raises(ValueError):
        _book(env, env['uid'], env['seat1'], start, start + timedelta(minutes=300))

    r = _book(env, env['uid'], env['seat1'], start, start + timedelta(minutes=30))
    assert r['status'] == 'booked'


# ---------------------------------------------------------------- B5
def test_degrade_without_cv2(env, monkeypatch):
    cid = db.execute(
        "INSERT INTO contents(owner_id,title,file_path,status,created_at) "
        "VALUES(?,?,?,?,?)",
        (env['uid'], '无法解码的视频', os.path.join(config.MEDIA_DIR, 'missing.mp4'), 'processing', db.now()))

    monkeypatch.setattr(content, 'HAS_CV2', False)
    monkeypatch.setattr(content, 'cv2', None)

    res = content.process(cid)
    assert res['degraded'] is True
    assert res['frames'] == 1
    assert res['status'] == 'pending_review'

    frames = db.query('SELECT * FROM content_frames WHERE content_id=?', (cid,))
    assert len(frames) == 1
    assert os.path.exists(content._abs(frames[0]['path']))   # 占位帧必须真的生成


# ---------------------------------------------------------------- B6
def test_review_requires_frame_decisions(env):
    import app as app_module

    cid = db.execute(
        "INSERT INTO contents(owner_id,title,status,created_at) VALUES(?,?,?,?)",
        (env['uid'], '待审视频', 'pending_review', db.now()))
    frame_id = db.execute(
        "INSERT INTO content_frames(content_id,idx,ts_sec,path,risk,labels,reasons,status) "
        "VALUES(?,1,0,'x.jpg',0.9,'大面积红色','疑似重点标注','pending')", (cid,))
    reviewer = db.execute(
        "INSERT INTO users(username,password_hash,name,role,college,created_at) "
        "VALUES('rev','x','审核员','reviewer','',?)", (db.now(),))

    app_module.app.config['TESTING'] = True
    client = app_module.app.test_client()
    with client.session_transaction() as s:
        s['uid'] = reviewer

    denied = client.post('/api/review/%d/decision' % cid,
                         json={'decision': 'approve', 'checklist': {}})
    assert denied.status_code == 400
    assert '可疑帧' in denied.get_json()['error']

    ok = client.post('/api/review/%d/decision' % cid,
                     json={'decision': 'approve', 'checklist': {},
                           'frame_status': {str(frame_id): 'cleared'}})
    assert ok.status_code == 200
    assert ok.get_json()['content']['status'] == 'approved'


# ---------------------------------------------------------------- B9
def test_invalid_query_params_are_client_errors(env):
    import app as app_module

    app_module.app.config['TESTING'] = True
    client = app_module.app.test_client()
    with client.session_transaction() as s:
        s['uid'] = env['uid']

    ok = client.get('/api/seats?floor_id=abc')      # 回退到第一层，不应 500
    assert ok.status_code == 200
    assert ok.get_json()['ok'] is True

    missing = client.get('/api/nav?seat_id=abc')    # 座位不存在 → 404
    assert missing.status_code == 404


# ---------------------------------------------------------------- B11
def test_device_occupied_map_latest_and_floor(env):
    devices.ensure_tables()
    now = db.now()
    db.execute('INSERT INTO seat_events(seat_id,device_id,occupied,created_at) VALUES(?,?,?,?)',
               (env['seat1'], 'd1', 1, now))
    db.execute('INSERT INTO seat_events(seat_id,device_id,occupied,created_at) VALUES(?,?,?,?)',
               (env['seat1'], 'd1', 0, now))          # 同一座位后一次无人
    db.execute('INSERT INTO seat_events(seat_id,device_id,occupied,created_at) VALUES(?,?,?,?)',
               (env['seat2'], 'd2', 1, now))

    m = devices.device_occupied_map()
    assert m[env['seat1']] is False
    assert m[env['seat2']] is True

    fid2 = db.execute("INSERT INTO floors(name,building,floor_no) VALUES('3F','图书馆',3)")
    seat3 = db.execute(
        "INSERT INTO seats(floor_id,code,zone,x,y,status) VALUES(?,?,?,?,?,'free')",
        (fid2, 'C-01', '普通区', 10, 10))
    db.execute('INSERT INTO seat_events(seat_id,device_id,occupied,created_at) VALUES(?,?,?,?)',
               (seat3, 'd3', 1, now))

    assert seat3 not in devices.device_occupied_map(env['fid'])
    assert devices.device_occupied_map(fid2)[seat3] is True


# ---------------------------------------------------------------- B12
def test_fallback_match_breakdown_matches_score(env):
    db.execute(
        "INSERT INTO contents(owner_id,title,subject,knowledge_point,duration_sec,status,created_at) "
        "VALUES(?,?,?,?,?, 'approved', ?)",
        (env['uid'], '高数视频', '高等数学', '极限', 180, db.now()))

    out = relay._fallback_match({'subject': '高等数学', 'stuck_points': '极限'})
    assert out
    item = out[0]
    assert item['score'] == round(min(sum(item['breakdown'].values()), 1.0), 2)
    assert item['breakdown']['subject'] == 0.45
    assert item['breakdown']['stuck'] == 0.25
    assert item['breakdown']['duration'] == 0.15


# ---------------------------------------------------------------- B13
def test_end_unchecked_booking_is_cancelled(env):
    start = datetime.now() + timedelta(minutes=5)
    r = _book(env, env['uid'], env['seat1'], start, start + timedelta(minutes=60))

    assert seats.end(env['uid'], r['id']) is None
    assert db.one('SELECT status FROM reservations WHERE id=?', (r['id'],))['status'] == 'cancelled'
    assert db.one('SELECT COUNT(*) c FROM study_sessions WHERE reservation_id=?', (r['id'],))['c'] == 0
    assert db.one('SELECT COUNT(*) c FROM relay_pushes')['c'] == 0


# ---------------------------------------------------------------- B14
def test_stats_free_seats_account_for_devices(env):
    import app as app_module

    devices.ensure_tables()
    db.execute('INSERT INTO seat_events(seat_id,device_id,occupied,created_at) VALUES(?,?,?,?)',
               (env['seat1'], 'd1', 1, db.now()))

    app_module.app.config['TESTING'] = True
    client = app_module.app.test_client()
    with client.session_transaction() as s:
        s['uid'] = env['uid']

    r = client.get('/api/stats')
    assert r.status_code == 200
    stats = r.get_json()['stats']
    assert stats['seats_total'] == 2
    assert stats['seats_free'] == 1          # seat1 被设备判定有人


# ---------------------------------------------------------------- S1
def test_secret_key_is_not_hardcoded(env):
    assert config.SECRET_KEY
    assert config.SECRET_KEY != 'zhixue-space-demo-2026'


# ---------------------------------------------------------------- S2
def test_cross_site_post_is_rejected(env):
    import app as app_module

    app_module.app.config['TESTING'] = True
    client = app_module.app.test_client()

    evil = client.post('/api/auth/login', json={'username': 'x', 'password': 'y'},
                       headers={'Origin': 'https://evil.example'})
    assert evil.status_code == 403

    same = client.post('/api/auth/login', json={'username': 'x', 'password': 'y'},
                       headers={'Origin': 'http://localhost'})
    assert same.status_code == 401          # 同源放行，进入账号校验


# ---------------------------------------------------------------- S3
def test_media_requires_login_for_video(env):
    import app as app_module

    client = app_module.app.test_client()
    video = client.get('/media/demo.mp4')
    assert video.status_code == 401         # 视频需要登录

    image = client.get('/media/demo.jpg')
    assert image.status_code == 404         # 图片鉴权放行，文件不存在


# ---------------------------------------------------------------- S4
def test_demo_expire_limited_to_students(env):
    import app as app_module

    reviewer = db.execute(
        "INSERT INTO users(username,password_hash,name,role,college,created_at) "
        "VALUES('rev','x','审核员','reviewer','',?)", (db.now(),))
    app_module.app.config['TESTING'] = True
    client = app_module.app.test_client()
    with client.session_transaction() as s:
        s['uid'] = reviewer

    r = client.post('/api/demo/expire')
    assert r.status_code == 403


# ---------------------------------------------------------------- S5
def test_sensor_requires_token_when_configured(env, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, 'SENSOR_TOKEN', 'secret-token')
    client = app_module.app.test_client()

    denied = client.post('/api/sensor/device/register', json={'device_id': 'd1'})
    assert denied.status_code == 401

    ok = client.post('/api/sensor/device/register', json={'device_id': 'd1'},
                     headers={'X-Sensor-Token': 'secret-token'})
    assert ok.status_code == 200