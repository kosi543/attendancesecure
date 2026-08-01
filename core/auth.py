"""
core/auth.py
============
Registration and login for the three roles.

  * STUDENT  registers with: full name, matric number, department, level,
             email (+ confirm), phone (+234), password (+ confirm).
             Logs in with **matric number + password**.

  * LECTURER registers with: full name, school/work email (+ confirm),
             phone (+234), department, password (+ confirm).
             The department must be one the ADMIN has already created, so a
             lecturer can no longer register into a department that does not
             exist. Logs in with **email + password**.

  * ADMIN    does NOT register publicly. Signs in with the secret access key
             + an admin password. Both are kept in the database (hashed) so a
             new administrator can change them from inside the app.

Passwords and the admin access key are stored as salted SHA-256 hashes.
"""

from __future__ import annotations

import hashlib
import os
import re

from core import database as db
from config import (ROLE_STUDENT, ROLE_LECTURER, ROLE_ADMIN,
                    ADMIN_ACCESS_KEY, ADMIN_DEFAULT_PASSWORD, NIGERIA_DIAL_CODE)

ADMIN_DOC_ID = "ADMIN"


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
def hash_password(password: str, salt: str | None = None) -> str:
    if salt is None:
        salt = os.urandom(16).hex()
    h = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"{salt}${h}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$")
    except (ValueError, AttributeError):
        return False
    return hash_password(password, salt) == stored


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email or ""))


def valid_nigerian_phone(phone: str) -> bool:
    """Accept +234XXXXXXXXXX (10 digits after the code)."""
    phone = (phone or "").replace(" ", "")
    return bool(re.match(rf"^\{NIGERIA_DIAL_CODE}\d{{10}}$", phone))


# ---------------------------------------------------------------------------
# Departments (created by the ADMIN only; everyone else picks from this list)
# ---------------------------------------------------------------------------
def list_department_names() -> list:
    """Return the department names the admin has created, sorted."""
    depts = db.get_collection("departments")
    return sorted(d["name"] for d in depts.values())


def departments_exist() -> bool:
    return bool(list_department_names())


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def register_student(name, matric, department, level, email, confirm_email,
                     phone, password, confirm_password) -> tuple[bool, str]:
    if not all([name, matric, department, level, email, phone, password]):
        return False, "Please fill in all fields."
    # the department must be one the admin created
    if department not in list_department_names():
        return False, ("That department does not exist yet. The administrator "
                       "must create it first.")
    if not valid_email(email):
        return False, "Enter a valid email address."
    if email != confirm_email:
        return False, "Email and confirm-email do not match."
    if not valid_nigerian_phone(phone):
        return False, f"Phone must be in the form {NIGERIA_DIAL_CODE}XXXXXXXXXX."
    if password != confirm_password:
        return False, "Passwords do not match."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if db.get_document("users", matric.strip()):
        return False, "A student with this matric number already exists."

    db.add_document("users", matric.strip(), {
        "role": ROLE_STUDENT, "name": name.strip(), "matric": matric.strip(),
        "department": department, "level": level, "email": email.lower(),
        "phone": phone, "password": hash_password(password),
        "created_at": db.now_iso(),
    })
    return True, "Registration successful! You can now log in with your matric number."


def register_lecturer(name, email, confirm_email, phone, department,
                      password, confirm_password) -> tuple[bool, str]:
    if not all([name, email, phone, department, password]):
        return False, "Please fill in all fields."
    # A lecturer can only join a department the administrator has created.
    if not departments_exist():
        return False, ("No departments have been created yet. The "
                       "administrator must add departments before lecturers "
                       "can register.")
    if department not in list_department_names():
        return False, ("That department does not exist. Pick one the "
                       "administrator has created.")
    if not valid_email(email):
        return False, "Enter a valid school/work email address."
    if email != confirm_email:
        return False, "Email and confirm-email do not match."
    if not valid_nigerian_phone(phone):
        return False, f"Phone must be in the form {NIGERIA_DIAL_CODE}XXXXXXXXXX."
    if password != confirm_password:
        return False, "Passwords do not match."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if db.get_document("users", email.lower()):
        return False, "A lecturer with this email already exists."

    # unique staff identifier so a lecturer is never confused with a student
    import random
    staff_id = "CU-LEC-" + "".join(random.choices("0123456789", k=5))

    db.add_document("users", email.lower(), {
        "role": ROLE_LECTURER, "name": name.strip(), "email": email.lower(),
        "phone": phone, "department": department, "staff_id": staff_id,
        "password": hash_password(password), "created_at": db.now_iso(),
    })
    return True, (f"Registration successful! Your staff ID is {staff_id}. "
                  f"You can now log in with your email.")


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
def login_student(matric, password) -> tuple[bool, dict | str]:
    user = db.get_document("users", (matric or "").strip())
    if not user or user.get("role") != ROLE_STUDENT:
        return False, "No student found with that matric number."
    if not verify_password(password, user["password"]):
        return False, "Incorrect password."
    return True, user


