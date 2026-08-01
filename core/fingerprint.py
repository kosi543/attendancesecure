"""
core/fingerprint.py
===================
Device Identifier: browser fingerprint (Complete App Flow → "Device
Identifier (Browser Fingerprint)").

Why this file matters
---------------------
The old version derived the "device id" from the student's matric number
(md5(matric)). That is NOT a device id at all: the same student always got
the same id on every phone, and two students on ONE shared phone always got
DIFFERENT ids, which makes the "multiple accounts on one device" fraud
check impossible.

This module collects real, device-specific signals from the browser
(user-agent, screen size, timezone, platform, language, hardware) using the
`streamlit-js-eval` bridge and hashes them into one opaque token. Now:

  * the SAME phone produces the SAME token for whoever uses it  -> a proxy
    scanning for several friends is detectable, and
  * a normal student on their own phone gets a stable personal token.

This is exactly the signal the Isolation Forest uses as `device_freq`
(accounts-per-device) and devices-per-account.
"""

from __future__ import annotations

import hashlib
import streamlit as st

try:
    from streamlit_js_eval import streamlit_js_eval
    _JS_OK = True
except Exception:                       # noqa: BLE001
    _JS_OK = False


# The JS expression runs in the student's browser and returns a string of
# stable device/browser characteristics joined by "|".
_FP_JS = (
    "[navigator.userAgent, navigator.platform, navigator.language,"
    " (screen.width + 'x' + screen.height + 'x' + screen.colorDepth),"
    " new Date().getTimezoneOffset(),"
    " (navigator.hardwareConcurrency || 0),"
    " (navigator.deviceMemory || 0)].join('|')"
)


def get_device_fingerprint() -> str:
    """
    Return a stable per-device id, e.g. 'dev-1a2b3c4d5e6f7a8b'.

    Falls back to a per-session random id only if the JS bridge is
    unavailable (so the app still works), but in normal browser use this is
    a genuine device fingerprint.
    """
    if "device_fp" in st.session_state and st.session_state["device_fp"]:
        return st.session_state["device_fp"]

    raw = None
    if _JS_OK:
        try:
            raw = streamlit_js_eval(js_expressions=_FP_JS, key="device_fp_js",
                                    want_output=True)
        except Exception:               # noqa: BLE001
            raw = None

    if raw:
        fp = "dev-" + hashlib.sha256(str(raw).encode("utf-8")).hexdigest()[:16]
    else:
        # JS not ready yet (first render), return None-ish so the caller can
        # wait one rerun rather than baking in a fake id.
        return ""

    st.session_state["device_fp"] = fp
    return fp


def fingerprint_ready() -> bool:
    """True once the browser has reported its fingerprint."""
    return bool(st.session_state.get("device_fp"))
