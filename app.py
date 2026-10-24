# -*- coding: utf-8 -*-
"""习得 · Web 应用入口。"""
import os
import threading
import time
import uuid
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   send_from_directory, session, url_for)

import db
import seed
from config import (AMAP_JS_KEY, AMAP_SECURITY_CODE, HOST, MAX_FRAMES, MEDIA_DIR, PORT, SECRET_KEY, UPLOAD_DIR)
from services import devices, flow, llm, navigation, outdoor, relay, seats

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

NAV = [
    ('home', '今日', '/', 'home'),
    ('seats', '空间', '/seats', 'seat'),
    ('nav', '导航', '/nav', 'pin'),
    ('learn', '学习', '/learn', 'book'),
    ('pool', '接力池', '/pool', 'play'),
    ('upload', '交棒', '/upload', 'upload'),
    ('review', '审核', '/review', 'shield'),
    ('workflow', '编排', '/workflow', 'flow'),
    ('ai', 'AI 设置', '/admin/ai', 'spark'),
    ('profile', '我的', '/profile', 'user'),
]

ROLE_NAV = {
    'student': ['home', 'seats', 'nav', 'learn', 'pool', 'upload', 'profile'],
    'teacher': ['home', 'seats', 'nav', 'learn', 'pool', 'upload', 'profile'],
    'reviewer': ['home', 'nav', 'review', 'pool', 'workflow', 'profile'],
    'admin': ['home', 'seats', 'nav', 'review', 'workflow', 'ai', 'pool', 'profile'],
}


def current_user():
    uid = session.get('uid')
    if not uid:
        return None
    r = db.one('SELECT * FROM users WHERE id=?', (uid,))
    return dict(r) if r else None


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user():
            if request.path.startswith('/api/'):
                return jsonify({'ok': False, 'error': '请先登录'}), 401
            return redirect(url_for('login_page', next=request.path))
        return fn(*a, **kw)
    return wrapper


def role_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            u = current_user()
            if not u:
                return jsonify({'ok': False, 'error': '请先登录'}), 401
            if u['role'] not in roles:
                return jsonify({'ok': False, 'error': '没有权限'}), 403
            return fn(*a, **kw)
        return wrapper
    return deco


def media_url(p):
    if not p:
        return ''
    s = str(p).replace('\\', '/')
    marker = '/media/'
    i = s.find(marker)
    if i >= 0:
        return '/media/' + s[i + len(marker):]
    if s.startswith('media/'):
        return '/' + s
    _up = os.path.abspath(UPLOAD_DIR).replace('\\', '/')
    if s.startswith(_up + '/'):
        return '/uploads/' + s[len(_up) + 1:]
    if not s.startswith('/') and not s.startswith('http'):
        return '/media/' + s.lstrip('/')
    return s


app.jinja_env.filters['media'] = media_url


@app.context_processor
def inject():
    u = current_user()
    allowed = ROLE_NAV.get(u['role'], ['home', 'profile']) if u else []
    nav = [x for x in NAV if x[0] in allowed]
    unread = 0
    if u:
        r = db.one('SELECT COUNT(*) c FROM messages WHERE user_id=? AND read=0', (u['id'],))
        unread = r['c'] if r else 0
    return {'user': u, 'nav_items': nav, 'unread': unread, 'now': db.now()}


# ---------------- pages ----------------

@app.route('/login')
def login_page():
    if current_user():
        return redirect(url_for('home'))
    return render_template('login.html')


@app.route('/')
@login_required
def home():
    return render_template('home.html', active='home')


@app.route('/seats')
@login_required
def seats_page():
    return render_template('seats.html', active='seats')


@app.route('/nav')
@login_required
def nav_page():
    return render_template('nav.html', active='seats')


@app.route('/learn')
@login_required
def learn_page():
    return render_template('learn.html', active='learn')


@app.route('/pool')
@login_required
def pool_page():
    return render_template('pool.html', active='pool')


@app.route('/upload')
@login_required
def upload_page():
    return render_template('upload.html', active='upload')


