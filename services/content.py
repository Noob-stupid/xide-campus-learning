# -*- coding: utf-8 -*-
"""内容流水线：抽帧 → AI 初筛 → 人工帧级复核 → 入池匹配。

对外接口见 docs/CONTRACT.md 第 6 节：
    process(content_id) -> dict
    review(content_id, reviewer_id, decision, note='', checklist=None, frame_status=None) -> dict
    match_for_session(session, limit=5) -> list[dict]

设计约定：
- content_frames.labels 存逗号分隔纯文本、reasons 存中文分号分隔纯文本（与 app.py 的
  split(',') / 直出展示对齐，不存 JSON）。
- 路径入库统一存「相对 DATA_DIR 的 posix 路径」（如 media/content_3/frames/f_02.jpg），
  DATA_DIR 之外的绝对路径才原样存，便于换机器/换盘符。
- 没有 cv2（或视频打不开）不抛异常：写一张占位说明帧，status 仍为 pending_review。
- 阈值全部来自 config.py（MAX_FRAMES / FRAME_INTERVAL_SEC / SUSPICIOUS_RISK），不写死在业务里。
"""

import math
import os

import numpy as np

import config
import db

try:  # cv2 缺失时降级，不炸掉整个应用
    import cv2

    HAS_CV2 = True
except Exception:  # pragma: no cover - 环境相关
    cv2 = None
    HAS_CV2 = False


# ---------------------------------------------------------------- 小工具

def _clamp01(x):
    return max(0.0, min(1.0, float(x)))


def _rel(path):
    """把绝对路径转成相对 DATA_DIR 的 posix 路径（示范：media/content_1/frames/f_01.jpg）。"""
    if not path:
        return ''
    try:
        base = os.path.abspath(config.DATA_DIR)
        target = os.path.abspath(path)
        if target == base:
            return ''
        if target.startswith(base + os.sep):
            return os.path.relpath(target, base).replace(os.sep, '/')
        return target
    except Exception:
        return str(path)


def _abs(path):
    """_rel 的逆运算：把入库路径还原成本机绝对路径。"""
    if not path:
        return ''
    p = str(path).replace('/', os.sep)
    if os.path.isabs(p):
        return p
    return os.path.join(config.DATA_DIR, p)


def labels_of(raw):
    """content_frames.labels 存的是逗号分隔纯文本（与 app.py 的 split(',') 对齐）。"""
    return [x.strip() for x in str(raw or '').split(',') if x.strip()]


def reasons_of(raw):
    """content_frames.reasons 存的是中文分号分隔纯文本。"""
    return [x.strip() for x in str(raw or '').split('；') if x.strip()]


def _norm_text(s):
    """只保留中英文数字字符，去掉空格与所有标点（含中文全角标点）。"""
    return ''.join(ch for ch in str(s or '') if ch.isalnum()).lower()


def _bigrams(s):
    s = _norm_text(s)
    if not s:
        return set()
    if len(s) == 1:
        return {s}
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _cover_ratio(query, text):
    """query 的二元组有多少落在 text 里（0-1）。"""
    a, b = _bigrams(query), _bigrams(text)
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a))


