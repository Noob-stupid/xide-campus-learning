# -*- coding: utf-8 -*-
"""室内路网编排（后台编辑用）。

和 `services/navigation.py` 的分工：
- `navigation.py` 只读：把 nav_nodes / nav_edges 变成图 + A* 寻路；
- 本模块只写：节点/连线的增删改、整体缩放平移、连通性诊断。

坐标统一用选座页那张 960×620 的画布，所以后台底图、座位、路网三者能对齐。
"""
import math
import re

import db

CANVAS_W, CANVAS_H = 960, 620
PAD = 8


# ---------------------------------------------------------------------------
# 基础
# ---------------------------------------------------------------------------
def canvas_size():
    return CANVAS_W, CANVAS_H


def canvas_of(floor_id):
    """这一层的画布尺寸（跟随底图比例；老数据回落 960×620）。"""
    row = db.one('SELECT canvas_w, canvas_h FROM floors WHERE id=?', (floor_id,))
    if row:
        try:
            w = float(row['canvas_w'] or CANVAS_W)
            h = float(row['canvas_h'] or CANVAS_H)
            if w > 0 and h > 0:
                return w, h
        except Exception:
            pass
    return float(CANVAS_W), float(CANVAS_H)


def _clamp(x, y, size=None):
    w, h = size or (CANVAS_W, CANVAS_H)
    x = max(PAD, min(w - PAD, float(x)))
    y = max(PAD, min(h - PAD, float(y)))
    return round(x, 1), round(y, 1)


def _dist(a, b):
    return round(math.hypot(float(a['x']) - float(b['x']), float(a['y']) - float(b['y'])), 1)


def nodes_of(floor_id):
    return [dict(r) for r in db.query('SELECT * FROM nav_nodes WHERE floor_id=? ORDER BY code', (floor_id,))]


def edges_of(floor_id):
    return [dict(r) for r in db.query('SELECT * FROM nav_edges WHERE floor_id=? ORDER BY id', (floor_id,))]


def network(floor_id):
    nodes, edges = nodes_of(floor_id), edges_of(floor_id)
    return {
        'nodes': nodes, 'edges': edges,
        'stats': stats(nodes, edges),
        'canvas': dict(zip(('w', 'h'), canvas_of(floor_id))),
    }


def _by_code(floor_id, code):
    return db.one('SELECT * FROM nav_nodes WHERE floor_id=? AND code=?', (floor_id, code))


def next_code(floor_id, prefix='N'):
    top = 0
    for r in db.query('SELECT code FROM nav_nodes WHERE floor_id=?', (floor_id,)):
        m = re.search(r'(\d+)$', str(r['code'] or ''))
        if m:
            top = max(top, int(m.group(1)))
    return '%s%03d' % (prefix, top + 1)


# ---------------------------------------------------------------------------
# 增删改
# ---------------------------------------------------------------------------
def create_node(floor_id, x, y, kind='corridor', code=''):
    x, y = _clamp(x, y, canvas_of(floor_id))
    code = (code or '').strip()[:12] or next_code(floor_id)
    if _by_code(floor_id, code):
        raise ValueError('节点号 %s 已存在' % code)
    db.execute('INSERT INTO nav_nodes(floor_id,code,x,y,kind) VALUES(?,?,?,?,?)',
               (floor_id, code, x, y, kind or 'corridor'))
    return dict(_by_code(floor_id, code))


