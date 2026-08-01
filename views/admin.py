"""
views/admin.py
==============
Administrator portal.
  * Small "Private area" login (access key + password)
  * Overview
  * Notifications
  * Departments (add / delete)
  * Look up users: full edit of every field, including the matric number or
    email the record is keyed on, plus a password reset and delete
  * Override eligibility (with a reason)
  * Security: change the admin access key and password, so the system can be
    handed over to a new administrator
"""

import streamlit as st

from core.ui import brand_title, nav_menu, tile, logout_button
import pandas as pd

from core import auth, attendance as att, database as db


def render():
    if not st.session_state.get("auth") or st.session_state.get("role") != "admin":
        _login()
        return
    _dashboard()


# ---------------------------------------------------------------------------
def _login():
    brand_title("Administrator")
    if st.button("← Back", key="a_back"):
        st.session_state["page"] = "intro"; st.rerun()

    # small, quiet "private area" note, not a big glossy panel
    st.markdown(
        "<div style='display:inline-block;background:#4A1023;color:#FFD9E5;"
        "padding:4px 10px;border-radius:6px;font-size:12px;font-weight:600;"
        "letter-spacing:.5px'>PRIVATE AREA</div>",
        unsafe_allow_html=True)
    st.write("")
    key = st.text_input("Admin Pass", placeholder="AS-ADMIN-XXXX")
    pwd = st.text_input("Password", type="password")
    if st.button("Unlock"):
        ok, res = auth.login_admin(key, pwd)
        if ok:
            st.session_state.update(auth=True, role="admin", user=res)
            st.rerun()
        else:
            st.error(res)


# ---------------------------------------------------------------------------
def _dashboard():
    st.sidebar.markdown("**Administrator**")
    logout_button()
    choice = nav_menu(
        ["Overview", "Predictions", "Notifications",
         "Departments", "Look up users", "Override eligibility", "Security"],
        "admin_menu")
    brand_title(choice)

    if choice == "Overview":
        _overview()
    elif choice == "Predictions":
        _predictions()
    elif choice == "Notifications":
        _notifications()
    elif choice == "Departments":
        _departments()
    elif choice == "Look up users":
        _lookup()
    elif choice == "Override eligibility":
        _override_eligibility()
    else:
        _security()


def _overview():
    users = db.get_collection("users")
    students = [u for u in users.values() if u.get("role") == "student"]
    lecturers = [u for u in users.values() if u.get("role") == "lecturer"]
    courses = db.get_collection("courses")
    flagged = [r for r in db.get_collection("attendance").values() if r.get("flagged")]
    c1, c2, c3, c4 = st.columns(4)
    tile(c1, len(students), "Students"); tile(c2, len(lecturers), "Lecturers")
    tile(c3, len(courses), "Courses"); tile(c4, len(flagged), "Flagged")
    st.write("")
    if courses:
        st.dataframe(
            [{"Code": c["course_code"], "Title": c["title"],
              "Department": c.get("department", ""),
              "Lecturer": c.get("lecturer_name") or c["lecturer_id"],
              "Classes": c["total_classes"],
              "Registered": len(att.course_students(cid))}
             for cid, c in courses.items()],
            use_container_width=True, hide_index=True)
    else:
        st.info("No courses yet.")


def _predictions():
    """Every prediction across the institution, at-risk students first."""
    rows = att.list_predictions()
    if not rows:
        st.info("No predictions have been made yet."); return
    at_risk = [r for r in rows if r.get("at_risk")]
    c1, c2 = st.columns(2)
    tile(c1, len(rows), "Assessed"); tile(c2, len(at_risk), "At risk")
    st.write("")
    st.dataframe(
        [{"Name": r.get("name", ""), "Matric": r.get("matric", ""),
          "Course": r.get("course_code", ""),
          "Attendance": f"{r.get('attendance_percent', 0):.0f}%",
          "Eligible": "Yes" if r.get("eligible") else "No",
          "Result": ("At risk" if r.get("at_risk")
                     else "On track" if r.get("eligible") else "Not assessed"),
          "Model": r.get("model") or ","}
         for r in sorted(rows, key=lambda x: not x.get("at_risk"))],
        use_container_width=True, hide_index=True)


