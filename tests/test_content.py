# -*- coding: utf-8 -*-
"""services/content.py 的测试：抽帧 → 初筛 → 复核 → 入池匹配。

跑法（在项目根）：
    python -m pytest tests/test_content.py -q

数据库与媒体目录都指向临时目录，不会碰到 data/ 下的真实数据。
"""

import os
import shutil
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 必须在 import config / db 之前把数据目录指到临时目录
_TMP = tempfile.mkdtemp(prefix='zx_content_test_')
os.environ['ZX_DATA_DIR'] = _TMP

import config  # noqa: E402

config.DATA_DIR = _TMP
config.DB_PATH = os.path.join(_TMP, 'zhixue.db')
config.MEDIA_DIR = os.path.join(_TMP, 'media')
config.UPLOAD_DIR = os.path.join(_TMP, 'uploads')
for _d in (config.DATA_DIR, config.MEDIA_DIR, config.UPLOAD_DIR):
    os.makedirs(_d, exist_ok=True)

import db  # noqa: E402

db.DB_PATH = config.DB_PATH  # db.py 在 import 时绑定了 DB_PATH，这里覆盖掉

from services import content  # noqa: E402

pytest.importorskip('cv2')
pytest.importorskip('numpy')
pytest.importorskip('PIL')

from tools import make_demo_video  # noqa: E402


# ---------------------------------------------------------------- fixtures

@pytest.fixture(scope='session', autouse=True)
def _schema():
    db.init_db()
    yield
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(autouse=True)
def _clean_db(_schema):
    for table in ('content_frames', 'reviews', 'contents', 'relay_pushes', 'users'):
        db.execute('DELETE FROM %s' % table)
    db.execute("INSERT INTO users(id,username,password_hash,name,role,created_at) "
               "VALUES(1,'stu','x','花火','student',?)", (db.now(),))
    db.execute("INSERT INTO users(id,username,password_hash,name,role,created_at) "
               "VALUES(2,'rev','x','审核员','reviewer',?)", (db.now(),))


@pytest.fixture(scope='session')
def demo_video():
    """用 make_demo_video 生成 9 秒演示视频（含一张大面积红色重点页）。"""
    path = os.path.join(config.MEDIA_DIR, 'demo', 'demo_video.mp4')
    made = make_demo_video.make(path)
    assert os.path.exists(made) and os.path.getsize(made) > 1024
    return made


def _add_content(file_path, title='二次函数的图像与性质', subject='数学', knowledge_point='判别式'):
    return db.execute(
        'INSERT INTO contents(owner_id,title,subject,knowledge_point,description,file_path,source_type,status,created_at) '
        "VALUES(1,?,?,?,'学生交棒的教学短视频',?,'student','processing',?)",
        (title, subject, knowledge_point, file_path, db.now()))


def _frames(cid):
    return [dict(r) for r in db.query(
        'SELECT * FROM content_frames WHERE content_id=? ORDER BY idx', (cid,))]


# ---------------------------------------------------------------- process

def test_process_extracts_frames_and_updates_content(demo_video):
    cid = _add_content(demo_video)
    res = content.process(cid)

    assert res['content_id'] == cid
    assert res['frames'] > 0
    assert res['frames'] <= config.MAX_FRAMES
    assert res['status'] == 'pending_review'
    assert res['duration_sec'] > 7.0

    row = db.one('SELECT * FROM contents WHERE id=?', (cid,))
    assert row['status'] == 'pending_review'
    assert row['ai_summary']
    assert row['ai_risk'] > 0
    assert row['cover_path']

    frames = _frames(cid)
    assert len(frames) == res['frames']
    assert [f['idx'] for f in frames] == list(range(1, len(frames) + 1))
    for f in frames:
        assert os.path.exists(content._abs(f['path'])), f['path']
        assert isinstance(content.labels_of(f['labels']), list)
        assert isinstance(content.reasons_of(f['reasons']), list)
        assert f['status'] == 'pending'


