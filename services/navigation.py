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


def plan_path(floor_id, start_code, end_code):
    nodes, adj = build_graph(floor_id)
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
            steps.append('向%s直行' % d)
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