def update_node(nid, **kw):
    node = db.one('SELECT * FROM nav_nodes WHERE id=?', (nid,))
    if not node:
        raise ValueError('节点不存在')
    sets, args = [], []
    if 'x' in kw or 'y' in kw:
        x, y = _clamp(kw.get('x', node['x']), kw.get('y', node['y']), canvas_of(node['floor_id']))
        sets += ['x=?', 'y=?']
        args += [x, y]
    if kw.get('code'):
        code = str(kw['code']).strip()[:12]
        if code != node['code']:
            if _by_code(node['floor_id'], code):
                raise ValueError('节点号 %s 已存在' % code)
            db.execute('UPDATE nav_edges SET from_node=? WHERE floor_id=? AND from_node=?',
                       (code, node['floor_id'], node['code']))
            db.execute('UPDATE nav_edges SET to_node=? WHERE floor_id=? AND to_node=?',
                       (code, node['floor_id'], node['code']))
            sets.append('code=?')
            args.append(code)
    if kw.get('kind'):
        sets.append('kind=?')
        args.append(str(kw['kind'])[:12])
    if not sets:
        raise ValueError('没有要更新的字段')
    args.append(nid)
    db.execute('UPDATE nav_nodes SET %s WHERE id=?' % ', '.join(sets), tuple(args))
    if 'x' in kw or 'y' in kw:
        refresh_edges(node['floor_id'])
    return dict(db.one('SELECT * FROM nav_nodes WHERE id=?', (nid,)))


def delete_node(nid):
    node = db.one('SELECT * FROM nav_nodes WHERE id=?', (nid,))
    if not node:
        raise ValueError('节点不存在')
    db.execute('DELETE FROM nav_edges WHERE floor_id=? AND (from_node=? OR to_node=?)',
               (node['floor_id'], node['code'], node['code']))
    db.execute('DELETE FROM nav_nodes WHERE id=?', (nid,))
    return dict(node)


def link(floor_id, a, b):
    if not a or not b:
        raise ValueError('需要两个节点')
    if a == b:
        raise ValueError('不能连到自己')
    na, nb = _by_code(floor_id, a), _by_code(floor_id, b)
    if not na or not nb:
        raise ValueError('节点不存在')
    dup = db.one('SELECT id FROM nav_edges WHERE floor_id=? AND '
                 '((from_node=? AND to_node=?) OR (from_node=? AND to_node=?))',
                 (floor_id, a, b, b, a))
    if dup:
        raise ValueError('%s 和 %s 已经连过了' % (a, b))
    db.execute('INSERT INTO nav_edges(floor_id,from_node,to_node,distance) VALUES(?,?,?,?)',
               (floor_id, a, b, _dist(na, nb)))
    return dict(db.one('SELECT * FROM nav_edges WHERE floor_id=? ORDER BY id DESC LIMIT 1', (floor_id,)))


def unlink(edge_id):
    edge = db.one('SELECT * FROM nav_edges WHERE id=?', (edge_id,))
    if not edge:
        raise ValueError('连线不存在')
    db.execute('DELETE FROM nav_edges WHERE id=?', (edge_id,))
    return dict(edge)


def refresh_edges(floor_id):
    for e in edges_of(floor_id):
        a = _by_code(floor_id, e['from_node'])
        b = _by_code(floor_id, e['to_node'])
        if a and b:
            db.execute('UPDATE nav_edges SET distance=? WHERE id=?', (_dist(a, b), e['id']))


def clear_network(floor_id):
    db.execute('DELETE FROM nav_edges WHERE floor_id=?', (floor_id,))
    db.execute('DELETE FROM nav_nodes WHERE floor_id=?', (floor_id,))


def replace_network(floor_id, nodes, edges):
    """nodes: [(code,x,y,kind)]，edges: [(code_a, code_b)]"""
    clear_network(floor_id)
    for code, x, y, kind in nodes:
        db.execute('INSERT INTO nav_nodes(floor_id,code,x,y,kind) VALUES(?,?,?,?,?)',
                   (floor_id, code, x, y, kind or 'corridor'))
    pos = {c: (x, y) for c, x, y, _ in nodes}
    n_edge = 0
    for a, b in edges:
        if a in pos and b in pos and a != b:
            (x1, y1), (x2, y2) = pos[a], pos[b]
            db.execute('INSERT INTO nav_edges(floor_id,from_node,to_node,distance) VALUES(?,?,?,?)',
                       (floor_id, a, b, round(math.hypot(x1 - x2, y1 - y2), 1)))
            n_edge += 1
    return len(nodes), n_edge


