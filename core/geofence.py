"""
core/geofence.py
================
Geofencing via the Haversine formula (Chapter 3.3.3).

IMPORTANT DESIGN CHANGE (per your correction):
The geofence is NOT locked, and a student who scans from outside the
zone is NOT silently removed. Instead `check_location` returns a
structured result that lets the caller:

  * still record the scan, and
  * FLAG it with a human-readable reason ("Outside classroom geofence: 320 m away")

so the lecturer reviews flagged students rather than the system quietly
blocking them. The lecturer also sets the radius per session, so a big
lecture hall can use a 150 - 300 m radius while a small room uses 30 m.
"""

import math
from dataclasses import dataclass

from config import GEOFENCE_DEFAULT_RADIUS_M, GPS_ACCURACY_TOLERANCE_M

EARTH_RADIUS_M = 6_371_000  # metres


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in METRES."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (math.sin(d_phi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_M * c


@dataclass
class GeofenceResult:
    inside: bool
    distance_m: float
    radius_m: float
    reason: str | None  # populated only when outside
    tolerance_m: float = 0.0  # margin allowed for GPS error


def check_location(student_lat: float | None,
                   student_lon: float | None,
                   class_lat: float,
                   class_lon: float,
                   radius_m: float = GEOFENCE_DEFAULT_RADIUS_M,
                   accuracy_m: float = 0.0) -> GeofenceResult:
    """
    Compare the student's GPS against the lecturer-defined classroom zone.

    The browser tells us how accurate the reading is (`accuracy_m`), and we
    allow that margin on top of the radius. A phone sitting in the classroom
    but reporting itself 40 m out is then still counted as inside, instead of
    forcing the lecturer to set an unrealistic radius of several kilometres.

    The margin is capped at GPS_ACCURACY_TOLERANCE_M, so a device claiming to
    be accurate to 3 km cannot wave a student in from across town.

    If GPS is missing we treat it as a soft flag (location not shared)
    rather than a hard block.
    """
    if student_lat is None or student_lon is None:
        return GeofenceResult(
            inside=False, distance_m=-1.0, radius_m=radius_m,
            reason="Location not shared (GPS disabled)"
        )

    tolerance = min(max(float(accuracy_m or 0.0), 0.0), GPS_ACCURACY_TOLERANCE_M)
    dist = haversine_distance_m(student_lat, student_lon, class_lat, class_lon)

    if dist <= radius_m + tolerance:
        return GeofenceResult(inside=True, distance_m=dist,
                              radius_m=radius_m, reason=None,
                              tolerance_m=tolerance)

    return GeofenceResult(
        inside=False, distance_m=dist, radius_m=radius_m,
        tolerance_m=tolerance,
        reason=f"Outside classroom geofence: {dist:.0f} m away "
               f"(allowed radius {radius_m:.0f} m "
               f"plus {tolerance:.0f} m for GPS error)"
    )