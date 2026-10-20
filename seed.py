# -*- coding: utf-8 -*-
"""演示数据：用户、场馆、48 个座位、路网、学习内容与关键帧。"""
import os
import random
import sys

import db
from config import MEDIA_DIR

random.seed(20261020)


def _clear():
    for t in ['agent_logs', 'workflow_steps', 'workflow_runs', 'relay_pushes', 'messages',
              'reviews', 'content_frames', 'contents', 'study_sessions', 'reservations',
              'nav_edges', 'nav_nodes', 'seats', 'floors', 'buildings', 'users', 'seat_events', 'devices', 'settings']:
        try:
            db.execute('DELETE FROM %s' % t)
        except Exception:
            pass
    try:
        db.execute('DELETE FROM sqlite_sequence')
    except Exception:
        pass


def _users():
    from werkzeug.security import generate_password_hash
    rows = [
        ('student', '林晓', 'student', '沧州交通学院 · 软件工程',
         '把每一次自习，变成下一次的底气。', '高等数学,英语,编程'),
        ('reviewer', '周老师', 'reviewer', '图书馆 · 学习支持中心',
         'AI 标疑点，人来拍板。', '内容审核,学习方法'),
        ('admin', '管理员', 'admin', '智慧校园运营中心',
         '让空间会服务，让学习有回响。', '运营,指标'),
        ('teacher', '陈老师', 'teacher', '数学教研室',
         '把难点讲成直觉。', '高等数学,线性代数'),
    ]
    for username, name, role, college, sig, interests in rows:
        db.execute('INSERT INTO users(username,password_hash,name,role,college,avatar,cover,signature,interests,created_at) '
                   'VALUES(?,?,?,?,?,?,?,?,?,?)',
                   (username, generate_password_hash('123456'), name, role, college, '', '', sig, interests, db.now()))


FLOOR_SPECS = [
    {
        'building': '图书馆', 'name': '2F 静学自习区', 'floor_no': 2,
        'zones': [
            {'code': 'A', 'name': '靠窗区', 'x0': 90, 'y0': 95, 'rows': 3, 'cols': 4, 'dx': 62, 'dy': 52, 'type': 'window', 'features': 'window,power'},
            {'code': 'B', 'name': '安静区', 'x0': 620, 'y0': 95, 'rows': 3, 'cols': 4, 'dx': 62, 'dy': 52, 'type': 'quiet', 'features': 'quiet,power'},
            {'code': 'C', 'name': '电源区', 'x0': 90, 'y0': 420, 'rows': 3, 'cols': 4, 'dx': 62, 'dy': 52, 'type': 'power', 'features': 'power'},
            {'code': 'D', 'name': '讨论区', 'x0': 620, 'y0': 420, 'rows': 3, 'cols': 4, 'dx': 62, 'dy': 52, 'type': 'normal', 'features': 'discussion'},
        ],
    },
    {
        'building': '图书馆', 'name': '3F 研讨协作区', 'floor_no': 3,
        'zones': [
            {'code': 'E', 'name': '研讨区', 'x0': 150, 'y0': 140, 'rows': 2, 'cols': 6, 'dx': 100, 'dy': 120, 'type': 'discussion', 'features': 'discussion,power'},
            {'code': 'F', 'name': '静音舱', 'x0': 150, 'y0': 430, 'rows': 1, 'cols': 4, 'dx': 100, 'dy': 0, 'type': 'quiet', 'features': 'quiet,power'},
        ],
    },
    {
        'building': '教学楼 A', 'name': '1F 自习室', 'floor_no': 1,
        'zones': [
            {'code': 'G', 'name': '自习区', 'x0': 120, 'y0': 140, 'rows': 3, 'cols': 5, 'dx': 95, 'dy': 65, 'type': 'normal', 'features': 'power'},
        ],
    },
]


def _buildings():
    rows = [
        ('图书馆', 'LIB', 38.3035, 116.8382, '沧州交通学院 · 图书馆', '主馆，2F/3F 学习空间'),
        ('教学楼 A', 'TA', 38.3042, 116.8390, '沧州交通学院 · 教学楼 A', '1F 自习室'),
    ]
    for name, code, lat, lng, addr, desc in rows:
        db.execute('INSERT INTO buildings(name,code,lat,lng,address,description) VALUES(?,?,?,?,?,?)',
                   (name, code, lat, lng, addr, desc))


