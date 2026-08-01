"""
core/attendance.py
==================
Helpers that sit between the UI and the database for courses, sessions,
attendance recording, eligibility, and flagged-scan review.

Two rules drive this module:

  1. A course belongs to ONE lecturer and ONE department. A student can only
     register a course that a lecturer in their own department has created,
     so a student can never end up attached to the wrong lecturer.
  2. A student can only scan a session for a course they actually registered,
     and only from that course's own lecturer.

A scan made from outside the class zone (or with no location shared) is still
recorded, but flagged with the distance so the lecturer can review it rather
than the system silently blocking the student.
"""

from __future__ import annotations

import time

from core import database as db
from config import EXAM_ELIGIBILITY_PERCENT, SESSION_WINDOW_MINUTES


# ---------------------------------------------------------------------------
# Courses
#
# The document id is "CODE::lecturer" so two lecturers can each run their own
# copy of a course code without colliding, and every enrolment points at one
# exact course belonging to one exact lecturer.
# ---------------------------------------------------------------------------
def course_key(code: str, lecturer_id: str) -> str:
    return f"{code.upper().strip()}::{lecturer_id}"


def create_course(lecturer_id, code, title, total_classes,
                  department="", lecturer_name="") -> tuple[bool, str]:
    code = code.upper().strip()
    cid = course_key(code, lecturer_id)
    if db.get_document("courses", cid):
        return False, f"You already have a course with the code {code}."
    db.add_document("courses", cid, {
        "course_id": cid, "course_code": code, "title": title.strip(),
        "total_classes": int(total_classes), "lecturer_id": lecturer_id,
        "lecturer_name": lecturer_name, "department": department,
        "created_at": db.now_iso(),
    })
    return True, cid


def lecturer_courses(lecturer_id) -> dict:
    return db.query_where("courses", "lecturer_id", lecturer_id)


def get_course(course_id) -> dict | None:
    return db.get_document("courses", course_id)


def update_course(course_id, title, total_classes, reason, actor="",
                  new_code=None) -> tuple[bool, str]:
    """
    Lecturer edits a course, and must say why (kept in the notification feed).

    The course code can be corrected too. Because the code forms part of the
    course's key, the record is moved and every enrolment, session and
    attendance row that pointed at it is repointed, so nothing is orphaned.
    """
    course = db.get_document("courses", course_id)
    if not course:
        return False, "That course no longer exists."
    if not title.strip():
        return False, "Enter a course title."
    if not (reason or "").strip():
        return False, "Give a reason for the change."

    new_code = (new_code or course["course_code"]).upper().strip()
    if not new_code:
        return False, "Enter a course code."

    if new_code != course["course_code"]:
        new_id = course_key(new_code, course["lecturer_id"])
        if db.get_document("courses", new_id):
            return False, f"You already have another course coded {new_code}."
        moved = dict(course)
        moved.update({"course_id": new_id, "course_code": new_code,
                      "title": title.strip(),
                      "total_classes": int(total_classes),
                      "updated_at": db.now_iso(),
                      "last_edit_reason": reason.strip()})
        db.add_document("courses", new_id, moved)
        db.delete_document("courses", course_id)
        for eid, e in db.get_collection("enrolments").items():
            if e.get("course_id") == course_id:
                db.update_document("enrolments", eid,
                                   {"course_id": new_id, "course_code": new_code,
                                    "title": title.strip()})
        for sid, sess in db.get_collection("sessions").items():
            if sess.get("course_id") == course_id:
                db.update_document("sessions", sid,
                                   {"course_id": new_id, "course_code": new_code})
        for aid, rec in db.get_collection("attendance").items():
            if rec.get("course_id") == course_id:
                db.update_document("attendance", aid,
                                   {"course_id": new_id, "course_code": new_code})
        add_notification(
            f"Course {course['course_code']} was renamed to {new_code}. "
            f"Reason: {reason.strip()}", actor=actor or course.get("lecturer_id", ""))
        return True, f"Course updated and recoded to {new_code}."

    db.update_document("courses", course_id, {
        "title": title.strip(), "total_classes": int(total_classes),
        "updated_at": db.now_iso(), "last_edit_reason": reason.strip(),
    })
    add_notification(
        f"Course {course['course_code']} was edited "
        f"(title: {title.strip()}, classes: {int(total_classes)}). "
        f"Reason: {reason.strip()}", actor=actor or course.get("lecturer_id", ""))
    return True, "Course updated."