@app.route('/review')
@login_required
@role_required('reviewer', 'admin')
def review_page():
    return render_template('review.html', active='review')


@app.route('/review/<int:cid>')
@login_required
@role_required('reviewer', 'admin')
def review_detail_page(cid):
    return render_template('review_detail.html', active='review', content_id=cid)


@app.route('/workflow')
@login_required
def workflow_page():
    return render_template('workflow.html', active='workflow')


@app.route('/admin/ai')
@login_required
@role_required('admin')
def ai_settings_page():
    return render_template('ai_settings.html', active='ai', ai_status=llm.status())


@app.route('/profile')
@login_required
def profile_page():
    return render_template('profile.html', active='profile')


@app.route('/messages')
@login_required
def messages_page():
    return render_template('messages.html', active='profile')


# ---------------- health ----------------

@app.route('/api/health')
def api_health():
    return jsonify({'ok': True, 'service': 'xide'})


# ---------------- auth ----------------

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True) or request.form
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    r = db.one('SELECT * FROM users WHERE username=?', (username,))
    from werkzeug.security import check_password_hash
    if not r or not check_password_hash(r['password_hash'], password):
        return jsonify({'ok': False, 'error': '账号或密码错误'}), 401
    session['uid'] = r['id']
    session.permanent = True
    return jsonify({'ok': True, 'user': {'id': r['id'], 'name': r['name'], 'role': r['role']}})


@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'ok': True})


@app.route('/api/me')
def api_me():
    u = current_user()
    if not u:
        return jsonify({'ok': False}), 401
    return jsonify({'ok': True, 'user': u})


# ---------------- seats / booking ----------------

@app.route('/api/seats')
@login_required
def api_seats():
    u = current_user()
    fid = int(request.args.get('floor_id', 0) or 0)
    if not db.one('SELECT id FROM floors WHERE id=?', (fid,)):
        fr = db.one('SELECT id FROM floors ORDER BY id LIMIT 1')
        fid = fr['id'] if fr else 0
    rows = seats.seat_rows(fid, u['id'])
    occ = devices.device_occupied_map()
    for s in rows:
        if s.get('live_status') == 'free' and occ.get(s['id']):
            s['live_status'] = 'occupied'
    return jsonify({'ok': True, 'seats': rows})


@app.route('/api/floors')
@login_required
def api_floors():
    rows = db.query('SELECT f.*, (SELECT COUNT(*) FROM seats s WHERE s.floor_id=f.id) AS seat_count '
                    'FROM floors f ORDER BY f.building, f.floor_no')
    return jsonify({'ok': True, 'floors': [dict(x) for x in rows]})


@app.route('/api/bookings', methods=['POST'])
@login_required
def api_book():
    u = current_user()
    d = request.get_json(silent=True) or {}
    try:
        r = seats.book(u['id'], int(d['seat_id']), d.get('subject', ''), d.get('goal', ''),
                       d['start_at'], d['end_at'])
        return jsonify({'ok': True, 'reservation': r})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


@app.route('/api/bookings/<int:rid>/checkin', methods=['POST'])
@login_required
def api_checkin(rid):
    u = current_user()
    try:
        s = seats.checkin(u['id'], rid)
        return jsonify({'ok': True, 'session': s})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


@app.route('/api/bookings/<int:rid>/end', methods=['POST'])
@login_required
def api_end(rid):
    u = current_user()
    try:
        s = seats.end(u['id'], rid)
        return jsonify({'ok': True, 'session': s})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


@app.route('/api/sessions/current')
@login_required
def api_current_session():
    u = current_user()
    s = seats.current_session(u['id'])
    return jsonify({'ok': True, 'session': s})


@app.route('/api/my/reservations')
@login_required
def api_my_reservations():
    u = current_user()
    return jsonify({'ok': True, 'reservations': seats.my_reservations(u['id'])})


