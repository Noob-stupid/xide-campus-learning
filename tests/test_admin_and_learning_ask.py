# -*- coding: utf-8 -*-
"""管理员地图页与学习页“问小习”接口。"""
import pytest
from werkzeug.security import generate_password_hash

import app as app_module
import db
from services import devices


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 'test.db'))
    db.init_db()
    now = db.now()
    admin_id = db.execute(
        'INSERT INTO users(username,password_hash,name,role,college,avatar,cover,signature,interests,created_at) '
        'VALUES(?,?,?,?,?,?,?,?,?,?)',
        ('admin_t', generate_password_hash('x'), '管理员', 'admin', '', '', '', '', '', now))
    student_id = db.execute(
        'INSERT INTO users(username,password_hash,name,role,college,avatar,cover,signature,interests,created_at) '
        'VALUES(?,?,?,?,?,?,?,?,?,?)',
        ('student_t', generate_password_hash('x'), '学生', 'student', '', '', '', '', '', now))
    fid = db.execute('INSERT INTO floors(name,building,floor_no,plan_w,plan_h) VALUES(?,?,?,?,?)',
                     ('2F', '图书馆', 2, 960, 620))
    db.execute('INSERT INTO seats(floor_id,code,zone,x,y,w,h,seat_type,features,status) VALUES(?,?,?,?,?,?,?,?,?,?)',
               (fid, 'A-01', '靠窗区', 100, 100, 30, 24, 'window', 'window,power', 'free'))
    db.execute(
        'INSERT INTO contents(owner_id,title,subject,knowledge_point,description,source_type,file_path,cover_path,'
        'duration_sec,status,ai_summary,ai_risk,review_note,reviewer_id,reviewed_at,published_at,views,helpful,unhelpful,created_at) '
        'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (student_id, '极限的直觉', '高等数学', '极限,ε-δ', '演示', 'teacher', 'media/content_1/video.mp4',
         'media/content_1/frames/f_01.jpg', 180, 'approved', '', 0.1, '', admin_id, now, now, 0, 0, 0, now))
    app_module.app.config['TESTING'] = True
    c = app_module.app.test_client()
    with c.session_transaction() as s:
        s['uid'] = student_id
    return c, admin_id, student_id


def test_maps_page_is_admin_only(client):
    c, admin_id, _ = client
    with c.session_transaction() as s:
        s['uid'] = admin_id
    r = c.get('/admin/maps')
    assert r.status_code == 200
    assert 'floorList' in r.get_data(as_text=True)


def test_learning_ask_answers_then_recommends(client):
    c, _, _ = client
    r = c.post('/api/learning/ask', json={'text': '我还是不懂极限，左右极限相等才存在吗？'})
    assert r.status_code == 200
    data = r.get_json()
    assert data['ok'] is True
    assert '极限' in data['answer']
    assert data['check_question']
    assert len(data['contents']) >= 1
    assert data['contents'][0]['file_url']


def test_sensor_protocol_releases_after_two_empty_reports(client):
    _, _, _ = client
    first = devices.protocol_report('dev-test', 1, 1, 1)
    assert first['status'] == 'occupied'
    pending = devices.protocol_report('dev-test', 1, 0, 0)
    assert pending['status'] == 'pending_release'
    free = devices.protocol_report('dev-test', 1, 0, 0)
    assert free['status'] == 'free'