def _write_jpeg(path, img):
    """cv2.imwrite 在中文路径下会静默失败，统一走 imencode + 二进制写。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ok, buf = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok:
        return False
    with open(path, 'wb') as fh:
        fh.write(buf.tobytes())
    return True


def _mmss(sec):
    sec = int(round(float(sec or 0)))
    return '%d:%02d' % (sec // 60, sec % 60)


def _duration_text(sec):
    sec = float(sec or 0)
    if sec < 90:
        return '短视频（%d 秒），适合碎片时间' % int(round(sec))
    return '%d 分钟适合课间' % int(round(sec / 60.0))


FONT_CANDIDATES = (
    'C:/Windows/Fonts/msyh.ttc',
    'C:/Windows/Fonts/simhei.ttf',
    'C:/Windows/Fonts/simsun.ttc',
    '/System/Library/Fonts/PingFang.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
)


def find_font(size):
    """找一个能显示中文的字体，找不到返回 None（调用方退到默认字体）。"""
    try:
        from PIL import ImageFont
    except Exception:
        return None
    for cand in FONT_CANDIDATES:
        if os.path.exists(cand):
            for index in (0, 1):
                try:
                    return ImageFont.truetype(cand, size, index=index)
                except Exception:
                    continue
    return None


def _placeholder_frame(out_dir, text):
    """降级时画一张说明图，避免审核页出现裂图。"""
    w, h = 640, 360
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new('RGB', (w, h), (245, 247, 250))
        draw = ImageDraw.Draw(img)
        font = find_font(20)
        if font is None:
            font = ImageFont.load_default()
        draw.rectangle([24, 24, w - 24, h - 24], outline=(201, 138, 46), width=3)
        draw.text((48, 150), text, fill=(15, 42, 74), font=font)
        arr = np.array(img)[:, :, ::-1].copy()
    except Exception:
        arr = np.full((h, w, 3), 235, np.uint8)
        cv2.putText(arr, 'NO FRAMES', (40, 180), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (60, 60, 60), 2)
    path = os.path.join(out_dir, 'f_00.jpg')
    _write_jpeg(path, arr)
    return path


# ---------------------------------------------------------------- 单帧初筛

def analyse_frame(frame):
    """一帧的亮度/对比度/模糊/红色占比/肤色占比/暗部占比 + 风险 0-1。"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    b = frame[:, :, 0].astype(np.float32)
    g = frame[:, :, 1].astype(np.float32)
    r = frame[:, :, 2].astype(np.float32)

    brightness = float(gray.mean()) / 255.0
    contrast = float(gray.std()) / 64.0
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    blur = _clamp01(1.0 - sharpness / 260.0)

    red_ratio = float(((r > 110) & (r > g * 1.35) & (r > b * 1.35)).mean())
    dark_ratio = float((gray < 45).mean())

    ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
    yy, cr, cb = ycrcb[:, :, 0], ycrcb[:, :, 1], ycrcb[:, :, 2]
    skin_ratio = float(((cr >= 133) & (cr <= 173) & (cb >= 77) & (cb <= 127) & (yy > 60)).mean())

    # 权重合计 1.0；红色单独就能到 SUSPICIOUS_RISK，是最高优先级线索
    parts = {
        # 大面积红色 = 重点标注/遮盖/血腥等，权重最高
        'red': 0.58 * _clamp01(red_ratio / 0.22),
        'skin': 0.16 * _clamp01((skin_ratio - 0.06) / 0.24),
        'dark': 0.10 * _clamp01((dark_ratio - 0.15) / 0.45),
        'blur': 0.09 * blur,
        'contrast': 0.04 * _clamp01((0.30 - contrast) / 0.30),
        'bright': 0.03 * _clamp01(abs(brightness - 0.55) / 0.45),
    }
    risk = _clamp01(sum(parts.values()))

    labels, reasons = [], []
    if red_ratio >= 0.12:
        labels.append('大面积红色')
        reasons.append('红色区域占画面 %.0f%%，疑似重点标注/遮盖' % (red_ratio * 100))
    if skin_ratio >= 0.20:
        labels.append('人物特写')
        reasons.append('肤色像素占 %.0f%%，人物占比偏高' % (skin_ratio * 100))
    if dark_ratio >= 0.35:
        labels.append('画面偏暗')
        reasons.append('暗部占 %.0f%%，可能影响观看' % (dark_ratio * 100))
    if blur >= 0.72:
        labels.append('画面模糊')
        reasons.append('清晰度偏低（Laplacian %.0f）' % sharpness)
    if contrast <= 0.12:
        labels.append('对比度低')
        reasons.append('明暗对比弱，疑似纯色/翻拍')
    if brightness >= 0.96:
        labels.append('过曝')
        reasons.append('平均亮度 %.0f%%，接近过曝' % (brightness * 100))
    elif brightness <= 0.10:
        labels.append('欠曝')
        reasons.append('平均亮度 %.0f%%，画面过黑' % (brightness * 100))

    return {
        'risk': round(risk, 4),
        'brightness': round(brightness, 4),
        'contrast': round(contrast, 4),
        'sharpness': round(sharpness, 2),
        'blur': round(blur, 4),
        'red_ratio': round(red_ratio, 4),
        'skin_ratio': round(skin_ratio, 4),
        'dark_ratio': round(dark_ratio, 4),
        'labels': labels,
        'reasons': reasons,
    }


