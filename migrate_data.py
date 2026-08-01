"""
migrate_data.py
===============
One-off tidy-up for a database created before courses carried a department
and a lecturer of their own.

It:
  * gives every old course a course_id, a department and the lecturer's name
  * re-keys courses to "CODE::lecturer" so two lecturers never collide
  * points every enrolment at a real course, and deletes enrolments that were
    typed by hand and never belonged to any lecturer
  * points old sessions and attendance rows at the new course ids

Run it once:   python migrate_data.py
"""

from core import database as db
from core import attendance as att


def main():
    users = db.get_collection("users")
    courses = db.get_collection("courses")

    # 1. courses -----------------------------------------------------------
    remap = {}                      # old course id/code -> new course id
    for old_id, c in list(courses.items()):
        lid = c.get("lecturer_id")
        lect = users.get(lid, {})
        new_id = att.course_key(c.get("course_code", old_id), lid)
        data = dict(c)
        data.update({
            "course_id": new_id,
            "course_code": c.get("course_code", old_id).upper().strip(),
            "department": c.get("department") or lect.get("department", ""),
            "lecturer_name": c.get("lecturer_name") or lect.get("name", ""),
        })
        if new_id != old_id:
            db.add_document("courses", new_id, data)
            db.delete_document("courses", old_id)
        else:
            db.update_document("courses", new_id, data)
        remap[old_id] = new_id
        remap[data["course_code"]] = new_id
        print(f"course {old_id} -> {new_id}")

    # 2. enrolments --------------------------------------------------------
    for eid, e in list(db.get_collection("enrolments").items()):
        key = e.get("course_id") or e.get("course_code")
        new_id = remap.get(key)
        if not new_id:
            # a course the student typed that no lecturer ever created
            db.delete_document("enrolments", eid)
            print(f"removed orphan enrolment {e.get('course_code')} "
                  f"for {e.get('matric')}")
            continue
        course = db.get_document("courses", new_id) or {}
        db.update_document("enrolments", eid, {
            "course_id": new_id,
            "course_code": course.get("course_code", e.get("course_code")),
            "title": course.get("title", e.get("title", "")),
            "lecturer_id": course.get("lecturer_id"),
            "lecturer_name": course.get("lecturer_name", ""),
            "department": course.get("department", ""),
        })

    # 3. sessions and attendance ------------------------------------------
    for sid, s in db.get_collection("sessions").items():
        new_id = remap.get(s.get("course_id") or s.get("course_code"))
        if new_id:
            db.update_document("sessions", sid, {"course_id": new_id})
    for aid, r in db.get_collection("attendance").items():
        new_id = remap.get(r.get("course_id") or r.get("course_code"))
        if new_id:
            db.update_document("attendance", aid, {"course_id": new_id})

    print("Done.")


if __name__ == "__main__":
    main()
