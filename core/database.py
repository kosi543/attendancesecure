"""
core/database.py
================
Data layer for the system.

Your Chapter 1 & 2 and the App Flow specify **Firebase (Firestore)** as
the cloud database. This module talks to Firestore through the official
`firebase-admin` SDK.

So that you can RUN and SEE the app immediately (before creating a
Firebase project), it falls back to a local JSON "demo database" if no
`firebase_credentials.json` is found. The moment you drop your real
service-account file in the project root, it switches to live Firebase:
no code changes needed.

Collections (Firestore) / tables (demo):
    users          -> students, lecturers, admins
    courses        -> course_code, title, total_classes, lecturer_id
    sessions       -> active/closed attendance sessions
    attendance     -> every scan (the "fact table")
    flagged        -> scans needing lecturer review (with reasons)
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Try to initialise real Firebase. Fall back to local JSON if unavailable.
# ---------------------------------------------------------------------------
_CRED_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                          "firebase_credentials.json")
_DEMO_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                          "demo_database.json")

USING_FIREBASE = False
_db = None
_lock = threading.Lock()


def _init_firebase():
    global USING_FIREBASE, _db
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        cred = None
        if os.path.exists(_CRED_FILE):
            cred = credentials.Certificate(_CRED_FILE)
        else:
            try:
                import streamlit as st
                if "firebase" in st.secrets:
                    cred = credentials.Certificate(dict(st.secrets["firebase"]))
            except Exception:
                pass
        if cred is None:
            return False
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        _db = firestore.client()
        USING_FIREBASE = True
        return True
    except Exception as exc:   # noqa: BLE001
        print(f"[database] Firebase unavailable, using demo store: {exc}")
        return False


_init_firebase()


# ===========================================================================
# DEMO (local JSON) backend
# ===========================================================================
_EMPTY_STORE = {"users": {}, "departments": {}, "courses": {}, "sessions": {},
                "attendance": {}, "enrolments": {}, "notifications": {},
                "eligibility_overrides": {}, "flagged": {}}


def _load_demo() -> dict:
    """
    Read the local JSON store.

    If the file is missing, empty, or half-written (which happens if the app
    is stopped in the middle of a save), we do not crash the whole app. The
    damaged file is kept aside as demo_database.corrupt.json and a fresh,
    empty store is used instead.
    """
    if not os.path.exists(_DEMO_FILE) or os.path.getsize(_DEMO_FILE) == 0:
        return dict(_EMPTY_STORE)
    try:
        with open(_DEMO_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError("store is not a JSON object")
        for key in _EMPTY_STORE:
            data.setdefault(key, {})
        return data
    except (json.JSONDecodeError, ValueError) as exc:
        backup = _DEMO_FILE.replace(".json", ".corrupt.json")
        try:
            os.replace(_DEMO_FILE, backup)
            print(f"[database] {exc}. Damaged file kept as {backup}, "
                  f"starting a fresh store.")
        except OSError:
            print(f"[database] {exc}. Starting a fresh store.")
        return dict(_EMPTY_STORE)


def _save_demo(data: dict):
    """
    Write to a temporary file first, then swap it in. The real file is never
    left truncated, so a crash mid-save cannot wipe the database.
    """
    tmp = _DEMO_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, _DEMO_FILE)


# ===========================================================================
# Unified API used by the rest of the app
# ===========================================================================
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def _safe_id(doc_id: str) -> str:
    """
    Firestore treats '/' in a document id as a path separator, so a matric
    number such as SWE/2022/005 would be split into nested subcollections
    rather than stored as one document. The slash is therefore replaced on
    the way in, and put back on the way out by _real_id.
    """
    return str(doc_id).replace("/", "__")


def _real_id(doc_id: str) -> str:
    """Turn a stored Firestore id back into the original key."""
    return str(doc_id).replace("__", "/")


def add_document(collection: str, doc_id: str, data: dict) -> None:
    with _lock:
        if USING_FIREBASE:
            _db.collection(collection).document(_safe_id(doc_id)).set(data)
        else:
            store = _load_demo()
            store.setdefault(collection, {})[doc_id] = data
            _save_demo(store)


def update_document(collection: str, doc_id: str, data: dict) -> None:
    with _lock:
        if USING_FIREBASE:
            _db.collection(collection).document(_safe_id(doc_id)).update(data)
        else:
            store = _load_demo()
            store.setdefault(collection, {}).setdefault(doc_id, {}).update(data)
            _save_demo(store)


def get_document(collection: str, doc_id: str) -> dict | None:
    if USING_FIREBASE:
        snap = _db.collection(collection).document(_safe_id(doc_id)).get()
        return snap.to_dict() if snap.exists else None
    store = _load_demo()
    return store.get(collection, {}).get(doc_id)


def get_collection(collection: str) -> dict:
    """Return {doc_id: data} for the whole collection."""
    if USING_FIREBASE:
        return {_real_id(d.id): d.to_dict()
                for d in _db.collection(collection).stream()}
    return _load_demo().get(collection, {})


def query_where(collection: str, field: str, value) -> dict:
    """Return {doc_id: data} where data[field] == value."""
    items = get_collection(collection)
    return {k: v for k, v in items.items() if v.get(field) == value}


def delete_document(collection: str, doc_id: str) -> None:
    with _lock:
        if USING_FIREBASE:
            _db.collection(collection).document(_safe_id(doc_id)).delete()
        else:
            store = _load_demo()
            store.get(collection, {}).pop(doc_id, None)
            _save_demo(store)


def backend_name() -> str:
    return "Firebase Firestore (live)" if USING_FIREBASE else "Local demo store"