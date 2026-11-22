# -*- coding: utf-8 -*-
"""室内路网与 A* 导航。"""
import heapq
import math

import db


def build_graph(floor_id):
    nodes = {r['code']: {'x': r['x'], 'y': r['y'], 'kind': r['kind']}
             for r in db.query('SELECT * FROM nav_nodes WHERE floor_id=?', (floor_id,))}
    adj = {code: [] for code in nodes}
    for e in db.query('SELECT * FROM nav_edges WHERE floor_id=?', (floor_id,)):
        a, b, dist = e['from_node'], e['to_node'], e['distance']
        if a in adj and b in adj:
            adj[a].append((b, dist))
            adj[b].append((a, dist))
    return nodes, adj


def _heuristic(nodes, a, b):
    na, nb = nodes.get(a), nodes.get(b)
    if not na or not nb:
        return 0.0
    return math.hypot(na['x'] - nb['x'], na['y'] - nb['y'])


def _resolve_start(nodes, start_code):
    if start_code in nodes:
        return start_code
    if start_code in (None, '', 'entry'):
        for code, n in nodes.items():
            if n.get('kind') == 'entry':
                return code
        if nodes:
            # 没有显式入口时，取最靠下、最靠中间的点作为默认入口
            W = max(n['x'] for n in nodes.values()) or 0
            H = max(n['y'] for n in nodes.values()) or 0
            return min(nodes, key=lambda c: abs(nodes[c]['x'] - W / 2) + abs(nodes[c]['y'] - H))
    return start_code


def _add_seat_node(floor_id, end_code, nodes, adj):
    """把 s_<座位号> 动态挂到最近的路网节点上，不把 187 个座位塞进路网。"""
    if not end_code.startswith('s_'):
        return end_code
    seat_code = end_code[2:]
    seat = db.one('SELECT * FROM seats WHERE code=? AND floor_id=?', (seat_code, floor_id))
    if not seat:
        return end_code
    nearest, best = None, 1e18
    for code, n in nodes.items():
        d = (n['x'] - seat['x']) ** 2 + (n['y'] - seat['y']) ** 2
        if d < best:
            nearest, best = code, d
    if not nearest:
        return end_code
    nodes[end_code] = {'x': seat['x'], 'y': seat['y'], 'kind': 'seat'}
    dist = math.sqrt(best)
    adj[end_code] = [(nearest, dist)]
    adj[nearest].append((end_code, dist))
    return end_code


def plan_path(floor_id, start_code, end_code, start_xy=None):
    nodes, adj = build_graph(floor_id)
    if start_xy:
        try:
            sx, sy = float(start_xy[0]), float(start_xy[1])
        except Exception:
            sx = sy = None
        if sx is not None and nodes:
            nearest, best = None, 1e18
            for code, n in nodes.items():
                d = (n["x"] - sx) ** 2 + (n["y"] - sy) ** 2
                if d < best:
                    nearest, best = code, d
            if nearest:
                temp = "__temp_start__"
                nodes[temp] = {"x": sx, "y": sy, "kind": "entry"}
                dist = math.sqrt(best)
                adj[temp] = [(nearest, dist)]
                adj[nearest].append((temp, dist))
                start_code = temp
    start_code = _resolve_start(nodes, start_code)
    end_code = _add_seat_node(floor_id, end_code, nodes, adj)
    if start_code not in nodes or end_code not in nodes:
        return {'ok': False, 'error': '起点或终点不存在', 'path': [], 'steps': []}
    if start_code == end_code:
        return {'ok': True, 'path': [{'code': start_code, **nodes[start_code]}],
                'distance': 0, 'minutes': 0, 'steps': ['你已经在目的地']}

    open_heap = [(0.0, start_code)]
    came = {}
    g = {start_code: 0.0}
    while open_heap:
        _, cur = heapq.heappop(open_heap)
        if cur == end_code:
            break
        for nxt, w in adj.get(cur, []):
            ng = g[cur] + w
            if nxt not in g or ng < g[nxt]:
                came[nxt] = cur
                g[nxt] = ng
                heapq.heappush(open_heap, (ng + _heuristic(nodes, nxt, end_code), nxt))

    if end_code not in g:
        return {'ok': False, 'error': '路网未连通，请检查起点与终点', 'path': [], 'steps': []}

    codes = [end_code]
    while codes[-1] != start_code:
        codes.append(came[codes[-1]])
    codes.reverse()
    path = [{'code': c, **nodes[c]} for c in codes]
    dist = g[end_code]
    # 假设 1 像素 ≈ 1.2 厘米，步行 1.1 m/s
    meters = dist * 0.012
    minutes = max(1, round(meters / 1.1 / 60))
    return {
        'ok': True,
        'path': path,
        'distance': round(meters, 1),
        'minutes': minutes,
        'steps': _human_steps(nodes, codes),
    }


def _human_steps(nodes, codes):
    if len(codes) <= 2:
        return ['沿通道直行即可到达']
    steps = []
    prev_dir = None
    for i in range(len(codes) - 1):
        a, b = nodes[codes[i]], nodes[codes[i + 1]]
        dx, dy = b['x'] - a['x'], b['y'] - a['y']
        if abs(dx) > abs(dy):
            d = '向东' if dx > 0 else '向西'
        else:
            d = '向南' if dy > 0 else '向北'
        if d != prev_dir:
            steps.append('%s直行' % d)
            prev_dir = d
    steps.append('到达座位')
    return steps


def nearest_node(floor_id, x, y):
    rows = db.query('SELECT * FROM nav_nodes WHERE floor_id=?', (floor_id,))
    best, best_d = None, 1e18
    for r in rows:
        d = (r['x'] - x) ** 2 + (r['y'] - y) ** 2
        if d < best_d:
            best, best_d = dict(r), d
    return best