@app.route('/api/nav')
@login_required
def api_nav():
    seat_id = int(request.args.get('seat_id', 0))
    s = seats.seat_by_id(seat_id)
    if not s:
        return jsonify({'ok': False, 'error': '座位不存在'}), 404
    start = request.args.get('from', 'entry')
    r = navigation.plan_path(s['floor_id'], start, 's_%s' % s['code'])
    r['seat'] = s
    fl = db.one('SELECT * FROM floors WHERE id=?', (s['floor_id'],))
    r['floor'] = dict(fl) if fl else None
    return jsonify(r)


# ---------------- tutor / agent ----------------

@app.route('/api/tutor/start', methods=['POST'])
@login_required
def api_tutor_start():
    u = current_user()
    d = request.get_json(silent=True) or {}
    topic = d.get('topic', '高数极限')
    sess = seats.current_session(u['id'])
    if sess:
        old = sess.get('stuck_points') or ''
        db.execute('UPDATE study_sessions SET stuck_points=? WHERE id=?', ((old + ',' + topic).strip(','), sess['id']))
    try:
        from services import tutor
        return jsonify({'ok': True, **tutor.start(topic, u['id'])})
    except Exception as e:
        return jsonify({'ok': True, 'tutor_id': 'local', 'step': 1,
                        'question': '先不看定义：你觉得“无限逼近”和“到达”有什么区别？',
                        'options': ['逼近但不到', '就是到达', '说不清'],
                        'note': '规则兜底：%s' % e})


@app.route('/api/tutor/answer', methods=['POST'])
@login_required
def api_tutor_answer():
    d = request.get_json(silent=True) or {}
    try:
        from services import tutor
        return jsonify({'ok': True, **tutor.answer(d.get('tutor_id', 'local'), d.get('text', ''))})
    except Exception as e:
        return jsonify({'ok': True, 'done': True,
                        'explanation': '你抓住了“逼近但不到”这个关键。极限关心的是趋近过程，不是该点取值。',
                        'check_question': '那 x→2 时 f(x)=x² 会到 4 吗？',
                        'resource': None, 'note': '规则兜底：%s' % e})


@app.route('/api/agent/ask', methods=['POST'])
@login_required
def api_agent_ask():
    u = current_user()
    d = request.get_json(silent=True) or {}
    text = (d.get('text') or '').strip()
    sess = seats.current_session(u['id'])
    try:
        from services import agents
        out = agents.ask(text, u['id'], sess['id'] if sess else None)
        return jsonify({'ok': True, **out})
    except Exception as e:
        return jsonify({'ok': True, 'intent': 'unknown', 'agent': 'Router',
                        'reply': '我可以帮你找座、看当前场次、推荐学习视频，或者在你卡住时陪你拆问题。',
                        'suggestions': ['找个靠窗位置', '我现在学到哪了', '推荐一条高数视频'],
                        'tool_calls': [], 'note': '规则兜底：%s' % e})


# ---------------- contents / review ----------------

def _content_dict(r):
    d = dict(r)
    d['file_url'] = media_url(d.get('file_path'))
    d['cover_url'] = media_url(d.get('cover_path'))
    return d


@app.route('/api/contents')
@login_required
def api_contents():
    status = request.args.get('status', 'approved')
    subject = request.args.get('subject', '')
    sql = 'SELECT c.*, u.name AS owner_name FROM contents c LEFT JOIN users u ON u.id=c.owner_id WHERE 1=1'
    args = []
    if status:
        sql += ' AND c.status=?'
        args.append(status)
    if subject:
        sql += ' AND c.subject=?'
        args.append(subject)
    sql += ' ORDER BY c.id DESC'
    rows = db.query(sql, tuple(args))
    return jsonify({'ok': True, 'contents': [_content_dict(r) for r in rows]})


