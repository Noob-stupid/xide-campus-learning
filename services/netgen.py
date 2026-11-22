# -*- coding: utf-8 -*-
"""从平面图 / DXF 自动生成室内路网与座位候选。

两条路线（对应参考项目的两种做法）：

1. **图片路线**：底图二值化 -> 障碍掩膜 -> 取可走区 -> 细化成骨架 -> 骨架聚成图。
   不需要 CAD，但只能"猜"可行走区域，噪声多，适合没有 DXF 时兜底。
2. **DXF 路线**：DXF 是结构化数据，图层名直接写明墙/家具/房间名。
   不用猜：墙线当障碍，家具块当座位候选，文字层当房间名。

两条路线产出的节点都落在 960×620 的画布坐标里，和选座页共用同一套坐标。
"""
import math
import re

import numpy as np

CANVAS_W, CANVAS_H = 960, 620
MARGIN = 28

WALL_HINTS = ('wall', 'a-wall', '墙', '隔断', 'partition', 'column', '柱')
FURN_HINTS = ('furn', 'furniture', '家具', 'desk', 'table', 'chair', 'seat', '桌', '椅', '座')
TEXT_HINTS = ('text', 'anno', 'label', '文字', '标注', '房间')


# ===========================================================================
# 一、图片路线
# ===========================================================================
def _load_gray(path, size=(CANVAS_W, CANVAS_H)):
    from PIL import Image
    W, H = size
    with Image.open(path) as im:
        im = im.convert('L')
        w, h = im.size
        # 统一缩到画布尺寸，避免 4000px 的图算半天
        scale = min(W / float(w), H / float(h))
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))))
        canvas = Image.new('L', (W, H), 255)
        canvas.paste(im, ((W - im.size[0]) // 2, (H - im.size[1]) // 2))
        return np.array(canvas, dtype=np.uint8)


def _binarize(gray):
    """墙线是深色 -> 障碍；白底是可行走。用 Otsu 自适应阈值。"""
    hist, _ = np.histogram(gray.flatten(), bins=256, range=(0, 256))
    total = gray.size
    sum_all = np.dot(np.arange(256), hist)
    sum_b = 0.0
    w_b = 0
    best, thr = -1.0, 128
    for i in range(256):
        w_b += hist[i]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += i * hist[i]
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        between = w_b * w_f * (m_b - m_f) ** 2
        if between > best:
            best, thr = between, i
    wall = gray <= max(30, thr)
    return wall


def _runs_bridge(mask):
    """把断开的墙线接上一点，避免细化后路线从墙缝里钻出去。"""
    m = mask.copy()
    for _ in range(2):
        m = m | np.roll(m, 1, axis=0) | np.roll(m, -1, axis=0) | np.roll(m, 1, axis=1) | np.roll(m, -1, axis=1)
    return m


def _thin(binary):
    """Zhang-Suen 细化（numpy 版；opencv-python 不带 ximgproc）。"""
    img = (binary > 0).astype(np.uint8)
    changed = True
    guard = 0
    while changed and guard < 60:
        changed = False
        guard += 1
        for step in (0, 1):
            p = np.pad(img, 1, mode='constant')
            p2, p3, p4 = p[:-2, 1:-1], p[:-2, 2:], p[1:-1, 2:]
            p5, p6, p7 = p[2:, 2:], p[2:, 1:-1], p[2:, :-2]
            p8, p9 = p[1:-1, :-2], p[:-2, :-2]
            neigh = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
            seq = [p2, p3, p4, p5, p6, p7, p8, p9, p2]
            trans = sum(((seq[k] == 0) & (seq[k + 1] == 1)).astype(np.uint8) for k in range(8))
            if step == 0:
                cond = (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            else:
                cond = (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)
            kill = (img == 1) & (neigh >= 2) & (neigh <= 6) & (trans == 1) & cond
            if kill.any():
                img[kill] = 0
                changed = True
    return img


def _skeleton_to_graph(skel, cell=38.0):
    ys, xs = np.nonzero(skel)
    if len(xs) == 0:
        raise ValueError('图里没找到可走区域，检查底图是不是太大或太浅')
    cells = {}
    for x, y in zip(xs, ys):
        cells.setdefault((int(x // cell), int(y // cell)), []).append((x, y))
    order = sorted(cells.keys())
    nodes, idx = [], {}
    for i, k in enumerate(order, start=1):
        pts = np.array(cells[k], dtype=float)
        code = 'N%03d' % i
        idx[k] = code
        nodes.append((code, round(float(pts[:, 0].mean()), 1), round(float(pts[:, 1].mean()), 1), 'corridor'))
    edges = []
    limit = cell * 1.25
    for (cx, cy) in order:
        # 只连上下左右：对角相邻会连出一堆三角形，路网看起来像渔网，
        # A* 也会在走廊里斜着插来插去。
        for dx, dy in ((1, 0), (0, 1)):
            nb = (cx + dx, cy + dy)
            if nb in idx:
                a, b = idx[(cx, cy)], idx[nb]
                if a != b:
                    pair = tuple(sorted((a, b)))
                    if pair not in edges:
                        edges.append(pair)
    pos = {c: (x, y) for c, x, y, _ in nodes}
    keep = []
    for a, b in edges:
        (x1, y1), (x2, y2) = pos[a], pos[b]
        if math.hypot(x1 - x2, y1 - y2) <= limit:
            keep.append((a, b))
    return nodes, keep


def _prune_and_merge(nodes, edges):
    """剪掉毛刺（度=1 的短枝），再把度=2 的直线段合并 —— 让路网像走廊而不是蛛网。"""
    pos = {c: (x, y) for c, x, y, _ in nodes}
    kind = {c: k for c, x, y, k in nodes}
    adj = {c: set() for c in pos}
    for a, b in edges:
        if a in adj and b in adj:
            adj[a].add(b)
            adj[b].add(a)

    for _ in range(300):
        leaves = [c for c in adj if len(adj[c]) == 1]
        if not leaves:
            break
        for c in leaves:
            for nb in list(adj[c]):
                adj[nb].discard(c)
            adj.pop(c, None)
            pos.pop(c, None)
            kind.pop(c, None)

    changed = True
    while changed:
        changed = False
        for c in list(adj.keys()):
            if len(adj[c]) != 2:
                continue
            a, b = list(adj[c])
            ax, ay = pos[a]
            bx, by = pos[b]
            cx, cy = pos[c]
            v1 = (cx - ax, cy - ay)
            v2 = (bx - cx, by - cy)
            n1 = math.hypot(*v1) or 1e-6
            n2 = math.hypot(*v2) or 1e-6
            if (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2) < 0.94:
                continue
            adj[a].discard(c)
            adj[b].discard(c)
            adj.pop(c, None)
            pos.pop(c, None)
            kind.pop(c, None)
            adj[a].add(b)
            adj[b].add(a)
            changed = True
            break

    codes = sorted(adj.keys())
    renum = {old: 'N%03d' % i for i, old in enumerate(codes, start=1)}
    out_nodes = [(renum[c], round(pos[c][0], 1), round(pos[c][1], 1), kind.get(c, 'corridor')) for c in codes]
    seen, out_edges = set(), []
    for a in codes:
        for b in adj[a]:
            key = tuple(sorted((a, b)))
            if key in seen:
                continue
            seen.add(key)
            out_edges.append((renum[a], renum[b]))
    return out_nodes, out_edges


def from_image(path, size=(CANVAS_W, CANVAS_H)):
    """底图 -> 路网。返回 (nodes, edges, meta)。"""
    W, H = int(size[0]), int(size[1])
    gray = _load_gray(path, (W, H))
    wall = _binarize(gray)
    wall = _runs_bridge(wall)
    free = (~wall).astype(np.uint8)
    # 去掉贴边的碎块和外圈
    free[:6, :] = 0
    free[-6:, :] = 0
    free[:, :6] = 0
    free[:, -6:] = 0
    skel = _thin(free)
    nodes, edges = _skeleton_to_graph(skel)
    nodes, edges = _prune_and_merge(nodes, edges)
    if not nodes:
        raise ValueError('细化后没有可用节点，底图可能太干净（没有墙线）')
    return nodes, edges, {'wall_ratio': round(float(wall.mean()), 3), 'skeleton_px': int(skel.sum())}


# ===========================================================================
# 二、DXF 路线
# ===========================================================================
_CODE_RE = re.compile(r'^\s*(\d{1,3})\s*$')


def _pairs(text):
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines) - 1:
        if _CODE_RE.match(lines[i]):
            out.append((int(lines[i].strip()), lines[i + 1].rstrip('\r')))
            i += 2
        else:
            i += 1
    return out


def _entities(pairs):
    out, cur, inside = [], None, False
    i, n = 0, len(pairs)
    while i < n:
        code, val = pairs[i]
        if code == 2 and val.strip().upper() == 'ENTITIES':
            inside = True
            i += 1
            continue
        if inside and code == 2 and val.strip().upper() in ('OBJECTS', 'BLOCKS', 'CLASSES'):
            break
        if inside and code == 0:
            if cur:
                out.append(cur)
            cur = {'type': val.strip().upper(), 'layer': '0', 'pts': [], 'closed': False, 'text': ''}
            i += 1
            continue
        if cur is not None and inside:
            if code == 8:
                cur['layer'] = val.strip()
            elif code == 1:
                cur['text'] = val.strip()
            elif code == 70:
                try:
                    cur['closed'] = bool(int(val) & 1)
                except Exception:
                    pass
            elif code in (10, 11):
                cur['pts'].append([float(val), None])
            elif code in (20, 21):
                if cur['pts'] and cur['pts'][-1][1] is None:
                    cur['pts'][-1][1] = float(val)
        i += 1
    if cur:
        out.append(cur)
    return [e for e in out if e['pts'] or e['text']]


def _role(entity):
    layer = (entity.get('layer') or '').lower()
    if any(h in layer for h in WALL_HINTS):
        return 'wall'
    if any(h in layer for h in FURN_HINTS):
        return 'furn'
    if any(h in layer for h in TEXT_HINTS):
        return 'text'
    if entity['type'] in ('TEXT', 'MTEXT'):
        return 'text'
    return 'other'


def _fit(points, w=CANVAS_W, h=CANVAS_H, margin=MARGIN):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span_x = max(1e-6, maxx - minx)
    span_y = max(1e-6, maxy - miny)
    s = min((w - 2 * margin) / span_x, (h - 2 * margin) / span_y)
    ox = margin + ((w - 2 * margin) - span_x * s) / 2
    oy = margin + ((h - 2 * margin) - span_y * s) / 2

    def tr(p):
        return (round((p[0] - minx) * s + ox, 1), round((p[1] - miny) * s + oy, 1))

    return tr, s


def _seg(mask, a, b, thick=3):
    x0, y0 = int(a[0]), int(a[1])
    x1, y1 = int(b[0]), int(b[1])
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    h, w = mask.shape
    r = max(0, thick // 2)
    guard = 0
    while guard < 20000:
        guard += 1
        mask[max(0, y0 - r):min(h, y0 + r + 1), max(0, x0 - r):min(w, x0 + r + 1)] = 1
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy


def _from_dxf_simple(raw_bytes, cell=36.0, size=(CANVAS_W, CANVAS_H)):
    """DXF -> (路网, 座位候选, 房间名, 统计)。"""
    W, H = int(size[0]), int(size[1])
    text = None
    for enc in ('utf-8', 'gbk', 'latin-1'):
        try:
            text = raw_bytes.decode(enc)
            break
        except Exception:
            continue
    if not text:
        raise ValueError('DXF 编码无法识别（可能是二进制 DXF）')
    pairs = _pairs(text)
    if not pairs:
        raise ValueError('不是 ASCII DXF')
    ents = _entities(pairs)
    if not ents:
        raise ValueError('DXF 里没有实体')

    walls = [e for e in ents if _role(e) == 'wall' and e['pts']]
    furns = [e for e in ents if _role(e) == 'furn' and e['pts']]
    labels = [e for e in ents if _role(e) == 'text' and e['text']]
    if not walls:
        # 没有分层信息：把所有线当墙，至少能出一张图
        walls = [e for e in ents if e['pts'] and e['type'] in ('LINE', 'LWPOLYLINE', 'POLYLINE')]
    if not walls:
        raise ValueError('没找到墙线（图层名里应含 wall / 墙）')

    all_pts = [p for e in walls for p in e['pts'] if p[1] is not None]
    tr, scale = _fit(all_pts, W, H)

    mask = np.zeros((H, W), dtype=np.uint8)
    for e in walls:
        pts = [tr(p) for p in e['pts'] if p[1] is not None]
        for a, b in zip(pts, pts[1:]):
            _seg(mask, a, b, 3)
        if e.get('closed') and len(pts) > 2:
            _seg(mask, pts[-1], pts[0], 3)

    free = (mask == 0).astype(np.uint8)
    free[:6, :] = 0
    free[-6:, :] = 0
    free[:, :6] = 0
    free[:, -6:] = 0
    skel = _thin(free)
    nodes, edges = _skeleton_to_graph(skel, cell=cell)
    nodes, edges = _prune_and_merge(nodes, edges)

    # 座位候选：家具实体的包围盒中心，编号沿用房间名（没有就 SEAT-001）
    seats = []
    seen = set()
    for i, e in enumerate(furns, start=1):
        pts = [tr(p) for p in e['pts'] if p[1] is not None]
        if not pts:
            continue
        cx = round(sum(p[0] for p in pts) / len(pts), 1)
        cy = round(sum(p[1] for p in pts) / len(pts), 1)
        label = 'SEAT-%03d' % i
        if label in seen:
            continue
        seen.add(label)
        seats.append({'code': label, 'x': cx, 'y': cy})

    rooms = []
    for e in labels:
        pts = [tr(p) for p in e['pts'] if p[1] is not None]
        if not pts:
            continue
        rooms.append({'name': e['text'][:24], 'x': pts[0][0], 'y': pts[0][1]})

    if not nodes:
        raise ValueError('按墙线切开后没有可行走区域，检查图层或图元范围')
    return nodes, edges, seats, rooms, {
        'walls': len(walls), 'furniture': len(furns), 'labels': len(labels),
        'scale': round(scale, 4),
    }

def from_dxf(raw_bytes, cell=36.0, size=(CANVAS_W, CANVAS_H)):
    """DXF -> (nodes, edges, seats, rooms, meta)。

    使用从 MAX_xiangmu 验证过的 DxfRoadNetworkBuilder：
    - 按图层名识别 wall / furniture / text / door / stair
    - 处理 DXF 单位、墙主体包围盒、整幅图坐标对齐
    - 只把 300~900mm 的闭合家具块作为座位候选
    - 用骨架生成路网并补连孤立点
    """
    import os
    import tempfile
    from services.dxf_reader import DxfRoadNetworkBuilder

    fd, tmp = tempfile.mkstemp(suffix='.dxf')
    try:
        with os.fdopen(fd, 'wb') as fh:
            fh.write(raw_bytes)
        out = DxfRoadNetworkBuilder().build(tmp, target_size=size)
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass
    if not out.get('ok'):
        raise ValueError(out.get('error') or 'DXF 解析失败')
    W, H = int(size[0]), int(size[1])
    raw_nodes = (out.get('network') or {}).get('nodes') or {}
    raw_edges = (out.get('network') or {}).get('edges') or []
    if not raw_nodes:
        raise ValueError('DXF 没有生成可用路网节点')
    # 统一编号，保留 x/y
    ordered = sorted(raw_nodes.items(), key=lambda kv: (float(kv[1].get('y', 0)), float(kv[1].get('x', 0))))
    remap, nodes = {}, []
    for i, (old, n) in enumerate(ordered, start=1):
        code = 'N%03d' % i
        remap[old] = code
        x = max(0, min(W - 1, round(float(n.get('x', 0)), 1)))
        y = max(0, min(H - 1, round(float(n.get('y', 0)), 1)))
        nodes.append((code, x, y, 'corridor'))
    edges, seen = [], set()
    for e in raw_edges:
        a = remap.get(e.get('from'))
        b = remap.get(e.get('to'))
        if not a or not b or a == b:
            continue
        key = tuple(sorted((a, b)))
        if key not in seen:
            seen.add(key)
            edges.append(key)
    seats, seat_seen = [], set()
    for i, s in enumerate(out.get('seats') or [], start=1):
        code = str(s.get('seat_label') or s.get('code') or ('SEAT-%03d' % i))[:24]
        if code in seat_seen:
            code = '%s-%02d' % (code[:20], i)
        seat_seen.add(code)
        seats.append({'code': code,
                      'x': max(0, min(W - 1, round(float(s.get('x', 0)), 1))),
                      'y': max(0, min(H - 1, round(float(s.get('y', 0)), 1))),
                      'w': 16, 'h': 12})
    rooms = []
    for r in out.get('rooms') or []:
        rooms.append({'name': str(r.get('name') or '')[:24],
                      'code': str(r.get('code') or ''),
                      'x': r.get('x', 0), 'y': r.get('y', 0)})
    meta = dict(out.get('stats') or {})
    meta['warnings'] = (out.get('warnings') or [])[:8]
    return nodes, edges, seats, rooms, meta
