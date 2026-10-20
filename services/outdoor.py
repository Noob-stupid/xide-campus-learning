# -*- coding: utf-8 -*-
"""室外步行导航：距离 / 方位 / 文字指引 / 手机地图链接。"""
import math

WALK_MPS = 1.25  # 约 4.5 km/h


def haversine(lat1, lng1, lat2, lng2):
    """返回米。"""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bearing(lat1, lng1, lat2, lng2):
    """返回 0-360，0=北，顺时针。"""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lng2 - lng1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def compass(deg):
    names = ['北', '东北', '东', '东南', '南', '西南', '西', '西北']
    return names[int((deg + 22.5) // 45) % 8]


def walk_route(start_lat, start_lng, building):
    lat, lng = float(building['lat']), float(building['lng'])
    dist = round(haversine(start_lat, start_lng, lat, lng))
    deg = round(bearing(start_lat, start_lng, lat, lng))
    mins = max(1, round(dist / WALK_MPS / 60))
    direction = compass(deg)
    steps = [
        '从当前位置向%s方向步行约 %d 米' % (direction, dist),
        '到达%s（%s）' % (building['name'], building.get('address') or '校园内'),
        '进馆后打开「导航」页，选择楼层与座位，继续室内路线',
    ]
    amap = ('https://uri.amap.com/navigation?from=%s,%s,我的位置&to=%s,%s,%s&mode=walk&policy=1&src=xide&coordinate=gaode&callnative=0'
            % (start_lng, start_lat, lng, lat, building['name']))
    return {
        'building': building,
        'distance_m': dist,
        'minutes': mins,
        'bearing': deg,
        'direction': direction,
        'steps': steps,
        'amap_uri': amap,
    }