@app.route('/api/contents/<int:cid>')
@login_required
def api_content(cid):
    r = db.one('SELECT c.*, u.name AS owner_name FROM contents c LEFT JOIN users u ON u.id=c.owner_id WHERE c.id=?', (cid,))
    if not r:
        return jsonify({'ok': False, 'error': '内容不存在'}), 404
    d = _content_dict(r)
    frames = [dict(x) for x in db.query('SELECT * FROM content_frames WHERE content_id=? ORDER BY idx', (cid,))]
    for f in frames:
        f['url'] = media_url(f['path'])
    d['frames'] = frames
    return jsonify({'ok': True, 'content': d})


@app.route('/api/contents', methods=['POST'])
@login_required
def api_upload_content():
    u = current_user()
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'ok': False, 'error': '请选择视频文件'}), 400
    title = (request.form.get('title') or '').strip()
    if not title:
        return jsonify({'ok': False, 'error': '请填写标题'}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ('.mp4', '.mov', '.webm'):
        return jsonify({'ok': False, 'error': '仅支持 mp4 / mov / webm'}), 400
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    stored = os.path.join(UPLOAD_DIR, '%s%s' % (uuid.uuid4().hex[:12], ext))
    f.save(stored)
    cid = db.execute(
        'INSERT INTO contents(owner_id,title,subject,knowledge_point,description,source_type,file_path,cover_path,'
        'duration_sec,status,ai_summary,ai_risk,review_note,created_at) '
        "VALUES(?,?,?,?,?,?,?,?,0,'processing','',0,'',?)",
        (u['id'], title, request.form.get('subject', ''), request.form.get('knowledge_point', ''),
         request.form.get('description', ''), request.form.get('source_type', 'student'), stored, '', db.now()))
    run_id = flow.start('content', {'content_id': cid, 'title': title}, user_id=u['id'], title='交棒 · ' + title)
    flow.step(run_id, 'upload', '上传接收', lambda c: {'content_id': cid, 'title': title})
    try:
        from services import content as content_svc
        result = content_svc.process(cid)
    except Exception as e:
        result = _process_fallback(cid, stored)
        result['note'] = '规则兜底：%s' % e
    try:
        flow.step(run_id, 'frames', '关键帧抽取', lambda c: {'frames': result.get('frames', 0)})
        flow.step(run_id, 'prescreen', 'AI 初筛', lambda c: {'max_risk': result.get('max_risk', 0), 'suspicious': result.get('suspicious', 0)})
        db.set_setting('content_run_%d' % cid, run_id)
        flow.finish(run_id, 'waiting')
    except Exception:
        pass
    return jsonify({'ok': True, 'content_id': cid, 'result': result})


def _process_fallback(cid, video_path):
    """没有 content.py 时的兜底抽帧。"""
    try:
        frames, duration = seed._frames(cid, video_path)
    except Exception as e:
        db.execute("UPDATE contents SET status='pending_review',ai_summary=? WHERE id=?", ('抽帧失败：%s' % e, cid))
        return {'content_id': cid, 'frames': 0, 'status': 'pending_review', 'error': str(e)}
    max_risk = 0
    for fr in frames:
        max_risk = max(max_risk, fr['risk'])
        db.execute('INSERT INTO content_frames(content_id,idx,ts_sec,path,risk,labels,reasons,status) VALUES(?,?,?,?,?,?,?,?)',
                   (cid, fr['idx'], fr['ts'], fr['path'], fr['risk'], ','.join(fr['labels']),
                    '；'.join(fr['reasons']), 'pending'))
    cover = frames[0]['path'] if frames else ''
    db.execute("UPDATE contents SET status='pending_review',duration_sec=?,cover_path=?,ai_risk=?,ai_summary=? WHERE id=?",
               (duration, cover, max_risk, 'AI 初筛：%d 帧，最高风险 %.2f' % (len(frames), max_risk), cid))
    return {'content_id': cid, 'frames': len(frames), 'suspicious': int(max_risk >= 0.55),
            'duration_sec': duration, 'status': 'pending_review'}


@app.route('/api/review/queue')
@login_required
@role_required('reviewer', 'admin')
def api_review_queue():
    rows = db.query("SELECT c.*, u.name AS owner_name FROM contents c LEFT JOIN users u ON u.id=c.owner_id "
                    "WHERE c.status='pending_review' ORDER BY c.id DESC")
    return jsonify({'ok': True, 'contents': [_content_dict(r) for r in rows]})


@app.route('/api/review/<int:cid>')
@login_required
@role_required('reviewer', 'admin')
def api_review_detail(cid):
    r = db.one('SELECT c.*, u.name AS owner_name FROM contents c LEFT JOIN users u ON u.id=c.owner_id WHERE c.id=?', (cid,))
    if not r:
        return jsonify({'ok': False, 'error': '内容不存在'}), 404
    d = _content_dict(r)
    d['frames'] = []
    for x in db.query('SELECT * FROM content_frames WHERE content_id=? ORDER BY idx', (cid,)):
        f = dict(x)
        f['url'] = media_url(f['path'])
        f['labels'] = [z for z in (f.get('labels') or '').split(',') if z]
        d['frames'].append(f)
    d['reviews'] = [dict(x) for x in db.query('SELECT * FROM reviews WHERE content_id=? ORDER BY id DESC', (cid,))]
    return jsonify({'ok': True, 'content': d})


@app.route('/api/review/<int:cid>/decision', methods=['POST'])
@login_required
@role_required('reviewer', 'admin')
def api_review_decision(cid):
    u = current_user()
    d = request.get_json(silent=True) or {}
    decision = d.get('decision', 'approve')
    if decision not in ('approve', 'reject'):
        return jsonify({'ok': False, 'error': 'decision 必须是 approve 或 reject'}), 400
    checklist = d.get('checklist') or {}
    frame_status = d.get('frame_status') or {}
    for fid, st in frame_status.items():
        if st in ('cleared', 'flagged', 'pending'):
            db.execute('UPDATE content_frames SET status=? WHERE id=? AND content_id=?', (st, int(fid), cid))
    try:
        from services import content as content_svc
        out = content_svc.review(cid, u['id'], decision, d.get('note', ''), checklist, frame_status)
    except Exception:
        status = 'approved' if decision == 'approve' else 'rejected'
        reviewed = db.one("SELECT COUNT(*) c FROM content_frames WHERE content_id=? AND status IN ('cleared','flagged')", (cid,))['c']
        db.execute('UPDATE contents SET status=?,review_note=?,reviewer_id=?,reviewed_at=?,published_at=? WHERE id=?',
                   (status, d.get('note', ''), u['id'], db.now(), db.now() if status == 'approved' else None, cid))
        db.execute('INSERT INTO reviews(content_id,reviewer_id,decision,note,checklist,frames_reviewed,created_at) VALUES(?,?,?,?,?,?,?)',
                   (cid, u['id'], decision, d.get('note', ''), db.dumps(checklist), reviewed, db.now()))
        out = {'content_id': cid, 'status': status, 'frames_reviewed': reviewed}
    run_id = int(db.get_setting('content_run_%d' % cid, 0) or 0)
    if run_id:
        try:
            flow.step(run_id, 'human', '人工帧级复核', lambda c: {'decision': decision, 'note': d.get('note', '')})
            flow.step(run_id, 'publish', '入接力池', lambda c: {'status': out.get('status', '')})
            flow.finish(run_id, 'succeeded')
        except Exception:
            pass
    row = db.one('SELECT * FROM contents WHERE id=?', (cid,))
    return jsonify({'ok': True, 'content': _content_dict(row), 'result': out})


@app.route('/api/my/contents')
@login_required
def api_my_contents():
    u = current_user()
    rows = db.query('SELECT c.*, u.name AS owner_name FROM contents c LEFT JOIN users u ON u.id=c.owner_id WHERE c.owner_id=? ORDER BY c.id DESC', (u['id'],))
    return jsonify({'ok': True, 'contents': [_content_dict(r) for r in rows]})


# ---------------- relay ----------------

def _pushes_with_urls(user_id):
    pushes = relay.pending(user_id)
    for p in pushes:
        p['file_url'] = media_url(p.get('file_path'))
        p['cover_url'] = media_url(p.get('cover_path'))
    return pushes


@app.route('/api/relay/pending')
@login_required
def api_relay_pending():
    u = current_user()
    return jsonify({'ok': True, 'pushes': _pushes_with_urls(u['id'])})


@app.route('/api/relay/<int:pid>/open', methods=['POST'])
@login_required
def api_relay_open(pid):
    u = current_user()
    try:
        return jsonify({'ok': True, 'push': relay.open_push(pid, u['id'])})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


@app.route('/api/relay/<int:pid>/feedback', methods=['POST'])
@login_required
def api_relay_feedback(pid):
    u = current_user()
    d = request.get_json(silent=True) or {}
    try:
        return jsonify({'ok': True, **relay.feedback(pid, u['id'], d.get('value', 'helpful'))})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


# ---------------- messages ----------------

@app.route('/api/messages')
@login_required
def api_messages():
    u = current_user()
    rows = db.query('SELECT * FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 50', (u['id'],))
    return jsonify({'ok': True, 'messages': [dict(x) for x in rows]})


@app.route('/api/messages/read', methods=['POST'])
@login_required
def api_messages_read():
    u = current_user()
    d = request.get_json(silent=True) or {}
    if d.get('id'):
        db.execute('UPDATE messages SET read=1 WHERE id=? AND user_id=?', (int(d['id']), u['id']))
    else:
        db.execute('UPDATE messages SET read=1 WHERE user_id=?', (u['id'],))
    return jsonify({'ok': True})


@app.route('/api/profile')
@login_required
def api_profile():
    u = dict(current_user())
    u['avatar_url'] = media_url(u.get('avatar'))
    u['cover_url'] = media_url(u.get('cover'))
    sessions = [dict(x) for x in db.query(
        'SELECT ss.*, s.code AS seat_code, s.zone FROM study_sessions ss JOIN seats s ON s.id=ss.seat_id '
        'WHERE ss.user_id=? ORDER BY ss.id DESC LIMIT 50', (u['id'],))]
    contents = [_content_dict(x) for x in db.query(
        'SELECT c.*, u.name AS owner_name FROM contents c LEFT JOIN users u ON u.id=c.owner_id '
        'WHERE c.owner_id=? ORDER BY c.id DESC', (u['id'],))]
    pushes = _pushes_with_urls(u['id'])
    total_min = sum(int(x.get('duration_min') or 0) for x in sessions)
    helpful = sum(1 for x in pushes if x.get('feedback') == 'helpful')
    rate = round(helpful * 100 / len(pushes)) if pushes else 0
    return jsonify({'ok': True, 'user': u,
                    'stats': {'sessions': len(sessions), 'minutes': total_min,
                              'contents': len(contents), 'relays': len(pushes), 'helpful_rate': rate},
                    'sessions': sessions, 'contents': contents, 'pushes': pushes})


@app.route('/api/profile/update', methods=['POST'])
@login_required
def api_profile_update():
    u = current_user()
    d = request.get_json(silent=True) or {}
    name = (d.get('name') or u.get('name') or '').strip()
    if not name:
        return jsonify({'ok': False, 'error': '昵称不能为空'}), 400
    if len(name) > 40:
        return jsonify({'ok': False, 'error': '昵称最多 40 个字'}), 400
    db.execute('UPDATE users SET name=?, signature=?, college=?, interests=? WHERE id=?',
               (name, d.get('signature', u.get('signature', '')), d.get('college', u.get('college', '')),
                d.get('interests', u.get('interests', '')), u['id']))
    return jsonify({'ok': True})


@app.route('/api/profile/upload', methods=['POST'])
@login_required
def api_profile_upload():
    u = current_user()
    kind = (request.form.get('kind') or 'avatar').strip()
    if kind not in ('avatar', 'cover'):
        return jsonify({'ok': False, 'error': 'kind 必须是 avatar 或 cover'}), 400
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'ok': False, 'error': '请选择图片'}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.webp', '.gif'):
        return jsonify({'ok': False, 'error': '仅支持 jpg / png / webp / gif'}), 400
    if request.content_length and request.content_length > 8 * 1024 * 1024:
        return jsonify({'ok': False, 'error': '图片不能超过 8MB'}), 400
    folder = os.path.join(MEDIA_DIR, 'profiles')
    os.makedirs(folder, exist_ok=True)
    name = '%s_%s_%s%s' % (u['id'], kind, uuid.uuid4().hex[:8], ext)
    path = os.path.join(folder, name)
    f.save(path)
    try:
        from PIL import Image
        Image.open(path).verify()
    except Exception:
        try:
            os.remove(path)
        except Exception:
            pass
        return jsonify({'ok': False, 'error': '文件不是有效图片'}), 400
    rel = 'profiles/' + name
    col = 'avatar' if kind == 'avatar' else 'cover'
    db.execute('UPDATE users SET %s=? WHERE id=?' % col, (rel, u['id']))
    return jsonify({'ok': True, 'kind': kind, 'url': media_url(rel)})


