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


def is_within_radius_m(user_lng, user_lat, target_lng, target_lat, radius_m):
    """Return True when user coordinates are inside or on the radius boundary."""
    if radius_m < 0:
        raise ValueError("radius_m must be >= 0")

    distance_m = haversine_m(user_lng, user_lat, target_lng, target_lat)
    return distance_m <= float(radius_m)