def norm_code(code: str) -> str:
    """Compare course codes without being tripped up by spaces or case, so
    'seg404', 'SEG 404' and 'Seg 404' are all the same course."""
    return "".join((code or "").split()).upper()


def _same_dept(a: str, b: str) -> bool:
    """Compare departments ignoring case and stray spaces, so 'Software
    engineering' and 'Software Engineering' are not treated as two places."""
    return (a or "").strip().lower() == (b or "").strip().lower()


def courses_for_department(department: str) -> dict:
    """
    Courses a student in this department may register. Courses created before
    departments were attached (no department field) stay visible so old data
    still works.
    """
    out = {}
    for cid, c in db.get_collection("courses").items():
        dept = c.get("department")
        if not dept or _same_dept(dept, department):
            out[cid] = c
    return out


def lecturers_in_department(department: str) -> list[dict]:
    """Lecturers registered in this department, used to tell a student who
    they are waiting on when no course has been created yet."""
    return [u for u in db.get_collection("users").values()
            if u.get("role") == "lecturer" and _same_dept(u.get("department"), department)]


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
def open_session(lecturer_id, course_id, class_lat, class_lon, radius_m) -> str:
    course = db.get_document("courses", course_id) or {}
    sid = db.new_id()
    started = time.time()
    db.add_document("sessions", sid, {
        "session_id": sid, "lecturer_id": lecturer_id,
        "course_id": course_id,
        "course_code": course.get("course_code", course_id),
        "class_lat": class_lat, "class_lon": class_lon, "radius_m": radius_m,
        "status": "open", "started_at": started,
        # the session auto-closes after SESSION_WINDOW_MINUTES
        "ends_at": started + SESSION_WINDOW_MINUTES * 60,
        "started_at_iso": db.now_iso(),
    })
    return sid


def seconds_left(session: dict) -> int:
    """Seconds remaining before the window auto-closes (>= 0)."""
    return max(0, int(session.get("ends_at", 0) - time.time()))


def is_expired(session: dict) -> bool:
    return time.time() >= session.get("ends_at", 0)


def close_session(sid):
    db.update_document("sessions", sid, {"status": "closed",
                                         "closed_at_iso": db.now_iso()})


def active_sessions() -> dict:
    """Open sessions that have NOT yet passed their window."""
    open_ = db.query_where("sessions", "status", "open")
    live = {}
    for sid, s in open_.items():
        if is_expired(s):
            close_session(sid)   # window elapsed -> auto-close
        else:
            live[sid] = s
    return live


def sessions_for_student(matric) -> dict:
    """
    Live sessions this student is actually allowed to scan: the course must be
    one they registered, AND the session must be run by that course's lecturer.
    Everything else is invisible to them.
    """
    mine = student_enrolments(matric)
    allowed = {(e.get("course_id") or e.get("course_code"), e.get("lecturer_id"))
               for e in mine.values()}
    out = {}
    for sid, s in active_sessions().items():
        key = (s.get("course_id") or s.get("course_code"), s.get("lecturer_id"))
        if key in allowed:
            out[sid] = s
    return out


# ---------------------------------------------------------------------------
# Attendance recording
# ---------------------------------------------------------------------------
def record_scan(session: dict, student: dict, device_id, ip,
                gps_lat, gps_lon, gps_distance, inside_zone, qr_ok,
                location_shared, reason="", device_known=True) -> str:
    """
    Record one scan. It counts as 'present' only when the live QR was valid
    AND the student was inside the lecturer's zone. Anything else is stored
    as 'flagged' with the reason, for the lecturer to review.
    """
    aid = db.new_id()
    # A device that cannot be fingerprinted is treated the same as any other
    # failed check: recorded, but flagged for the lecturer.
    present = bool(qr_ok and inside_zone and device_known)
    db.add_document("attendance", aid, {
        "attendance_id": aid, "session_id": session["session_id"],
        "course_id": session.get("course_id", session.get("course_code")),
        "course_code": session["course_code"],
        "matric": student["matric"], "name": student["name"],
        "timestamp": time.time(), "timestamp_iso": db.now_iso(),
        "device_id": device_id, "ip": ip,
        "gps_lat": gps_lat, "gps_lon": gps_lon,
        "gps_distance": gps_distance,
        "geofence_ok": bool(inside_zone), "qr_ok": bool(qr_ok),
        "device_known": bool(device_known),
        "location_shared": location_shared,
        "status": "present" if present else "flagged",
        "flagged": (not present),
        "reasons": reason,
        "review": "pending",
    })
    return aid