# ---------------------------------------------------------------------------
# 整体缩放 / 平移
# ---------------------------------------------------------------------------
def transform(floor_id, scale=1.0, dx=0.0, dy=0.0, with_seats=True):
    """整层缩放 + 平移。

    关键：**不能逐个节点钳制**——贴边的节点各自被压回画布，路网形状就变形了
    （用户看到的就是"越拖越扁"）。这里先把所有点一起算好，再用同一个平移量
    把整组挪回画布内，形态严格保持。
    """
    scale = max(0.2, min(4.0, float(scale or 1)))
    dx = float(dx or 0)
    dy = float(dy or 0)
    cw, ch = canvas_of(floor_id)
    cx, cy = cw / 2, ch / 2

    nodes = nodes_of(floor_id)
    seats = [dict(r) for r in db.query('SELECT * FROM seats WHERE floor_id=?', (floor_id,))] if with_seats else []
    if not nodes and not seats:
        return {'nodes': 0, 'seats': 0}

    def moved(x, y):
        return ((float(x) - cx) * scale + cx + dx, (float(y) - cy) * scale + cy + dy)

    node_pts = [(n['id'],) + moved(n['x'], n['y']) for n in nodes]
    seat_pts = [(s['id'],) + moved(s['x'], s['y']) for s in seats]

    # 整组平移修正：bbox 超出画布时，所有点同时挪回去，形状不变
    adjx = adjy = 0.0
    allx = [p[1] for p in node_pts] + [p[1] for p in seat_pts]
    ally = [p[2] for p in node_pts] + [p[2] for p in seat_pts]
    if allx:
        if min(allx) < PAD:
            adjx = PAD - min(allx)
        elif max(allx) > cw - PAD:
            adjx = (cw - PAD) - max(allx)
        if min(ally) < PAD:
            adjy = PAD - min(ally)
        elif max(ally) > ch - PAD:
            adjy = (ch - PAD) - max(ally)

    for nid, x, y in node_pts:
        db.execute('UPDATE nav_nodes SET x=?, y=? WHERE id=?',
                   (round(x + adjx, 1), round(y + adjy, 1), nid))
    for sid, x, y in seat_pts:
        db.execute('UPDATE seats SET x=?, y=? WHERE id=?',
                   (round(x + adjx, 1), round(y + adjy, 1), sid))
    refresh_edges(floor_id)
    return {'nodes': len(node_pts), 'seats': len(seat_pts),
            'applied': {'dx': round(dx + adjx, 1), 'dy': round(dy + adjy, 1), 'scale': scale},
            'clamped': bool(adjx or adjy)}


# ---------------------------------------------------------------------------
# 诊断：连通性 / 孤立点 / 重复边 / 越界
# ---------------------------------------------------------------------------
def components(nodes, edges):
    adj = {n['code']: set() for n in nodes}
    for e in edges:
        if e['from_node'] in adj and e['to_node'] in adj:
            adj[e['from_node']].add(e['to_node'])
            adj[e['to_node']].add(e['from_node'])
    seen, groups = set(), []
    for code in adj:
        if code in seen:
            continue
        stack, comp = [code], []
        seen.add(code)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for nb in adj[cur]:
                if nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        groups.append(comp)
    return adj, groups


def stats(nodes, edges):
    adj, groups = components(nodes, edges)
    isolated = [c for c, nb in adj.items() if not nb]
    deg = {c: len(nb) for c, nb in adj.items()}
    sizes = sorted((len(g) for g in groups), reverse=True)
    # 连通率：最大的那块占总节点数的比例
    ratio = round((sizes[0] / len(nodes) * 100), 1) if nodes and sizes else 0.0
    return {
        'nodes': len(nodes), 'edges': len(edges),
        'components': len(groups),
        'largest_component': sizes[0] if sizes else 0,
        'connected_ratio': ratio,
        'isolated': len(isolated),
        'dead_ends': len([c for c, d in deg.items() if d == 1]),
        'isolated_codes': isolated[:20],
    }