# ---------------------------------------------------------------- 抽帧

def _open_video(path):
    if not HAS_CV2:
        return None, '未安装 opencv-python，无法抽帧'
    if not path or not os.path.exists(path):
        return None, '视频文件不存在：%s' % (path or '(空)')
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        try:
            cap.release()
        except Exception:
            pass
        return None, '视频无法解码（格式不支持或文件损坏）'
    return cap, ''


def _probe_duration(cap):
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if fps > 0 and total > 0:
        return total / fps, fps, total
    # 帧数信息缺失时顺着读一遍
    n = 0
    while True:
        ok, _ = cap.read()
        if not ok:
            break
        n += 1
    fps = fps if fps > 0 else 25.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    return (n / fps if n else 0.0), fps, n


def _pick_times(duration):
    """按时间均匀取帧，总数不超过 MAX_FRAMES。"""
    if duration <= 0:
        return [0.0]
    n = int(math.ceil(duration / float(config.FRAME_INTERVAL_SEC or 1.2)))
    n = max(1, min(int(config.MAX_FRAMES), n))
    if n == 1:
        return [0.0]
    end = max(duration - 0.08, 0.0)
    return [round(end * i / float(n - 1), 3) for i in range(n)]


def _grab_at(cap, ts):
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, float(ts) * 1000.0)
        ok, frame = cap.read()
        if ok and frame is not None:
            return frame
    except Exception:
        pass
    return None


def _summarise(frame_count, flagged, max_risk, top_labels):
    if frame_count <= 0:
        return ''
    if flagged <= 0:
        return '共抽 %d 帧，初筛未发现可疑画面（最高风险 %.2f），可进入人工复核。' % (frame_count, max_risk)
    label_text = '、'.join(top_labels) if top_labels else '画面异常'
    return '共抽 %d 帧，其中 %d 帧初筛可疑（最高风险 %.2f），线索：%s。建议人工逐帧复核。' % (
        frame_count, flagged, max_risk, label_text)


# ---------------------------------------------------------------- 对外接口