def already_scanned(session_id, matric) -> bool:
    recs = db.query_where("attendance", "session_id", session_id)
    return any(r.get("matric") == matric for r in recs.values())


def session_scans(session_id) -> dict:
    return db.query_where("attendance", "session_id", session_id)


# ---------------------------------------------------------------------------
# Flagged-scan review (manual, by the lecturer)
# ---------------------------------------------------------------------------
def flagged_for_lecturer(lecturer_id) -> list[dict]:
    """All flagged scans across this lecturer's sessions."""
    sessions = db.query_where("sessions", "lecturer_id", lecturer_id)
    sids = set(sessions.keys())
    out = [rec for rec in db.get_collection("attendance").values()
           if rec.get("session_id") in sids and rec.get("flagged")]
    return sorted(out, key=lambda r: r.get("timestamp", 0), reverse=True)


def set_review(attendance_id, decision):
    """decision: 'confirmed' (genuine) or 'rejected' (removed)."""
    db.update_document("attendance", attendance_id, {"review": decision})


# ---------------------------------------------------------------------------
# Student course registration: pick a real course, from a real lecturer
# ---------------------------------------------------------------------------
def student_join_course(matric, name, course_id, reason) -> tuple[bool, str]:
    """
    A student registers one of the courses a lecturer has already created.
    Because the course carries its lecturer, the student is always attached to
    the correct lecturer, and never to a course they invented themselves.
    """
    course = db.get_document("courses", course_id)
    if not course:
        return False, "Pick a course from the list."
    if not (reason or "").strip():
        return False, "Give a reason for registering this course."

    existing = db.query_where("enrolments", "matric", matric)
    for e in existing.values():
        if (e.get("course_id") or e.get("course_code")) == course_id:
            return False, f"You already registered {course['course_code']}."

    eid = db.new_id()
    db.add_document("enrolments", eid, {
        "id": eid, "matric": matric, "name": name,
        "course_id": course_id, "course_code": course["course_code"],
        "title": course.get("title", ""),
        "lecturer_id": course.get("lecturer_id"),
        "lecturer_name": course.get("lecturer_name", ""),
        "department": course.get("department", ""),
        "reason": reason.strip(), "created_at": db.now_iso(),
    })
    add_notification(
        f"Student {name} ({matric}) registered {course['course_code']} under "
        f"{course.get('lecturer_name') or course.get('lecturer_id')}. "
        f"Reason: {reason.strip()}", actor=matric)
    return True, (f"Registered for {course['course_code']} under "
                  f"{course.get('lecturer_name') or course.get('lecturer_id')}.")


def student_request_course(matric, name, code, title, reason, department=""
                           ) -> tuple[bool, str]:
    """
    A student registers a course the lecturer has NOT created yet.

    The registration is stored as PENDING: it has no lecturer, so it cannot be
    scanned against. The moment a lecturer in the same department creates a
    course with the same code, the registration links itself to that lecturer
    and becomes scannable. If the course already exists, we join it outright
    instead of leaving it hanging.
    """
    code = code.strip()
    if not code or not title.strip():
        return False, "Enter a course code and title."
    if not (reason or "").strip():
        return False, "Give a reason for registering this course."

    # already exists? join the real thing rather than making a duplicate
    matches = [cid for cid, c in courses_for_department(department).items()
               if norm_code(c.get("course_code")) == norm_code(code)]
    if len(matches) == 1:
        return student_join_course(matric, name, matches[0], reason)
    if len(matches) > 1:
        return False, (f"{code.upper()} is taught by more than one lecturer in "
                       f"your department. Pick the right one from the course "
                       f"list above so you are registered under the correct "
                       f"lecturer.")

    # not registered twice, pending or otherwise
    for e in student_enrolments(matric).values():
        if norm_code(e.get("course_code")) == norm_code(code):
            return False, f"You already registered {code.upper()}."

    eid = db.new_id()
    db.add_document("enrolments", eid, {
        "id": eid, "matric": matric, "name": name,
        "course_id": None, "course_code": code.upper(),
        "title": title.strip(), "lecturer_id": None, "lecturer_name": "",
        "department": department, "reason": reason.strip(),
        "pending": True, "created_at": db.now_iso(),
    })
    add_notification(
        f"Student {name} ({matric}) registered {code.upper()} before any "
        f"lecturer created it. Reason: {reason.strip()}", actor=matric)
    return True, (f"{code.upper()} saved. It will link to the lecturer "
                  f"automatically once they create the course. You cannot scan "
                  f"attendance for it until then.")


