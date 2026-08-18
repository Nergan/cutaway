import math
from collections import Counter
from dataclasses import dataclass
from typing import Tuple

GeoPoint = Tuple[float, float]  # (lat, lon)


@dataclass(frozen=True)
class RiskThresholds:
    max_requests_per_second: float = 10.0
    frequency_weight: float = 1.5
    impossible_travel_kmh: float = 900.0  # ~ commercial aircraft cruise speed
    impossible_travel_score: float = 50.0
    min_entropy_ratio: float = 0.2  # normalized 0..1 (fraction of 8 bits/byte)
    low_entropy_score: float = 20.0
    ban_threshold: float = 100.0


def score_request_rate(requests_per_second: float, thresholds: RiskThresholds) -> float:
    if requests_per_second <= thresholds.max_requests_per_second:
        return 0.0
    return requests_per_second * thresholds.frequency_weight


def haversine_km(a: GeoPoint, b: GeoPoint) -> float:
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(h)))


def score_geo_velocity(distance_km: float, elapsed_hours: float, thresholds: RiskThresholds) -> float:
    if elapsed_hours <= 0:
        return 0.0
    speed_kmh = distance_km / elapsed_hours
    return thresholds.impossible_travel_score if speed_kmh > thresholds.impossible_travel_kmh else 0.0


def shannon_entropy_ratio(data: bytes) -> float:
    """Returns entropy normalized to [0, 1] (1.0 == 8 bits/byte, maximally random)."""
    if not data:
        return 0.0
    counts = Counter(data)
    length = len(data)
    bits_per_byte = -sum((c / length) * math.log2(c / length) for c in counts.values())
    return bits_per_byte / 8.0


def score_entropy(entropy_ratio: float, thresholds: RiskThresholds) -> float:
    return thresholds.low_entropy_score if entropy_ratio < thresholds.min_entropy_ratio else 0.0