def diagnose(floor_id):
    """返回结构化事实 + 中文建议（不依赖大模型）。"""
    nodes, edges = nodes_of(floor_id), edges_of(floor_id)
    st = stats(nodes, edges)
    cw, ch = canvas_of(floor_id)
    out_of_bounds = [n['code'] for n in nodes
                     if not (0 <= float(n['x']) <= cw and 0 <= float(n['y']) <= ch)]
    dup = set()
    for e in edges:
        key = tuple(sorted((e['from_node'], e['to_node'])))
        if key in dup:
            continue
        pair = [e['from_node'], e['to_node']]
        if pair[0] == pair[1]:
            dup.add(key)
        elif db.one('SELECT COUNT(*) AS c FROM nav_edges WHERE floor_id=? AND '
                    '((from_node=? AND to_node=?) OR (from_node=? AND to_node=?))',
                    (floor_id, pair[0], pair[1], pair[1], pair[0]))['c'] > 1:
            dup.add(key)

    tips = []
    if not nodes:
        tips.append('这一层还没有路网：可以用「从底图生成」或「DXF 生成」，也可以直接点空白画节点。')
    else:
        if st['components'] > 1:
            tips.append('路网被分成了 %d 块，最大一块只占 %s%%，导航会走不到其它区域。'
                        '用「接上断开的部分」一键补齐，或手工连线。' % (st['components'], st['connected_ratio']))
        if st['isolated']:
            tips.append('有 %d 个孤立节点（没有任何连线），删掉或连上。' % st['isolated'])
        if st['dead_ends'] and st['nodes'] > 4:
            tips.append('有 %d 个末端节点，如果不通向入口或座位，可以删掉减少噪声。' % st['dead_ends'])
        if dup:
            tips.append('有 %d 组重复连线，保存时会被合并。' % len(dup))
        if out_of_bounds:
            tips.append('有 %d 个节点超出画布范围，建议框选后整体平移。' % len(out_of_bounds))
        if not tips:
            tips.append('路网连通，没有孤立点或重复边。')
    return {
        'ok': True,
        'facts': st,
        'duplicates': len(dup),
        'out_of_bounds': len(out_of_bounds),
        'tips': tips,
    }


def join_components(floor_id, limit=None):
    """把断开的几块按「最近的两个节点」连起来，返回新增的连线。"""
    nodes, edges = nodes_of(floor_id), edges_of(floor_id)
    _, groups = components(nodes, edges)
    if len(groups) <= 1:
        return []
    pos = {n['code']: (float(n['x']), float(n['y'])) for n in nodes}
    added = []
    # 每次把最大块和离它最近的一块连起来，直到只剩一块
    main = max(groups, key=len)
    main_codes = set(main)
    rest = [set(g) for g in groups if set(g) != main_codes]
    while rest:
        best = None
        for gi in rest:
            for a in main_codes:
                for b in gi:
                    d = math.hypot(pos[a][0] - pos[b][0], pos[a][1] - pos[b][1])
                    if limit and d > limit:
                        continue
                    if best is None or d < best[0]:
                        best = (d, a, b, gi)
        if not best:
            # 剩下的都超过上限，硬连最近的一对
            for gi in rest:
                for a in main_codes:
                    for b in gi:
                        d = math.hypot(pos[a][0] - pos[b][0], pos[a][1] - pos[b][1])
                        if best is None or d < best[0]:
                            best = (d, a, b, gi)
        if not best:
            break
        d, a, b, gi = best
        try:
            link(floor_id, a, b)
            added.append({'from': a, 'to': b, 'distance': round(d, 1)})
        except Exception:
            pass
        main_codes |= gi
        rest = [g for g in rest if g != gi]
    return added