@app.route('/outdoor')
@login_required
def outdoor_page():
    return render_template('outdoor.html', amap_key=AMAP_JS_KEY, amap_security=AMAP_SECURITY_CODE)


@app.route('/api/outdoor')
@login_required
def api_outdoor():
    name = (request.args.get('building') or '').strip()
    b = db.one('SELECT * FROM buildings WHERE name=?', (name,)) if name else None
    if not b:
        b = db.one('SELECT * FROM buildings ORDER BY id LIMIT 1')
    if not b:
        return jsonify({'ok': False, 'error': '还没有建筑数据，请先运行 seed'}), 404
    lat = request.args.get('lat', type=float)
    lng = request.args.get('lng', type=float)
    source = 'browser'
    if lat is None or lng is None:
        lat, lng, source = 38.3018, 116.8360, 'demo'
    info = outdoor.walk_route(lat, lng, dict(b))
    info.update({
        'ok': True,
        'buildings': [dict(x) for x in db.query('SELECT * FROM buildings ORDER BY id')],
        'start': {'lat': lat, 'lng': lng, 'source': source},
        'amap_configured': bool(AMAP_JS_KEY),
    })
    return jsonify(info)


@app.route('/api/admin/ai')
@login_required
@role_required('admin')
def api_admin_ai_status():
    return jsonify(llm.status())


