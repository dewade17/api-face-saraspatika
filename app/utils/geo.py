import math

def haversine_m(x1, y1, x2, y2):
    R = 6371000.0
    phi1 = math.radians(y1)
    phi2 = math.radians(y2)
    dphi = math.radians(y2 - y1)
    dlmb = math.radians(x2 - x1)
    a = math.sin(dphi/2.0)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlmb/2.0)**2
    c = 2*math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c