def _build_floors():
    """数据驱动的多建筑/多楼层生成：新增场馆只改 FLOOR_SPECS。"""
    all_seats = []
    for spec in FLOOR_SPECS:
        fid = db.execute('INSERT INTO floors(name,building,floor_no,plan_w,plan_h) VALUES(?,?,?,?,?)',
                         (spec['name'], spec['building'], spec['floor_no'], 960, 620))
        seats = []
        for z in spec['zones']:
            n = 1
            for row in range(z['rows']):
                for col in range(z['cols']):
                    x = z['x0'] + col * z['dx']
                    y = z['y0'] + row * z['dy']
                    code = '%s-%02d' % (z['code'], n)
                    db.execute('INSERT INTO seats(floor_id,code,zone,x,y,w,h,seat_type,features,status) VALUES(?,?,?,?,?,?,?,?,?,?)',
                               (fid, code, z['name'], x, y, 30, 24, z['type'], z['features'], 'free'))
                    seats.append({'code': code, 'zone': z['name'], 'zone_code': z['code'],
                                  'x': x, 'y': y, 'row': row})
                    n += 1
        _make_nav(fid, seats)
        all_seats.extend(seats)
    return all_seats


def _make_nav(fid, seats):
    """按座位坐标生成可扩展的室内路网：入口→大厅→走廊→分区过道→座位。"""
    import math
    from collections import defaultdict
    corridor_y = 335
    min_x = min(s['x'] for s in seats) if seats else 100
    max_x = max(s['x'] for s in seats) if seats else 860
    nodes = {
        'entry': (480, 600, 'entrance'),
        'hall': (480, 520, 'hall'),
        'corridor_c': (480, corridor_y, 'corridor'),
        'corridor_l': (min(240, min_x - 80), corridor_y, 'corridor'),
        'corridor_r': (max(720, max_x + 80), corridor_y, 'corridor'),
    }
    edges = [
        ('entry', 'hall'), ('hall', 'corridor_c'),
        ('corridor_c', 'corridor_l'), ('corridor_c', 'corridor_r'),
    ]
    groups = defaultdict(list)
    for s in seats:
        groups[s['zone_code']].append(s)
    for zcode, zseats in groups.items():
        ys = sorted(set(s['y'] for s in zseats))
        left = min(s['x'] for s in zseats) < 480
        aisle_x = min(s['x'] for s in zseats) - 34 if left else max(s['x'] for s in zseats) + 34
        row_nodes = []
        for i, y in enumerate(ys, 1):
            code = 'z_%s_r%d' % (zcode.lower(), i)
            nodes[code] = (aisle_x, y, 'aisle')
            row_nodes.append(code)
        for i in range(len(row_nodes) - 1):
            edges.append((row_nodes[i], row_nodes[i + 1]))
        corner = 'z_%s_corner' % zcode.lower()
        nodes[corner] = (aisle_x, corridor_y, 'corner')
        edges.append((corner, row_nodes[0]))
        edges.append((corner, 'corridor_l' if left else 'corridor_r'))
        for s in zseats:
            node = 's_%s' % s['code']
            nodes[node] = (s['x'], s['y'], 'seat')
            edges.append((row_nodes[ys.index(s['y'])], node))
    for code, (x, y, kind) in nodes.items():
        db.execute('INSERT INTO nav_nodes(floor_id,code,x,y,kind) VALUES(?,?,?,?,?)', (fid, code, x, y, kind))
    for a, b in edges:
        ax, ay, _ = nodes[a]
        bx, by, _ = nodes[b]
        db.execute('INSERT INTO nav_edges(floor_id,from_node,to_node,distance) VALUES(?,?,?,?)',
                   (fid, a, b, round(math.hypot(ax - bx, ay - by), 2)))


def _font(size):
    from PIL import ImageFont
    for p in [r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\simhei.ttf', r'C:\Windows\Fonts\simsun.ttc', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc']:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def make_video(path, title, slides, red_index=-1):
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw
    os.makedirs(os.path.dirname(path), exist_ok=True)
    frames = []
    for si, (t, body) in enumerate(slides):
        img = Image.new('RGB', (640, 360), (15, 42, 74))
        d = ImageDraw.Draw(img)
        if si == red_index:
            d.rectangle([0, 0, 640, 360], fill=(160, 28, 28))
        else:
            for y in range(360):
                d.line([(0, y), (640, y)], fill=(15, 42 + y // 10, 74))
        d.text((40, 40), t, font=_font(30), fill=(255, 255, 255))
        yy = 110
        for line in body:
            d.text((40, yy), line, font=_font(20), fill=(235, 240, 248))
            yy += 38
        d.text((40, 318), '习得 · 学习接力   %d/%d' % (si + 1, len(slides)), font=_font(14), fill=(200, 210, 225))
        frames.append(cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR))
    h, w = frames[0].shape[:2]
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'mp4v'), 8, (w, h))
    for f in frames:
        for _ in range(8):
            vw.write(f)
    vw.release()
    return path