@app.route('/api/admin/ai', methods=['POST'])
@login_required
@role_required('admin')
def api_admin_ai_save():
    d = request.get_json(silent=True) or {}
    try:
        return jsonify(llm.save_config(d.get('providers') or [], d.get('active_id') or ''))
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


@app.route('/api/admin/ai/test', methods=['POST'])
@login_required
@role_required('admin')
def api_admin_ai_test():
    d = request.get_json(silent=True) or {}
    return jsonify(llm.test_provider(d.get('provider')))


# ---------------- workflow / stats ----------------

@app.route('/api/workflow/defs')
@login_required
def api_flow_defs():
    return jsonify({'ok': True, 'flows': flow.flow_defs()})


@app.route('/api/workflow/runs')
@login_required
def api_flow_runs():
    return jsonify({'ok': True, 'runs': flow.list_runs(30)})


@app.route('/api/workflow/runs/<int:rid>')
@login_required
def api_flow_run(rid):
    r = flow.get_run(rid)
    if not r:
        return jsonify({'ok': False, 'error': '运行不存在'}), 404
    return jsonify({'ok': True, 'run': r})


@app.route('/api/stats')
@login_required
def api_stats():
    total = db.one('SELECT COUNT(*) c FROM seats')['c']
    fr = db.one('SELECT id FROM floors ORDER BY id LIMIT 1')
    free = 0
    for _f in db.query('SELECT id FROM floors'):
        free += sum(1 for _s in seats.seat_rows(_f['id']) if _s['live_status'] == 'free')
    pending = db.one("SELECT COUNT(*) c FROM contents WHERE status='pending_review'")['c']
    approved = db.one("SELECT COUNT(*) c FROM contents WHERE status='approved'")['c']
    today = datetime.now().strftime('%Y-%m-%d')
    sessions = db.one("SELECT COUNT(*) c FROM study_sessions WHERE created_at LIKE ?", (today + '%',))['c']
    pushes = db.one('SELECT COUNT(*) c FROM relay_pushes')['c']
    helpful = db.one("SELECT COUNT(*) c FROM relay_pushes WHERE feedback='helpful'")['c']
    rate = round(helpful * 100 / pushes) if pushes else 0
    return jsonify({'ok': True, 'stats': {
        'seats_total': total, 'seats_free': free, 'pending_review': pending,
        'contents_approved': approved, 'sessions_today': sessions, 'pushes': pushes,
        'helpful_rate': rate, 'ai_enabled': llm.available()}})