def _notifications():
    st.caption("Every important change is recorded here.")
    notes = att.list_notifications()
    if not notes:
        st.info("No notifications yet."); return
    for n in notes:
        st.markdown(
            f"<div class='card'><p style='margin:0'>{n['message']}</p>"
            f"<small style='color:#6B7280'>{n.get('time_iso','')[:19]} • "
            f"by {n.get('actor','system')}</small></div>",
            unsafe_allow_html=True)


def _departments():
    st.caption("Students and lecturers can only register into a department "
               "that exists here, so create these first.")
    with st.expander("Add a department", expanded=True):
        name = st.text_input("Department name", placeholder="Computer Science")
        if st.button("Add"):
            if name.strip():
                did = name.strip().lower().replace(" ", "_")
                db.add_document("departments", did,
                                {"name": name.strip(), "created_at": db.now_iso()})
                att.add_notification(f"Department '{name.strip()}' added.", actor="admin")
                st.success(f"Department '{name}' added."); st.rerun()
            else:
                st.error("Enter a department name.")
    depts = db.get_collection("departments")
    if not depts:
        st.info("No departments yet."); return
    for did, d in depts.items():
        col1, col2 = st.columns([5, 1])
        col1.markdown(f"<div class='card'><b>{d['name']}</b></div>",
                      unsafe_allow_html=True)
        if col2.button("Delete", key=f"deldep_{did}"):
            db.delete_document("departments", did); st.rerun()


def _lookup():
    tab_s, tab_l = st.tabs(["Student", "Lecturer"])
    with tab_s:
        matric = st.text_input("Student matric number", key="adm_matric")
        if st.button("Search student", key="adm_find_s"):
            u = auth.find_student_by_matric(matric)
            st.session_state["found_student"] = u or {}
        u = st.session_state.get("found_student")
        if u:
            _view_student(u)
        elif u == {}:
            st.warning("No student found.")
    with tab_l:
        email = st.text_input("Lecturer email", key="adm_email")
        if st.button("Search lecturer", key="adm_find_l"):
            u = auth.find_lecturer_by_email(email)
            st.session_state["found_lect"] = u or {}
        u = st.session_state.get("found_lect")
        if u:
            _view_lecturer(u)
        elif u == {}:
            st.warning("No lecturer found.")


def _view_student(u):
    st.markdown(f"<div class='card'><b>{u['name']}</b>, Student<br>"
                f"{u['matric']} • {u.get('department','')} • L{u.get('level','')}<br>"
                f"<small style='color:#6B7280'>{u.get('email','')} • "
                f"{u.get('phone','')}</small></div>", unsafe_allow_html=True)

    with st.expander("Edit all details"):
        depts = auth.list_department_names() or [u.get("department", "")]
        levels = ["100", "200", "300", "400", "500"]
        c1, c2 = st.columns(2)
        name = c1.text_input("Full name", value=u.get("name", ""), key="e_s_name")
        matric = c2.text_input("Matric number", value=u.get("matric", ""),
                               key="e_s_matric",
                               help="Changing this moves every attendance and "
                                    "course record with the student.")
        dept = c1.selectbox("Department", depts,
                            index=depts.index(u["department"]) if u.get("department") in depts else 0,
                            key="e_s_dept")
        level = c2.selectbox("Level", levels,
                             index=levels.index(str(u.get("level"))) if str(u.get("level")) in levels else 0,
                             key="e_s_level")
        email = c1.text_input("Email", value=u.get("email", ""), key="e_s_email")
        phone = c2.text_input("Phone", value=u.get("phone", ""), key="e_s_phone")
        if st.button("Save changes", key="e_s_save"):
            ok, msg = auth.update_user(
                u["matric"],
                {"name": name.strip(), "department": dept, "level": level,
                 "email": email.strip().lower(), "phone": phone.strip()},
                new_id=matric.strip())
            (st.success if ok else st.error)(msg)
            if ok:
                st.session_state.pop("found_student", None); st.rerun()

    with st.expander("Reset password"):
        p1 = st.text_input("New password", type="password", key="e_s_p1")
        p2 = st.text_input("Confirm new password", type="password", key="e_s_p2")
        if st.button("Reset password", key="e_s_preset"):
            ok, msg = auth.set_user_password(u["matric"], p1, p2)
            (st.success if ok else st.error)(msg)

    with st.expander("Delete this student"):
        st.caption("This removes the account. Attendance records stay in the "
                   "database for the audit trail.")
        if st.button("Delete student", key="e_s_del"):
            auth.delete_user(u["matric"]); st.warning("Deleted.")
            st.session_state.pop("found_student", None); st.rerun()