def _frames(content_id, video_path):
    import cv2
    import numpy as np
    outdir = os.path.join(MEDIA_DIR, 'content_%d' % content_id, 'frames')
    os.makedirs(outdir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    fps = cap.get(cv2.CAP_PROP_FPS) or 8
    n = min(8, max(1, total))
    idxs = [int(i * (total - 1) / max(1, n - 1)) for i in range(n)]
    frames = []
    for i, fi in enumerate(idxs):
        cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
        ok, frame = cap.read()
        if not ok:
            continue
        path = os.path.join(outdir, 'f_%02d.jpg' % (i + 1))
        ok, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        if ok:
            buf.tofile(path)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        red = float(((rgb[:, :, 0] > 0.55) & (rgb[:, :, 1] < 0.35) & (rgb[:, :, 2] < 0.35)).mean())
        bright = float(rgb.mean())
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        risk, labels, reasons = 0.0, [], []
        if red > 0.35:
            risk = max(risk, 0.78)
            labels.append('大面积红色')
            reasons.append('画面高饱和红色占比 %.0f%%，需人工确认是否为警示/血腥内容' % (red * 100))
        if bright < 0.12:
            risk = max(risk, 0.5)
            labels.append('画面过暗')
            reasons.append('画面过暗，可能影响观看')
        if blur < 40:
            labels.append('画面模糊')
            reasons.append('画面清晰度偏低')
        frames.append({'idx': i + 1, 'ts': round(fi / fps, 1), 'path': path,
                       'risk': round(risk, 2), 'labels': labels, 'reasons': reasons})
    cap.release()
    return frames, round(total / fps, 1)


def _contents(user_ids):
    specs = [
        ('极限的直觉：从无限逼近到 ε-δ', '高等数学', '极限,ε-δ', 'teacher', 'student',
         '用 3 分钟把“无限逼近”讲成直觉，再看 ε-δ 定义。',
         [('极限的直觉', ['先不看定义。', '“无限逼近”和“到达”', '有什么区别？', '', '极限关心过程，不是该点取值。'])]),
        ('英语时态：一张时间轴讲清 12 个时态', '英语', '时态,时间轴', 'teacher', 'student',
         '把 12 个时态放回时间轴上，一次记住。',
         [('英语时态', ['过去 ← 现在 → 将来', '', '先问：动作发生在哪一段？', '再看：动作和参照点的关系。', '', '一张图记住 12 个时态。'])]),
        ('递归到底怎么展开？用一棵树看懂', '编程', '递归,调用栈', 'student', 'student',
         '用一棵调用树解释递归展开与回溯。',
         [('递归', ['递归 = 把大问题变成小问题', '', '先写终止条件', '再写递推关系', '', '调用栈就是那棵树。'])]),
        ('自习复盘三步法', '学习方法', '复盘,笔记', 'platform', 'student',
         '结束自习前，用三步把今天真正留下来。',
         [('自习复盘三步法', ['一、写下今天学到的三件事', '二、标出一个还没懂的点', '三、给下一次留一个问题', '', '三分钟，比再刷十道题有用。'])]),
        ('导数入门的三个直觉', '高等数学', '导数,变化率', 'student', 'student',
         '切线、速度、变化率：三个直觉理解导数。',
         [('导数入门', ['一、切线斜率', '二、瞬时速度', '三、变化率']),
          ('重点标记：易错点', ['导数存在 ≠ 导函数连续', '可导一定连续，连续不一定可导', '这是最容易错的一条']),
          ('记住这三个直觉', ['切线、速度、变化率', '回到定义，不要只背公式'])]),
    ]
    for i, (title, subject, kp, source, owner_key, desc, slides) in enumerate(specs):
        owner_id = user_ids[owner_key]
        slug = 'content_%d' % (i + 1)
        video = os.path.join(MEDIA_DIR, slug, 'video.mp4')
        red_index = 1 if i == 4 else -1
        make_video(video, title, slides, red_index=red_index)
        status = 'pending_review' if i == 4 else 'approved'
        reviewer_id = user_ids['reviewer'] if status == 'approved' else None
        cid = db.execute(
            'INSERT INTO contents(owner_id,title,subject,knowledge_point,description,source_type,file_path,cover_path,'
            'duration_sec,status,ai_summary,ai_risk,review_note,reviewer_id,reviewed_at,published_at,views,helpful,unhelpful,created_at) '
            'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (owner_id, title, subject, kp, desc, source, video, '', 0, status, '', 0, '',
             reviewer_id, db.now() if reviewer_id else None, db.now() if reviewer_id else None,
             12 + i * 3, 4 + i, 1, db.now()))
        frame_rows, duration = _frames(cid, video)
        duration = 180.0  # 演示片实际很短，元数据按 3 分钟展示，匹配“课间看一条”的产品口径
        cover = frame_rows[0]['path'] if frame_rows else ''
        db.execute('UPDATE contents SET cover_path=?,duration_sec=? WHERE id=?', (cover, duration, cid))
        max_risk = 0
        for fr in frame_rows:
            max_risk = max(max_risk, fr['risk'])
            db.execute('INSERT INTO content_frames(content_id,idx,ts_sec,path,risk,labels,reasons,status) VALUES(?,?,?,?,?,?,?,?)',
                       (cid, fr['idx'], fr['ts'], fr['path'], fr['risk'],
                        ','.join(fr['labels']), '；'.join(fr['reasons']), 'pending'))
        db.execute('UPDATE contents SET ai_risk=?,ai_summary=? WHERE id=?',
                   (max_risk, 'AI 初筛：%d 帧，最高风险 %.2f' % (len(frame_rows), max_risk), cid))
        if status == 'approved':
            db.execute("UPDATE content_frames SET status='cleared' WHERE content_id=?", (cid,))


