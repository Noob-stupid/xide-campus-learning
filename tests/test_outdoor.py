# -*- coding: utf-8 -*-
from services import outdoor


def test_haversine_distance():
    d = outdoor.haversine(38.3018, 116.8360, 38.3035, 116.8382)
    assert 200 < d < 350


def test_compass_direction():
    assert outdoor.compass(0) == '北'
    assert outdoor.compass(45) == '东北'
    assert outdoor.compass(180) == '南'


def test_walk_route_shape():
    b = {'name': '图书馆', 'lat': 38.3035, 'lng': 116.8382, 'address': '沧州交通学院 · 图书馆'}
    r = outdoor.walk_route(38.3018, 116.8360, b)
    assert r['distance_m'] > 0
    assert r['minutes'] >= 1
    assert r['direction'] in ('北', '东北', '东', '东南', '南', '西南', '西', '西北')
    assert len(r['steps']) == 3
    assert 'uri.amap.com' in r['amap_uri']