def process(content_id):
    """抽帧 + AI 初筛 + 写 content_frames + 更新 contents。

    返回 {content_id, frames, suspicious, duration_sec, status}（另附 frames_flagged/max_risk/degraded/note）。
    """
    content_id = int(content_id)
    row = db.one('SELECT * FROM contents WHERE id=?', (content_id,))
    if row is None:
        raise ValueError('内容不存在：%s' % content_id)
    row = dict(row)

    out_dir = os.path.join(config.MEDIA_DIR, 'content_%d' % content_id, 'frames')
    os.makedirs(out_dir, exist_ok=True)

    db.execute('DELETE FROM content_frames WHERE content_id=?', (content_id,))

    video_path = _abs(row.get('file_path') or '')
    cap, err = _open_video(video_path)

    frames = []
    duration_sec = float(row.get('duration_sec') or 0)
    degrade_note = ''

    if cap is None:
        degrade_note = err or '无法打开视频'
    else:
        try:
            duration_sec, _fps, _total = _probe_duration(cap)
            for i, ts in enumerate(_pick_times(duration_sec)):
                frame = _grab_at(cap, ts)
                if frame is None:
                    continue
                path = os.path.join(out_dir, 'f_%02d.jpg' % (i + 1))
                if not _write_jpeg(path, frame):
                    continue
                info = analyse_frame(frame)
                frames.append({
                    'idx': i + 1,
                    'ts_sec': float(ts),
                    'path': _rel(path),
                    'risk': info['risk'],
                    'labels': info['labels'],
                    'reasons': info['reasons'],
                    'status': 'pending',
                })
        finally:
            try:
                cap.release()
            except Exception:
                pass

    if not frames:
        if not degrade_note:
            degrade_note = '抽帧结果为空（视频时长过短或读取失败）'
        placeholder = _placeholder_frame(out_dir, '该视频暂时无法抽帧：%s' % degrade_note)
        frames.append({
            'idx': 0,
            'ts_sec': 0.0,
            'path': _rel(placeholder),
            'risk': 0.5,
            'labels': ['无法抽帧'],
            'reasons': [degrade_note + '，已转人工抽检'],
            'status': 'pending',
        })

    threshold = float(config.SUSPICIOUS_RISK)
    flagged = [f for f in frames if f['risk'] >= threshold and '无法抽帧' not in f['labels']]
    max_risk = max([f['risk'] for f in frames], default=0.0)
    suspicious = 1 if flagged else 0

    label_counter = {}
    for f in frames:
        for lb in f['labels']:
            label_counter[lb] = label_counter.get(lb, 0) + 1
    top_labels = [lb for lb, _c in sorted(label_counter.items(), key=lambda kv: -kv[1])[:3]
                  if lb != '无法抽帧']

    for f in frames:
        db.execute(
            'INSERT INTO content_frames(content_id,idx,ts_sec,path,risk,labels,reasons,status) '
            'VALUES(?,?,?,?,?,?,?,?)',
            (content_id, f['idx'], f['ts_sec'], f['path'], f['risk'],
             ','.join(f['labels']), '；'.join(f['reasons']), f['status']))

    summary = _summarise(len(frames), len(flagged), max_risk, top_labels)
    if degrade_note:
        summary = '本次未能抽帧：%s。已生成一张说明帧，等待人工抽检。' % degrade_note

    cover = frames[0]['path'] if frames else ''
    params = [round(duration_sec, 3), 'pending_review', summary, round(max_risk, 4)]
    sql = 'UPDATE contents SET duration_sec=?, status=?, ai_summary=?, ai_risk=?'
    if cover and not (row.get('cover_path') or ''):
        sql += ', cover_path=?'
        params.append(cover)
    sql += ' WHERE id=?'
    params.append(content_id)
    db.execute(sql, tuple(params))

    return {
        'content_id': content_id,
        'frames': len(frames),
        'suspicious': suspicious,
        'duration_sec': round(duration_sec, 2),
        'status': 'pending_review',
        'frames_flagged': len(flagged),
        'max_risk': round(max_risk, 4),
        'degraded': bool(degrade_note),
        'note': degrade_note,
    }


def review(content_id, reviewer_id, decision, note='', checklist=None, frame_status=None):
    """人工复核：approve / reject，写 reviews 与 content_frames.status。

    frame_status: {帧 idx 或 str(idx): 'cleared'|'flagged'}；未指定的帧默认 cleared。
    返回 {content_id, status, frames_reviewed}。
    """
    content_id = int(content_id)
    decision = str(decision or '').strip().lower()
    if decision in ('approve', 'approved', 'pass', 'ok'):
        decision = 'approve'
    elif decision in ('reject', 'rejected', 'deny'):
        decision = 'reject'
    else:
        raise ValueError('decision 只能是 approve 或 reject：%r' % (decision,))

    row = db.one('SELECT * FROM contents WHERE id=?', (content_id,))
    if row is None:
        raise ValueError('内容不存在：%s' % content_id)

    frames = [dict(r) for r in db.query(
        'SELECT id, idx FROM content_frames WHERE content_id=? ORDER BY idx', (content_id,))]
    frame_ids = {fr['id'] for fr in frames}

    # frame_status 的键在路由层是「帧 id」（app.py: WHERE id=?），也允许传 idx，两种都认
    by_id, by_idx = {}, {}
    for key, val in (frame_status or {}).items():
        try:
            num = int(key)
        except (TypeError, ValueError):
            continue
        st = str(val).strip().lower()
        if st not in ('cleared', 'flagged'):
            continue
        if num in frame_ids:
            by_id[num] = st
        else:
            by_idx[num] = st

    cleared = flagged = 0
    for fr in frames:
        st = by_id.get(fr['id']) or by_idx.get(int(fr['idx'])) or 'cleared'
        if st == 'flagged':
            flagged += 1
        else:
            cleared += 1
        db.execute('UPDATE content_frames SET status=? WHERE id=?', (st, fr['id']))

    frames_reviewed = cleared + flagged
    status = 'approved' if decision == 'approve' else 'rejected'
    stamp = db.now()

    db.execute(
        'UPDATE contents SET status=?, reviewer_id=?, reviewed_at=?, review_note=?, published_at=? WHERE id=?',
        (status, reviewer_id, stamp, str(note or ''), stamp if decision == 'approve' else None, content_id))

    db.execute(
        'INSERT INTO reviews(content_id,reviewer_id,decision,note,checklist,frames_reviewed,created_at) '
        'VALUES(?,?,?,?,?,?,?)',
        (content_id, reviewer_id, decision, str(note or ''),
         db.dumps(checklist or {}), frames_reviewed, stamp))

    return {
        'content_id': content_id,
        'status': status,
        'frames_reviewed': frames_reviewed,
        'decision': decision,
        'frames_flagged': flagged,
    }