def _history(user_ids):
    sid = user_ids['student']
    seat = db.one("SELECT * FROM seats WHERE code='A-06'")
    from datetime import datetime, timedelta
    end = datetime.now() - timedelta(days=1, hours=2)
    start = end - timedelta(minutes=96)
    fmt = '%Y-%m-%d %H:%M:%S'
    rid = db.execute('INSERT INTO reservations(user_id,seat_id,subject,goal,start_at,end_at,checkin_at,checkout_at,status,source,created_at) '
                     "VALUES(?,?,?,?,?,?,?,?,'completed','web',?)",
                     (sid, seat['id'], '高等数学', '复习极限', start.strftime(fmt), end.strftime(fmt),
                      start.strftime(fmt), end.strftime(fmt), start.strftime(fmt)))
    ssid = db.execute('INSERT INTO study_sessions(reservation_id,user_id,seat_id,subject,started_at,ended_at,duration_min,status,stuck_points,relay_content_id,created_at) '
                      "VALUES(?,?,?,?,?,?,96,'relayed','ε-δ',1,?)",
                      (rid, sid, seat['id'], '高等数学', start.strftime(fmt), end.strftime(fmt), start.strftime(fmt)))
    db.execute('INSERT INTO relay_pushes(session_id,user_id,content_id,reason,score_json,created_at,opened_at,feedback) '
               'VALUES(?,?,?,?,?,?,?,?)',
               (ssid, sid, 1, '主题匹配 · 命中你的卡点 ε-δ · 3 分钟适合课间',
                db.dumps({'score': 0.92}), end.strftime(fmt), end.strftime(fmt), 'helpful'))
    db.execute('INSERT INTO messages(user_id,kind,title,body,payload,read,created_at) VALUES(?,?,?,?,?,1,?)',
               (sid, 'relay', '学习接力 · 为你找到一条视频',
                '你刚在 A-06 完成 96 分钟学习。这条《极限的直觉》讲的正是你卡住的 ε-δ。',
                db.dumps({'push_id': 1, 'content_id': 1}), end.strftime(fmt)))


def seed(reset=True):
    db.init_db()
    if reset:
        _clear()
    if db.one('SELECT COUNT(*) c FROM users')['c']:
        print('已有数据，跳过 seed（用 --reset 强制重建）')
        return
    _users()
    _buildings()
    users = {r['username']: r['id'] for r in db.query('SELECT id,username FROM users')}
    all_seats = _build_floors()
    _contents(users)
    _history(users)
    print('seed 完成：%d 座位 / %d 内容 / %d 用户' % (
        len(all_seats), db.one('SELECT COUNT(*) c FROM contents')['c'], len(users)))


if __name__ == '__main__':
    seed(reset=('--reset' in sys.argv or db.one('SELECT COUNT(*) c FROM users')['c'] == 0))