def test_process_flags_the_red_slide_only(demo_video):
    cid = _add_content(demo_video)
    res = content.process(cid)
    frames = _frames(cid)

    risky = [f for f in frames if f['risk'] >= config.SUSPICIOUS_RISK]
    assert res['suspicious'] == 1
    assert res['frames_flagged'] == len(risky)
    assert 1 <= len(risky) <= 2, '演示视频里只有一张红色页'
    # 文字页不应被误判：其余帧的风险要明显低
    calm = [f['risk'] for f in frames if f['risk'] < config.SUSPICIOUS_RISK]
    assert calm and max(calm) < 0.2

    hit = risky[0]
    assert '大面积红色' in content.labels_of(hit['labels'])
    assert any('红色' in r for r in content.reasons_of(hit['reasons']))
    assert hit['risk'] > 0.55


def test_process_degrades_when_video_missing():
    cid = _add_content('D:/not/here/missing.mp4')
    res = content.process(cid)

    assert res['degraded'] is True
    assert res['frames'] == 1              # 一张占位说明帧
    assert res['status'] == 'pending_review'
    assert res['note']

    row = db.one('SELECT * FROM contents WHERE id=?', (cid,))
    assert row['status'] == 'pending_review'
    assert '抽帧' in row['ai_summary']

    frames = _frames(cid)
    assert len(frames) == 1
    assert '无法抽帧' in content.labels_of(frames[0]['labels'])
    assert os.path.exists(content._abs(frames[0]['path']))


def test_process_degrades_when_video_unreadable():
    bad = os.path.join(config.MEDIA_DIR, 'broken.mp4')
    with open(bad, 'wb') as fh:
        fh.write(b'this is definitely not a video' * 200)

    cid = _add_content(bad)
    res = content.process(cid)

    assert res['degraded'] is True
    assert res['status'] == 'pending_review'
    frames = _frames(cid)
    assert len(frames) == 1
    assert '无法抽帧' in content.labels_of(frames[0]['labels'])


def test_process_is_idempotent(demo_video):
    cid = _add_content(demo_video)
    content.process(cid)
    second = content.process(cid)
    assert len(_frames(cid)) == second['frames']


def test_process_rejects_unknown_content():
    with pytest.raises(ValueError):
        content.process(99999)


def test_pick_times_respects_max_frames():
    times = content._pick_times(600.0)
    assert 1 <= len(times) <= config.MAX_FRAMES
    assert times == sorted(times)
    assert times[0] == 0.0


# ---------------------------------------------------------------- review

def test_review_approve_sets_published_at(demo_video):
    cid = _add_content(demo_video)
    content.process(cid)
    total = len(_frames(cid))

    res = content.review(cid, 2, 'approve', note='抽帧清晰，红色页为重点标注',
                         checklist={'清晰': True, '合规': True},
                         frame_status={'2': 'flagged'})

    assert res['status'] == 'approved'
    assert res['frames_reviewed'] == total
    assert res['frames_flagged'] == 1

    row = db.one('SELECT * FROM contents WHERE id=?', (cid,))
    assert row['status'] == 'approved'
    assert row['published_at']
    assert row['reviewed_at']
    assert row['reviewer_id'] == 2
    assert row['review_note'].startswith('抽帧清晰')

    flagged = [f for f in _frames(cid) if f['status'] == 'flagged']
    assert len(flagged) == 1 and flagged[0]['idx'] == 2

    audit = db.one('SELECT * FROM reviews WHERE content_id=?', (cid,))
    assert audit['decision'] == 'approve'
    assert audit['frames_reviewed'] == total
    assert db.loads(audit['checklist'], {})['合规'] is True


def test_review_accepts_frame_id_keys(demo_video):
    """app.py 的路由按帧 id 传 frame_status，这里必须按 id 命中（而不是 idx）。"""
    cid = _add_content(demo_video)
    content.process(cid)
    target = _frames(cid)[-1]

    res = content.review(cid, 2, 'approve', frame_status={str(target['id']): 'flagged'})

    assert res['frames_flagged'] == 1
    flagged = [f for f in _frames(cid) if f['status'] == 'flagged']
    assert [f['idx'] for f in flagged] == [target['idx']]


