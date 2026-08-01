"""
config.py
=========
Central settings for AttendanceSecure. Everything you might want to change
(app name, colours, QR refresh window, geofence radius, the exam
eligibility threshold, admin access key) lives here so you never have to
dig through the code.
"""

# ---------------------------------------------------------------------------
# App branding
# ---------------------------------------------------------------------------
APP_NAME = "AttendanceSecure"
APP_TAGLINE = "Trusted attendance, early support for every student."

# Brand colours: clean light theme, one calm accent used sparingly.
# Mostly white with a soft pink tint, so it reads simple and human-made.
BRAND_PRIMARY = "#D6336C"     # calm rose accent (not glossy hot-pink)
BRAND_DARK = "#FCFAFB"        # near-white page background (faint warm tint)
BRAND_PANEL = "#FFFFFF"       # white cards
BRAND_LIGHT = "#1F2430"       # near-black text (dark on light)
BRAND_MUTED = "#6B7280"       # muted grey text
BRAND_BORDER = "#ECE7EA"      # soft card border
BRAND_TINT = "#FBEEF3"        # very light pink tint for hover/active
BRAND_OK = "#2ECC71"          # success green
BRAND_DANGER = "#E74C3C"      # warning red

# ---------------------------------------------------------------------------
# Dynamic QR security (dynamic, time-limited codes)
# ---------------------------------------------------------------------------
# The QR token is valid for exactly this many seconds: short enough to defeat
# screenshot sharing, long enough for a slow phone to finish a scan.
QR_REFRESH_SECONDS = 8

# The server also accepts ONE previous window to allow small network/clock delay.
QR_GRACE_WINDOWS = 1

# The whole attendance session stays open for this many minutes, then closes
# automatically so students can't keep scanning forever. The QR still
# refreshes every 8 s within this window.
SESSION_WINDOW_MINUTES = 5

# Secret signing key for the HMAC. In production, read this from an
# environment variable instead of hard-coding it.
QR_SECRET_KEY = "attendancesecure-secret-change-me-in-production"

# ---------------------------------------------------------------------------
# Geofencing (Haversine). Adjustable by the lecturer per session.
# ---------------------------------------------------------------------------
# Default campus centre (Chrisland University, Abeokuta). The lecturer
# overrides this per session by capturing their own GPS.
# PLACEHOLDER ONLY. Replace these with your real classroom coordinates:
# open Google Maps, long-press the room, and copy the two numbers. If a
# session is ever started without capturing a location, this is the centre
# that gets used, and every student will read as kilometres away.
DEFAULT_CAMPUS_LAT = 6.8333
DEFAULT_CAMPUS_LON = 3.1500

# The geofence radius is not locked; the lecturer picks it per session with a
# slider between these bounds (in metres).
GEOFENCE_MIN_RADIUS_M = 20
GEOFENCE_MAX_RADIUS_M = 2000    # ceiling; only needed when the centre is poor
GEOFENCE_DEFAULT_RADIUS_M = 100

# A browser reports how accurate its position is, in metres. A phone on GPS is
# usually 5 - 30 m; a laptop with no GPS chip guesses from WiFi and can be
# hundreds or thousands of metres out. We allow that reported margin on top of
# the radius, but cap it, so a genuinely far-away student is still caught.
GPS_ACCURACY_TOLERANCE_M = 150     # most generous margin we will ever allow
POOR_ACCURACY_WARN_M = 100         # warn the lecturer above this

# ---------------------------------------------------------------------------
# Attendance / eligibility
# ---------------------------------------------------------------------------
EXAM_ELIGIBILITY_PERCENT = 70.0   # >= 70% attendance => eligible to sit exams

# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
ROLE_STUDENT = "student"
ROLE_LECTURER = "lecturer"
ROLE_ADMIN = "admin"

# Admin master key: the "unique" admin login. Admin signs in with this
# secret access key plus a password rather than a public registration.
ADMIN_ACCESS_KEY = "AS-ADMIN-2026"
ADMIN_DEFAULT_PASSWORD = "Asadmin@2026"

# Nigerian phone code for lecturer/student registration validation.
NIGERIA_DIAL_CODE = "+234"