def link_pending_enrolments(course_id) -> int:
    """
    When a lecturer creates a course, attach the students who had already
    registered that code and were waiting. Only students in the same
    department are attached, so a pending registration never lands under a
    lecturer it has nothing to do with. Returns how many were linked.
    """
    course = db.get_document("courses", course_id)
    if not course:
        return 0
    count = 0
    for eid, e in db.get_collection("enrolments").items():
        if e.get("lecturer_id"):
            continue                                    # already has a lecturer
        if norm_code(e.get("course_code")) != norm_code(course.get("course_code")):
            continue
        if e.get("department") and not _same_dept(e["department"],
                                                  course.get("department", "")):
            continue                                    # different department
        db.update_document("enrolments", eid, {
            "course_id": course_id,
            "course_code": course.get("course_code"),
            "title": course.get("title", e.get("title", "")),
            "lecturer_id": course.get("lecturer_id"),
            "lecturer_name": course.get("lecturer_name", ""),
            "department": course.get("department", ""),
            "pending": False, "linked_at": db.now_iso(),
        })
        count += 1
    return count


def student_enrolments(matric) -> dict:
    return db.query_where("enrolments", "matric", matric)


def update_enrolment(enrolment_id, course_code, title, reason, actor=""
                     ) -> tuple[bool, str]:
    """
    A student edits a course they registered. While it is still waiting for a
    lecturer they may correct the code and title too, because they typed them.
    Once a lecturer owns the course only the reason may change, otherwise a
    student could rename someone else's course.
    """
    enr = db.get_document("enrolments", enrolment_id)
    if not enr:
        return False, "That registration no longer exists."
    if not (reason or "").strip():
        return False, "Give a reason."

    changes = {"reason": reason.strip(), "updated_at": db.now_iso()}
    if not enr.get("lecturer_id"):
        if not (course_code or "").strip() or not (title or "").strip():
            return False, "Enter a course code and title."
        code = course_code.upper().strip()
        for other in student_enrolments(enr["matric"]).values():
            if other["id"] != enrolment_id and \
                    norm_code(other.get("course_code")) == norm_code(code):
                return False, f"You already registered {code}."
        changes["course_code"] = code
        changes["title"] = title.strip()

    db.update_document("enrolments", enrolment_id, changes)
    add_notification(
        f"{enr.get('name')} ({enr.get('matric')}) updated "
        f"{changes.get('course_code', enr.get('course_code'))}. "
        f"Reason: {reason.strip()}", actor=actor or enr.get("matric", ""))
    return True, "Updated."


def update_enrolment_reason(enrolment_id, reason, actor="") -> tuple[bool, str]:
    """A student edits the reason attached to a course they registered."""
    enr = db.get_document("enrolments", enrolment_id)
    if not enr:
        return False, "That registration no longer exists."
    if not (reason or "").strip():
        return False, "Give a reason."
    db.update_document("enrolments", enrolment_id,
                       {"reason": reason.strip(), "updated_at": db.now_iso()})
    add_notification(
        f"{enr.get('name')} ({enr.get('matric')}) changed the reason for "
        f"{enr.get('course_code')} to: {reason.strip()}",
        actor=actor or enr.get("matric", ""))
    return True, "Updated."


def drop_enrolment(enrolment_id, reason, actor="") -> tuple[bool, str]:
    """A student removes a course they registered, with a reason."""
    enr = db.get_document("enrolments", enrolment_id)
    if not enr:
        return False, "That registration no longer exists."
    if not (reason or "").strip():
        return False, "Give a reason for dropping the course."
    db.delete_document("enrolments", enrolment_id)
    add_notification(
        f"{enr.get('name')} ({enr.get('matric')}) dropped "
        f"{enr.get('course_code')}. Reason: {reason.strip()}",
        actor=actor or enr.get("matric", ""))
    return True, f"{enr.get('course_code')} removed."