def test_review_reject_keeps_content_out_of_pool(demo_video):
    cid = _add_content(demo_video)
    content.process(cid)

    res = content.review(cid, 2, 'reject', note='红色页疑似错误标注')

    assert res['status'] == 'rejected'
    row = db.one('SELECT * FROM contents WHERE id=?', (cid,))
    assert row['status'] == 'rejected'
    assert row['published_at'] is None
    assert content.match_for_session({'subject': '数学'}) == []


def test_review_rejects_bad_decision(demo_video):
    cid = _add_content(demo_video)
    content.process(cid)
    with pytest.raises(ValueError):
        content.review(cid, 2, 'maybe')


# ---------------------------------------------------------------- match

def _approve(video, title, subject='数学', kp='判别式'):
    cid = _add_content(video, title=title, subject=subject, knowledge_point=kp)
    content.process(cid)
    content.review(cid, 2, 'approve', note='ok')
    return cid


def test_match_only_returns_approved_with_readable_reason(demo_video):
    approved = _approve(demo_video, '二次函数·判别式')
    rejected_content = _add_content(demo_video, title='未过审的内容', subject='数学')
    content.process(rejected_content)
    content.review(rejected_content, 2, 'reject', note='不合规')
    _add_content(demo_video, title='还在队列里', subject='数学')  # 停在 processing

    hits = content.match_for_session({'subject': '数学', 'knowledge_point': '判别式',
                                      'stuck_points': '判别式符号总写错'}, limit=5)

    assert isinstance(hits, list)
    assert [h['id'] for h in hits] == [approved]
    item = hits[0]
    for key in ('id', 'title', 'subject', 'duration_sec', 'reason', 'score', 'breakdown',
                'cover_path', 'file_path', 'source_type'):
        assert key in item, key
    assert '主题匹配' in item['reason']
    assert '已通过人工复核' in item['reason']
    assert '分钟' in item['reason'] or '秒' in item['reason']
    assert 0 <= item['score'] <= 100
    assert set(item['breakdown']) >= {'subject', 'knowledge', 'duration', 'freshness'}
    assert item['cover_path'].startswith('media/')


def test_match_ranks_subject_hit_first_and_respects_limit(demo_video):
    math_id = _approve(demo_video, '二次函数·判别式', subject='数学', kp='判别式')
    _approve(demo_video, '英语听力训练', subject='英语', kp='听力')
    _approve(demo_video, '线性代数入门', subject='数学', kp='矩阵')

    hits = content.match_for_session({'subject': '数学', 'knowledge_point': '判别式'}, limit=5)
    assert hits[0]['id'] == math_id
    assert hits[0]['score'] >= hits[-1]['score']

    limited = content.match_for_session({'subject': '数学'}, limit=2)
    assert len(limited) == 2


def test_match_empty_when_nothing_approved():
    assert content.match_for_session({'subject': '数学'}) == []
    assert content.match_for_session({'subject': '数学'}, limit=0) == []


def test_match_reason_mentions_knowledge_point(demo_video):
    _approve(demo_video, '二次函数·判别式', subject='数学', kp='判别式')
    hit = content.match_for_session({'subject': '数学', 'knowledge_point': '判别式'})[0]
    assert '知识点' in hit['reason']


def test_feedback_score_neutral_and_extremes():
    assert content._feedback_score({'helpful': 0, 'unhelpful': 0}) == 0.5
    assert content._feedback_score({'helpful': 5, 'unhelpful': 0}) == 1.0
    assert content._feedback_score({'helpful': 0, 'unhelpful': 5}) == 0.0
    assert 0.5 < content._feedback_score({'helpful': 1, 'unhelpful': 0}) < 1.0