def login_lecturer(email, password) -> tuple[bool, dict | str]:
    user = db.get_document("users", (email or "").lower().strip())
    if not user or user.get("role") != ROLE_LECTURER:
        return False, "No lecturer found with that email."
    if not verify_password(password, user["password"]):
        return False, "Incorrect password."
    return True, user


# ---------------------------------------------------------------------------
# Admin credentials: kept in the database so a NEW admin can change them
# ---------------------------------------------------------------------------
def _bootstrap_admin() -> dict:
    """Create the admin record on first use, and back-fill the access key
    for a database that was created before the key became changeable."""
    admin = db.get_document("users", ADMIN_DOC_ID)
    if not admin:
        db.add_document("users", ADMIN_DOC_ID, {
            "role": ROLE_ADMIN, "name": "System Administrator",
            "password": hash_password(ADMIN_DEFAULT_PASSWORD),
            "access_key": hash_password(ADMIN_ACCESS_KEY),
            "created_at": db.now_iso(),
        })
        admin = db.get_document("users", ADMIN_DOC_ID)
    if not admin.get("access_key"):
        db.update_document("users", ADMIN_DOC_ID,
                           {"access_key": hash_password(ADMIN_ACCESS_KEY)})
        admin = db.get_document("users", ADMIN_DOC_ID)
    return admin


def login_admin(access_key, password) -> tuple[bool, dict | str]:
    """Admin's unique login: secret access key + admin password."""
    admin = _bootstrap_admin()
    if not verify_password((access_key or "").strip(), admin["access_key"]):
        return False, "Invalid admin access key."
    if not verify_password(password, admin["password"]):
        return False, "Incorrect admin password."
    return True, admin


def change_admin_credentials(current_password, new_access_key, new_password,
                             confirm_password) -> tuple[bool, str]:
    """
    Hand the system over to a new administrator: change the access key, the
    password, or both. The current password is required either way.
    """
    admin = _bootstrap_admin()
    if not verify_password(current_password, admin["password"]):
        return False, "Current admin password is incorrect."

    changes = {}
    if new_access_key and new_access_key.strip():
        if len(new_access_key.strip()) < 6:
            return False, "The access key must be at least 6 characters."
        changes["access_key"] = hash_password(new_access_key.strip())
    if new_password:
        if new_password != confirm_password:
            return False, "The new passwords do not match."
        if len(new_password) < 6:
            return False, "The new password must be at least 6 characters."
        changes["password"] = hash_password(new_password)

    if not changes:
        return False, "Nothing to change: enter a new access key or password."

    db.update_document("users", ADMIN_DOC_ID, changes)
    _notify("Admin access credentials were changed.")
    what = " and ".join(k.replace("_", " ") for k in changes)
    return True, f"Admin {what} updated. Use the new details at the next login."


# ---------------------------------------------------------------------------
# Admin lookups
#   * a STUDENT is looked up by MATRIC NUMBER
#   * a LECTURER is looked up by EMAIL
# ---------------------------------------------------------------------------
def find_student_by_matric(matric: str) -> dict | None:
    user = db.get_document("users", (matric or "").strip())
    return user if user and user.get("role") == ROLE_STUDENT else None


