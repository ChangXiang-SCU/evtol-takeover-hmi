# -*- coding: utf-8 -*-
"""地理小工具：经纬度距离 / 方位 / 沿方位推进。"""
import math

EARTH_R_M = 6371000.0


def distance_m(lat1, lng1, lat2, lng2):
    """两点大圆距离（米）。"""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_M * math.asin(math.sqrt(a))


def bearing_deg(lat1, lng1, lat2, lng2):
    """从点1指向点2的初始方位角（度，0=正北）。"""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lng2 - lng1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def move(lat, lng, bearing, dist_m):
    """从(lat,lng)沿bearing推进dist_m米，返回新(lat,lng)。"""
    br = math.radians(bearing)
    p1 = math.radians(lat)
    l1 = math.radians(lng)
    dr = dist_m / EARTH_R_M
    p2 = math.asin(math.sin(p1) * math.cos(dr) + math.cos(p1) * math.sin(dr) * math.cos(br))
    l2 = l1 + math.atan2(math.sin(br) * math.sin(dr) * math.cos(p1),
                         math.cos(dr) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), math.degrees(l2)