def course_students(course_id) -> list[dict]:
    """Only the students who registered THIS course under THIS lecturer."""
    out = [e for e in db.get_collection("enrolments").values()
           if (e.get("course_id") or e.get("course_code")) == course_id]
    return sorted(out, key=lambda e: e.get("name", ""))


# ---------------------------------------------------------------------------
# Eligibility (>= 70% attendance), with the admin override applied
# ---------------------------------------------------------------------------
def attendance_summary(matric) -> list[dict]:
    """
    Per-course attendance % and eligibility, for the courses this student
    actually registered (not every course in the system).
    """
    recs = db.query_where("attendance", "matric", matric)
    enrols = student_enrolments(matric)

    # distinct sessions counted per course
    by_course: dict[str, set] = {}
    for r in recs.values():
        if r.get("review") == "rejected":
            continue                       # lecturer removed this scan
        counted = (r.get("status") == "present") or (r.get("review") == "confirmed")
        if not counted:
            continue                       # still pending review, doesn't count yet
        key = r.get("course_id") or r.get("course_code")
        by_course.setdefault(key, set()).add(r["session_id"])

    summary = []
    for e in enrols.values():
        cid = e.get("course_id")
        if not cid:
            # registered before the lecturer created the course: nothing to
            # count yet, so show it as waiting rather than as 0% attendance
            summary.append({
                "course_id": None, "course_code": e.get("course_code", ""),
                "title": e.get("title", ""), "lecturer": "Awaiting lecturer",
                "attended": 0, "total": 0, "percent": 0.0,
                "eligible": False, "pending": True,
                "note": "Waiting for a lecturer to create this course.",
            })
            continue
        course = db.get_document("courses", cid) or {}
        attended = len(by_course.get(cid, set()))
        total = max(int(course.get("total_classes", e.get("total_classes", 1)) or 1), 1)
        pct = round(attended / total * 100, 1)
        eligible = pct >= EXAM_ELIGIBILITY_PERCENT
        note = ""
        override = get_eligibility_override(matric, e.get("course_code", ""))
        if override:
            eligible = bool(override.get("eligible"))
            note = f"Administrator override: {override.get('reason','')}"
        summary.append({
            "course_id": cid,
            "course_code": e.get("course_code", cid),
            "title": course.get("title", e.get("title", "")),
            "lecturer": course.get("lecturer_name") or e.get("lecturer_name")
                        or e.get("lecturer_id", ""),
            "attended": attended, "total": total, "percent": pct,
            "eligible": eligible, "pending": False, "note": note,
        })
    return sorted(summary, key=lambda s: s["course_code"])


# ---------------------------------------------------------------------------
# Notifications (admin sees every important system change)
# ---------------------------------------------------------------------------
def add_notification(message: str, actor: str = "system") -> None:
    nid = db.new_id()
    db.add_document("notifications", nid, {
        "id": nid, "message": message, "actor": actor,
        "time_iso": db.now_iso(), "read": False,
    })


def list_notifications() -> list:
    """All notifications, newest first."""
    items = list(db.get_collection("notifications").values())
    return sorted(items, key=lambda n: n.get("time_iso", ""), reverse=True)


# ---------------------------------------------------------------------------
# Admin: override a student's eligibility for a course (with a reason)
# ---------------------------------------------------------------------------
def set_eligibility_override(matric, course_code, eligible: bool, reason: str):
    oid = f"{matric}::{course_code}"
    db.add_document("eligibility_overrides", oid, {
        "id": oid, "matric": matric, "course_code": course_code,
        "eligible": eligible, "reason": reason, "time_iso": db.now_iso(),
    })
    add_notification(
        f"Admin overrode eligibility for {matric} in {course_code} to "
        f"{'ELIGIBLE' if eligible else 'NOT eligible'}. Reason: {reason}",
        actor="admin")


def get_eligibility_override(matric, course_code):
    return db.get_document("eligibility_overrides", f"{matric}::{course_code}")

# ---------------------------------------------------------------------------
# Academic features used by the prediction layer
#
# Attendance comes from the system's own scan records. The other three
# features are entered once by the student and stored on their record.
# ---------------------------------------------------------------------------
def save_academic_features(matric, prior_gpa, test_score, assignment_rate):
    db.update_document("users", matric, {
        "prior_gpa": float(prior_gpa),
        "test_score": float(test_score),
        "assignment_rate": float(assignment_rate),
        "features_updated": db.now_iso(),
    })