# ---------------------------------------------------------------- 匹配打分

def _subject_score(query, cand):
    a, b = _norm_text(query), _norm_text(cand)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.85
    return round(min(0.7, _cover_ratio(query, cand) * 0.7 + _cover_ratio(cand, query) * 0.3), 4)


def _knowledge_score(query, row):
    if not _norm_text(query):
        return 0.5  # 没给知识点时不惩罚，取中性分
    text = ' '.join(str(row.get(k) or '') for k in
                    ('knowledge_point', 'title', 'description', 'ai_summary'))
    return round(_cover_ratio(query, text), 4)


def _duration_score(sec):
    sec = float(sec or 0)
    if sec <= 0:
        return 0.5
    return round(_clamp01(1.0 - abs(sec - 180.0) / 300.0), 4)


def _days_since(stamp):
    if not stamp:
        return None
    try:
        return max(0.0, (db.parse(db.now()) - db.parse(str(stamp))).total_seconds() / 86400.0)
    except Exception:
        return None


def _freshness_score(row):
    days = _days_since(row.get('published_at') or row.get('created_at'))
    if days is None:
        return 0.3
    return round(1.0 / (1.0 + days / 10.0), 4)


def _fresh_text(row):
    days = _days_since(row.get('published_at') or row.get('created_at'))
    if days is None:
        return '入池时间未知'
    if days < 1:
        return '今日入池'
    if days < 3:
        return '%d 天前入池' % int(days)
    if days < 8:
        return '本周入池'
    return '%d 天前入池' % int(days)


def match_for_session(session, limit=5):
    """只从 approved 内容里，按 主题/知识点/时长/新鲜度 打分，返回带 reason 的推荐列表。"""
    session = dict(session or {})
    subject = session.get('subject') or ''
    knowledge = session.get('knowledge_point') or session.get('stuck_points') or ''
    limit = int(limit or 5)
    if limit <= 0:
        return []

    rows = db.query("SELECT * FROM contents WHERE status='approved' ORDER BY id DESC")
    out = []
    for r in rows:
        r = dict(r)
        sub = _subject_score(subject, r.get('subject'))
        kn = _knowledge_score(knowledge, r)
        dur = _duration_score(r.get('duration_sec'))
        fresh = _freshness_score(r)
        score = round(40.0 * sub + 25.0 * kn + 20.0 * dur + 15.0 * fresh, 2)
        if score <= 3.0:
            continue

        parts = []
        if sub > 0:
            parts.append('主题匹配 %d%%' % int(round(sub * 100)))
        if kn >= 0.25 and _norm_text(knowledge):
            kp = str(r.get('knowledge_point') or r.get('title') or '')[:12]
            parts.append('命中知识点「%s」' % kp)
        parts.append(_duration_text(r.get('duration_sec')))
        parts.append(_fresh_text(r))
        parts.append('已通过人工复核')
        reason = ' · '.join(parts)

        out.append({
            'id': r['id'],
            'title': r.get('title') or '',
            'subject': r.get('subject') or '',
            'duration_sec': round(float(r.get('duration_sec') or 0), 2),
            'reason': reason,
            'score': score,
            'breakdown': {
                'subject': round(sub, 4),
                'knowledge': round(kn, 4),
                'duration': round(dur, 4),
                'freshness': round(fresh, 4),
            },
            'cover_path': r.get('cover_path') or '',
            'file_path': r.get('file_path') or '',
            'source_type': r.get('source_type') or '',
            'knowledge_point': r.get('knowledge_point') or '',
        })

    out.sort(key=lambda x: -x['score'])
    return out[:limit]
