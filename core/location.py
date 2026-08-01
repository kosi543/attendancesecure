"""
core/location.py
================
Real device GPS capture using the browser's Geolocation API through
streamlit-js-eval. When this renders, the browser shows its allow/deny
popup; if allowed, we get latitude/longitude/accuracy for the geofence.

Why the popup sometimes never appears on a phone
------------------------------------------------
Browsers only hand out GPS and camera on a "secure context": an https page,
or http://localhost on the same machine. When a phone opens the app on the
laptop's LAN address (http://192.168.x.x:8501) the browser blocks location
and camera SILENTLY, with no popup at all. That is not an app bug, it is the
browser's rule. `secure_context()` below detects it so the app can say so
plainly instead of leaving the student staring at nothing.

To test on a real phone, serve the app over https, for example:
    streamlit run app.py --server.sslCertFile=cert.pem --server.sslKeyFile=key.pem
or expose it through a https tunnel (ngrok / localtunnel / Streamlit Cloud).
"""

from __future__ import annotations

import streamlit as st

try:
    from streamlit_js_eval import get_geolocation, streamlit_js_eval
    _GEO_OK = True
except Exception:
    _GEO_OK = False


def request_location(key: str = "gps") -> dict | None:
    """
    Ask the browser for the current GPS position.

    Returns {"lat", "lon", "accuracy"} if allowed, or None if denied /
    unavailable. We pass component_key (the argument this library expects)
    so the component renders and the browser popup appears.
    """
    if not _GEO_OK:
        return None

    loc = get_geolocation(component_key=key)

    # The component returns None on the first run (before the user responds);
    # Streamlit reruns automatically once the browser answers.
    if not loc or "coords" not in loc:
        return None

    c = loc["coords"]
    if c.get("latitude") is None or c.get("longitude") is None:
        return None

    return {
        "lat": float(c["latitude"]),
        "lon": float(c["longitude"]),
        "accuracy": float(c.get("accuracy") or 0.0),
    }


def secure_context(key: str = "sec_ctx"):
    """
    True  -> https or localhost, so GPS and camera prompts will appear.
    False -> plain http on an IP address, the browser will block both.
    None  -> the browser has not answered yet (first render).
    """
    if not _GEO_OK:
        return None
    if "is_secure_ctx" in st.session_state:
        return st.session_state["is_secure_ctx"]
    try:
        val = streamlit_js_eval(js_expressions="window.isSecureContext",
                                key=key, want_output=True)
    except Exception:                       # noqa: BLE001
        return None
    if val is None:
        return None
    st.session_state["is_secure_ctx"] = bool(val)
    return bool(val)


def permission_warning(key: str = "sec_ctx"):
    """
    Show a plain warning when the page cannot ask for location or camera.
    Call this at the top of any screen that needs GPS or the camera.
    """
    ctx = secure_context(key)
    if ctx is False:
        st.warning(
            "Your browser will not ask for **location or camera** on this "
            "address, because the page is not on https or localhost. On a "
            "phone, open the app through an https link (or a tunnel such as "
            "ngrok), then the allow/deny popups will appear.")
    return ctx
