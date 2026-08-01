"""
core/qr_engine.py
=================
Dynamic QR tokenisation (Chapter 3.3.1 / 4.2.1).

Implements the Time-based One-Time Password (TOTP) principle. Every
`QR_REFRESH_SECONDS` (8 s) the lecturer's screen produces a fresh signed
token of the form:

    token = HMAC_SHA256(SecretKey, SessionID + floor(timestamp / 8))

A student can only submit a token that matches the server's current
(or one previous) 8-second window, so a screenshot taken even a few
seconds earlier is already useless.
"""

import time
import hmac
import hashlib
import base64
import io

import qrcode

from config import QR_SECRET_KEY, QR_REFRESH_SECONDS, QR_GRACE_WINDOWS


def _current_window(ts: float | None = None) -> int:
    """Return the integer index of the current 8-second time window."""
    if ts is None:
        ts = time.time()
    return int(ts // QR_REFRESH_SECONDS)


def _sign(session_id: str, window: int) -> str:
    """HMAC-SHA256 of (session_id + window) using the secret key."""
    message = f"{session_id}:{window}".encode("utf-8")
    digest = hmac.new(QR_SECRET_KEY.encode("utf-8"), message, hashlib.sha256).digest()
    # short, URL-safe token
    return base64.urlsafe_b64encode(digest).decode("utf-8")[:24]


def generate_token(session_id: str) -> tuple[str, int]:
    """
    Generate the current dynamic token for a session.
    Returns (token_string, seconds_remaining_in_window).
    """
    now = time.time()
    window = _current_window(now)
    token = _sign(session_id, window)
    # the encoded payload that goes inside the QR image
    payload = f"{session_id}|{window}|{token}"
    seconds_left = QR_REFRESH_SECONDS - int(now % QR_REFRESH_SECONDS)
    return payload, seconds_left


def validate_token(payload: str) -> tuple[bool, str]:
    """
    Validate a scanned payload against the server clock.
    Returns (is_valid, reason).
    """
    try:
        session_id, window_str, token = payload.split("|")
        window = int(window_str)
    except (ValueError, AttributeError):
        return False, "Malformed QR payload"

    current = _current_window()
    # accept the current window and up to QR_GRACE_WINDOWS previous ones
    for w in range(current, current - (QR_GRACE_WINDOWS + 1), -1):
        if hmac.compare_digest(token, _sign(session_id, w)):
            return True, "Valid"
    return False, "QR expired: please rescan the live code"


def session_id_from_payload(payload: str) -> str | None:
    """Pull the session id out of a scanned payload."""
    try:
        return payload.split("|")[0]
    except (ValueError, AttributeError):
        return None


def make_qr_image_b64(payload: str, box_size: int = 10) -> str:
    """Render the payload to a base64 PNG. `box_size` controls how big the
    QR is drawn, so the lecturer can enlarge it for students further away."""
    qr = qrcode.QRCode(box_size=box_size, border=2,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1F2430", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def decode_qr_from_image(image_bytes: bytes) -> str | None:
    """
    Decode a QR code from a photo the STUDENT took with the in-app camera.

    This is the heart of the "attendance is only recorded when the student
    uses the application's built-in scanner" rule: we read the lecturer's
    live code straight out of the captured image. A screenshot taken seconds
    earlier decodes to an expired token and is rejected by validate_token().

    Returns the decoded payload string, or None if no QR was found.
    Uses OpenCV's built-in QRCodeDetector (pure pip, no system libraries).
    """
    try:
        import numpy as np
        import cv2
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        detector = cv2.QRCodeDetector()
        data, points, _ = detector.detectAndDecode(arr)
        return data or None
    except Exception:                   # noqa: BLE001
        return None