# ---------------- devices ----------------

@app.route('/api/devices/status')
@login_required
def api_devices_status():
    return jsonify({'ok': True, 'devices': devices.status(1)})


@app.route('/api/devices/simulate', methods=['POST'])
@login_required
@role_required('admin', 'reviewer')
def api_devices_simulate():
    d = request.get_json(silent=True) or {}
    try:
        return jsonify({'ok': True, **devices.simulate(d.get('seat_code'), bool(d.get('occupied')))})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


@app.route('/api/sensor/report', methods=['POST'])
def api_sensor_report():
    d = request.get_json(silent=True) or {}
    try:
        return jsonify({'ok': True, **devices.report(d.get('device_id'), d.get('seat_code'), bool(d.get('occupied')))})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


# ---------------- demo helpers ----------------

@app.route('/api/demo/expire', methods=['POST'])
@login_required
def api_demo_expire():
    """演示：把当前用户进行中的预约结束时间改到现在，触发自动结束 + 接棒。"""
    u = current_user()
    r = db.one("SELECT * FROM reservations WHERE user_id=? AND status IN ('booked','checked_in') ORDER BY id DESC LIMIT 1", (u['id'],))
    if not r:
        return jsonify({'ok': False, 'error': '没有进行中的预约'}), 400
    now = db.now()
    db.execute('UPDATE reservations SET end_at=? WHERE id=?', (now, r['id']))
    done = seats.sweep_expired()
    db.execute('UPDATE messages SET read=1 WHERE user_id=?', (u['id'],))
    return jsonify({'ok': True, 'done': done})