def get_academic_features(matric) -> dict:
    user = db.get_document("users", matric) or {}
    return {"prior_gpa": user.get("prior_gpa"),
            "test_score": user.get("test_score"),
            "assignment_rate": user.get("assignment_rate")}


def save_prediction(matric, name, course_code, result):
    """Keep the latest prediction per student per course, and tell the admin
    when a student is flagged as at risk."""
    pid = f"{matric}::{course_code}"
    db.add_document("predictions", pid, {
        "id": pid, "matric": matric, "name": name,
        "course_code": course_code,
        "attendance_percent": result.get("attendance_percent"),
        "eligible": result.get("eligible"),
        "at_risk": result.get("at_risk"),
        "probability": result.get("probability"),
        "model": result.get("model"),
        "advice": result.get("advice", []),
        "time_iso": db.now_iso(),
    })
    if result.get("at_risk"):
        add_notification(
            f"{name} ({matric}) is flagged AT RISK in {course_code} "
            f"({result.get('model')}, probability "
            f"{result.get('probability', 0):.0%}).", actor="prediction")


def list_predictions() -> list:
    return sorted(db.get_collection("predictions").values(),
                  key=lambda p: p.get("time_iso", ""), reverse=True)


def predictions_for_course(course_code) -> list:
    return [p for p in db.get_collection("predictions").values()
            if p.get("course_code") == course_code]


# ---------------------------------------------------------------------------
# Assignments
#
# The lecturer creates an assignment for a course, then ticks the students who
# submitted it. The submission rate is worked out by the system, so a student
# never has to type a figure they could not possibly know.
# ---------------------------------------------------------------------------
def create_assignment(course_id, title, lecturer_id):
    course = db.get_document("courses", course_id) or {}
    aid = db.new_id()
    db.add_document("assignments", aid, {
        "id": aid, "course_id": course_id,
        "course_code": course.get("course_code", ""),
        "title": title.strip(), "lecturer_id": lecturer_id,
        "created_at": db.now_iso(),
    })
    add_notification(f"Assignment '{title.strip()}' added to "
                     f"{course.get('course_code','')}.", actor=lecturer_id)
    return aid


def course_assignments(course_id) -> list:
    items = [a for a in db.get_collection("assignments").values()
             if a.get("course_id") == course_id]
    return sorted(items, key=lambda a: a.get("created_at", ""))


def delete_assignment(assignment_id):
    for sid, s in list(db.get_collection("submissions").items()):
        if s.get("assignment_id") == assignment_id:
            db.delete_document("submissions", sid)
    db.delete_document("assignments", assignment_id)


def set_submission(assignment_id, matric, submitted: bool):
    """Tick or untick one student for one assignment."""
    sid = f"{assignment_id}::{matric}"
    db.add_document("submissions", sid, {
        "id": sid, "assignment_id": assignment_id, "matric": matric,
        "submitted": bool(submitted), "time_iso": db.now_iso(),
    })


def has_submitted(assignment_id, matric) -> bool:
    rec = db.get_document("submissions", f"{assignment_id}::{matric}")
    return bool(rec and rec.get("submitted"))


def assignment_rate(matric, course_id) -> tuple[float, int, int]:
    """
    Returns (percentage, submitted, total) for one student on one course.
    With no assignments set yet, the rate is reported as 0 of 0.
    """
    items = course_assignments(course_id)
    if not items:
        return 0.0, 0, 0
    done = sum(1 for a in items if has_submitted(a["id"], matric))
    return round(done / len(items) * 100, 1), done, len(items)


def last_session_zones(matric) -> dict:
    """
    The most recent session for each course this student registered, live or
    closed. Used by "Test my location" so a student can check they are inside
    the boundary before the class starts.
    """
    mine = student_enrolments(matric)
    allowed = {(e.get("course_id"), e.get("lecturer_id"))
               for e in mine.values() if e.get("lecturer_id")}
    latest: dict = {}
    for sid, s in db.get_collection("sessions").items():
        key = (s.get("course_id"), s.get("lecturer_id"))
        if key not in allowed:
            continue
        seen = latest.get(key)
        if not seen or s.get("started_at", 0) > seen.get("started_at", 0):
            latest[key] = s
    return {s["session_id"]: s for s in latest.values()}