def find_lecturer_by_email(email: str) -> dict | None:
    user = db.get_document("users", (email or "").lower().strip())
    return user if user and user.get("role") == ROLE_LECTURER else None


# ---------------------------------------------------------------------------
# Admin: full edit, including the matric number / email the record is keyed on
# ---------------------------------------------------------------------------
def _notify(message: str):
    try:
        from core import attendance as att
        att.add_notification(message, actor="admin")
    except Exception:                       # noqa: BLE001
        pass


def _move_student_records(old_matric: str, new_matric: str):
    """Follow a matric number change through every linked record."""
    for aid, rec in db.get_collection("attendance").items():
        if rec.get("matric") == old_matric:
            db.update_document("attendance", aid, {"matric": new_matric})
    for eid, enr in db.get_collection("enrolments").items():
        if enr.get("matric") == old_matric:
            db.update_document("enrolments", eid, {"matric": new_matric})
    for oid, ov in list(db.get_collection("eligibility_overrides").items()):
        if ov.get("matric") == old_matric:
            new_oid = f"{new_matric}::{ov.get('course_code')}"
            ov = dict(ov); ov["matric"] = new_matric; ov["id"] = new_oid
            db.add_document("eligibility_overrides", new_oid, ov)
            db.delete_document("eligibility_overrides", oid)


def _move_lecturer_records(old_email: str, new_email: str):
    """Follow a lecturer email change through courses, sessions, enrolments."""
    for cid, c in db.get_collection("courses").items():
        if c.get("lecturer_id") == old_email:
            db.update_document("courses", cid, {"lecturer_id": new_email})
    for sid, s in db.get_collection("sessions").items():
        if s.get("lecturer_id") == old_email:
            db.update_document("sessions", sid, {"lecturer_id": new_email})
    for eid, e in db.get_collection("enrolments").items():
        if e.get("lecturer_id") == old_email:
            db.update_document("enrolments", eid, {"lecturer_id": new_email})


def update_user(user_id: str, changes: dict, new_id: str | None = None
                ) -> tuple[bool, str]:
    """
    Admin edits a student's or lecturer's stored details.

    If `new_id` is supplied (a corrected matric number or email) the record is
    moved to the new key and every attendance, enrolment, course and session
    row that pointed at the old one is repointed, so nothing is orphaned.
    """
    user = db.get_document("users", user_id)
    if not user:
        return False, "That user no longer exists."

    new_id = (new_id or user_id).strip()
    if user.get("role") == ROLE_LECTURER:
        new_id = new_id.lower()

    data = dict(user)
    data.update(changes)

    if new_id != user_id:
        if not new_id:
            return False, "The matric number / email cannot be empty."
        if db.get_document("users", new_id):
            return False, "That matric number / email is already taken."
        # keep the identifier field itself in step with the new key
        if user.get("role") == ROLE_STUDENT:
            data["matric"] = new_id
        else:
            data["email"] = new_id
        db.add_document("users", new_id, data)
        db.delete_document("users", user_id)
        if user.get("role") == ROLE_STUDENT:
            _move_student_records(user_id, new_id)
        else:
            _move_lecturer_records(user_id, new_id)
        _notify(f"User {user_id} was updated and re-keyed to {new_id}.")
        return True, f"Saved. The record is now filed under {new_id}."

    db.update_document("users", user_id, data)
    _notify(f"User {user_id} details were updated.")
    return True, "Saved."


def set_user_password(user_id: str, new_password: str, confirm: str
                      ) -> tuple[bool, str]:
    """Admin resets a student's or lecturer's password."""
    if not new_password:
        return False, "Enter a new password."
    if new_password != confirm:
        return False, "The passwords do not match."
    if len(new_password) < 6:
        return False, "Password must be at least 6 characters."
    if not db.get_document("users", user_id):
        return False, "That user no longer exists."
    db.update_document("users", user_id, {"password": hash_password(new_password)})
    _notify(f"Password for {user_id} was reset by the administrator.")
    return True, "Password reset."


def delete_user(user_id: str) -> None:
    """Admin removes a student or lecturer account."""
    db.delete_document("users", user_id)
    _notify(f"User {user_id} was deleted.")