@app.route('/demo-login/<name>')
def demo_login(name):
    if not os.environ.get('ZX_DEMO_LOGIN'):
        abort(404)
    r = db.one('SELECT * FROM users WHERE username=?', (name,))
    if not r:
        abort(404)
    session['uid'] = r['id']
    nxt = request.args.get('next') or '/'
    if not nxt.startswith('/'):
        nxt = '/'
    return redirect(nxt)


@app.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename, conditional=True)


@app.route('/media/<path:filename>')
def media(filename):
    return send_from_directory(MEDIA_DIR, filename)


@app.errorhandler(413)
def too_large(e):
    return jsonify({'ok': False, 'error': '文件过大（上限 500MB）'}), 413


_SWEEPER_STARTED = False


def start_sweeper():
    global _SWEEPER_STARTED
    if _SWEEPER_STARTED:
        return None
    _SWEEPER_STARTED = True

    def loop():
        while True:
            try:
                seats.sweep_expired()
            except Exception:
                pass
            time.sleep(10)
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t


if os.environ.get('ZX_ENABLE_SWEEPER') == '1':
    start_sweeper()


if __name__ == '__main__':
    if not db.one('SELECT COUNT(*) c FROM users')['c']:
        seed.seed(reset=True)
    start_sweeper()
    print('=' * 56)
    print(' 习得 · http://127.0.0.1:%d' % PORT)
    print(' 账号：student / reviewer / admin / teacher  密码：123456')
    print('=' * 56)
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