def _view_lecturer(u):
    st.markdown(f"<div class='card'><b>{u['name']}</b>, Lecturer<br>"
                f"Staff ID: {u.get('staff_id',':')} • {u.get('department','')}<br>"
                f"<small style='color:#6B7280'>{u.get('email','')} • "
                f"{u.get('phone','')}</small></div>", unsafe_allow_html=True)

    with st.expander("Edit all details"):
        depts = auth.list_department_names() or [u.get("department", "")]
        c1, c2 = st.columns(2)
        name = c1.text_input("Full name", value=u.get("name", ""), key="e_l_name")
        email = c2.text_input("Email", value=u.get("email", ""), key="e_l_email",
                              help="Changing this moves the lecturer's courses "
                                   "and sessions with them.")
        dept = c1.selectbox("Department", depts,
                            index=depts.index(u["department"]) if u.get("department") in depts else 0,
                            key="e_l_dept")
        phone = c2.text_input("Phone", value=u.get("phone", ""), key="e_l_phone")
        staff = c1.text_input("Staff ID", value=u.get("staff_id", ""), key="e_l_staff")
        if st.button("Save changes", key="e_l_save"):
            ok, msg = auth.update_user(
                u["email"],
                {"name": name.strip(), "department": dept,
                 "phone": phone.strip(), "staff_id": staff.strip()},
                new_id=email.strip().lower())
            (st.success if ok else st.error)(msg)
            if ok:
                st.session_state.pop("found_lect", None); st.rerun()

    with st.expander("Reset password"):
        p1 = st.text_input("New password", type="password", key="e_l_p1")
        p2 = st.text_input("Confirm new password", type="password", key="e_l_p2")
        if st.button("Reset password", key="e_l_preset"):
            ok, msg = auth.set_user_password(u["email"], p1, p2)
            (st.success if ok else st.error)(msg)

    with st.expander("Delete this lecturer"):
        if st.button("Delete lecturer", key="e_l_del"):
            auth.delete_user(u["email"]); st.warning("Deleted.")
            st.session_state.pop("found_lect", None); st.rerun()


def _override_eligibility():
    st.caption("Mark a student eligible or not for a course, with a reason.")
    matric = st.text_input("Student matric number")
    course = st.text_input("Course code")
    decision = st.radio("Set to", ["Eligible", "Not eligible"], horizontal=True)
    reason = st.text_area("Reason")
    if st.button("Apply override"):
        if matric and course and reason.strip():
            if not auth.find_student_by_matric(matric):
                st.warning("No student found with that matric number."); return
            att.set_eligibility_override(matric.strip(), course.upper().strip(),
                                         decision == "Eligible", reason.strip())
            st.success(f"Eligibility for {matric} in {course.upper()} set to "
                       f"'{decision}'. Recorded in Notifications.")
        else:
            st.error("Enter matric number, course code, and a reason.")


def _security():
    st.caption("Change the administrator access key and password, for example "
               "when the system is handed over to a new administrator. Both "
               "are stored hashed, never in plain text.")
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    current = st.text_input("Current admin password", type="password",
                            key="sec_cur")
    new_key = st.text_input("New access key (leave blank to keep the current one)",
                            key="sec_key", placeholder="AS-ADMIN-XXXX")
    p1 = st.text_input("New password (leave blank to keep the current one)",
                       type="password", key="sec_p1")
    p2 = st.text_input("Confirm new password", type="password", key="sec_p2")
    if st.button("Update admin credentials"):
        ok, msg = auth.change_admin_credentials(current, new_key, p1, p2)
        if ok:
            st.success(msg)
            st.info("Write the new details down. There is no recovery route "
                    "other than the database.")
        else:
            st.error(msg)
    st.markdown("</div>", unsafe_allow_html=True)