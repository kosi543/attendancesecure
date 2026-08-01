"""
views/lecturer.py
=================
Lecturer portal.
  * Register / login with email. The department is a dropdown of the
    departments the ADMIN created, so a lecturer cannot register into a
    department that does not exist.
  * Courses: create, and edit (title / number of classes) with a reason.
  * Live session: allow location, set the zone, start; the QR refreshes
    every 8s with a size slider to enlarge it.
  * Flagged students (Confirm / Reject), showing how far outside they were.
  * Reports: only the students who registered THAT course under THIS lecturer.
  * At-risk prediction (placeholder)
"""

import streamlit as st

from core.ui import brand_title, nav_menu, tile, logout_button
from core import auth, attendance as att, qr_engine, database as db
from core.location import request_location, permission_warning
from config import (NIGERIA_DIAL_CODE, GEOFENCE_MIN_RADIUS_M,
                    GEOFENCE_MAX_RADIUS_M, GEOFENCE_DEFAULT_RADIUS_M,
                    DEFAULT_CAMPUS_LAT, DEFAULT_CAMPUS_LON, QR_REFRESH_SECONDS)

COURSE_REASONS = ["Assigned lecturer", "Taking over course", "Co-teaching", "Other"]


def render():
    if not st.session_state.get("auth") or st.session_state.get("role") != "lecturer":
        _auth_screen()
        return
    _dashboard()


# ---------------------------------------------------------------------------
def _auth_screen():
    brand_title("Lecturer portal")
    if st.button("← Back", key="l_back"):
        st.session_state["page"] = "intro"; st.rerun()

    tab_login, tab_reg = st.tabs(["Login", "Register"])
    with tab_login:
        email = st.text_input("School / work email", key="l_login_email")
        pwd = st.text_input("Password", type="password", key="l_login_pwd")
        if st.button("Log in", key="l_login_btn"):
            ok, res = auth.login_lecturer(email, pwd)
            if ok:
                st.session_state.update(auth=True, role="lecturer", user=res)
                st.rerun()
            else:
                st.error(res)
    with tab_reg:
        departments = auth.list_department_names()
        if not departments:
            # a lecturer can no longer register before the admin sets up
            # the departments
            st.info("Registration opens once the administrator has added "
                    "departments.")
            return
        c1, c2 = st.columns(2)
        name = c1.text_input("Full name", key="l_name")
        dept = c2.selectbox("Department", departments, key="l_dept")
        email = c1.text_input("School / work email", key="l_email")
        cemail = c2.text_input("Confirm email", key="l_cemail")
        phone = c1.text_input(f"Phone ({NIGERIA_DIAL_CODE}...)",
                              value=NIGERIA_DIAL_CODE, key="l_phone")
        pwd = c1.text_input("Password", type="password", key="l_pwd")
        cpwd = c2.text_input("Confirm password", type="password", key="l_cpwd")
        if st.button("Register", key="l_reg_btn"):
            ok, msg = auth.register_lecturer(name, email, cemail, phone, dept,
                                             pwd, cpwd)
            (st.success if ok else st.error)(msg)


# ---------------------------------------------------------------------------
def _dashboard():
    user = st.session_state["user"]
    st.sidebar.markdown(f"**{user['name']}**")
    st.sidebar.caption(f"{user.get('department','')} • {user['email']}")
    logout_button()

    choice = nav_menu(
        ["Courses", "Live session", "Assignments", "Flagged students",
         "Reports", "At-risk prediction"], "lecturer_menu")
    brand_title(choice)
    lid = user["email"]

    if choice == "Courses":
        _courses(user)
    elif choice == "Live session":
        _live_session(lid)
    elif choice == "Assignments":
        _assignments(lid)
    elif choice == "Flagged students":
        _flagged(lid)
    elif choice == "Reports":
        _reports(lid)
    else:
        _at_risk(lid)


def _courses(user):
    lid = user["email"]
    with st.expander("Create a course"):
        c1, c2, c3 = st.columns(3)
        code = c1.text_input("Course code", placeholder="CSC401")
        title = c2.text_input("Course title", placeholder="Machine Learning")
        total = c3.number_input("Total classes", 1, 60, 24)
        st.caption(f"This course will belong to your department: "
                   f"{user.get('department',',')}. Only students in that "
                   f"department can register it.")
        st.write("Reason")
        if "l_course_reason" not in st.session_state:
            st.session_state.l_course_reason = COURSE_REASONS[0]
        rc = st.columns(len(COURSE_REASONS))
        for i, r in enumerate(COURSE_REASONS):
            mark = f"● {r}" if st.session_state.l_course_reason == r else r
            if rc[i].button(mark, key=f"lrsn_{r}"):
                st.session_state.l_course_reason = r; st.rerun()
        if st.button("Create course", key="l_course_create"):
            if code and title:
                ok, res = att.create_course(lid, code, title, total,
                                            department=user.get("department", ""),
                                            lecturer_name=user.get("name", ""))
                if ok:
                    # students who registered this code while waiting for a
                    # lecturer are attached now
                    linked = att.link_pending_enrolments(res)
                    att.add_notification(
                        f"Lecturer {user.get('name')} ({lid}) created course "
                        f"{code.upper()} in {user.get('department','')}. "
                        f"Reason: {st.session_state.l_course_reason}", actor=lid)
                    msg = f"Course {code.upper()} created."
                    if linked:
                        msg += (f" {linked} student(s) who had already "
                                f"registered this code are now linked to you.")
                    else:
                        msg += " Your students can now register it."
                    st.success(msg); st.rerun()
                else:
                    st.error(res)
            else:
                st.error("Enter a course code and title.")

    courses = att.lecturer_courses(lid)
    if not courses:
        st.info("No courses yet.")
        return
    for cid, c in courses.items():
        enrolled = len(att.course_students(cid))
        st.markdown(
            f"<div class='card'><b>{c['course_code']}</b>, {c['title']}"
            f"<br><small style='color:#6B7280'>{c['total_classes']} classes • "
            f"{c.get('department','')} • {enrolled} student(s) registered"
            f"</small></div>", unsafe_allow_html=True)

        # Edit / delete, both need a reason
        with st.expander(f"Edit {c['course_code']}"):
            e1, e2, e3 = st.columns(3)
            new_code = e1.text_input("Course code",
                                     value=c.get("course_code", ""),
                                     key=f"cc_{cid}")
            new_title = e2.text_input("Course title", value=c.get("title", ""),
                                      key=f"ct_{cid}")
            new_total = e3.number_input("Total classes", 1, 60,
                                        int(c.get("total_classes", 24)),
                                        key=f"cn_{cid}")
            reason = st.text_input("Reason for the change", key=f"cr_{cid}",
                                   placeholder="e.g. two extra classes added")
            b1, b2 = st.columns(2)
            if b1.button("Save changes", key=f"cs_{cid}"):
                ok, msg = att.update_course(cid, new_title, new_total, reason,
                                            actor=lid, new_code=new_code)
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()
            if b2.button("Delete course", key=f"del_{cid}"):
                if not reason.strip():
                    st.error("Give a reason before deleting the course.")
                else:
                    db.delete_document("courses", cid)
                    att.add_notification(
                        f"Course {c['course_code']} was deleted by {lid}. "
                        f"Reason: {reason.strip()}", actor=lid)
                    st.warning("Course deleted."); st.rerun()



def _live_session(lid):
    courses = att.lecturer_courses(lid)
    if not courses:
        st.info("Create a course first."); return

    my_open = {sid: s for sid, s in att.active_sessions().items()
               if s["lecturer_id"] == lid}

    if not my_open:
        permission_warning()
        picks = {f"{c["course_code"]}, {c["title"]}": cid
                 for cid, c in courses.items()}
        label = st.selectbox("Course", list(picks.keys()))
        course_id = picks[label]

        # One tap sets a flag; the component then renders so the browser
        # popup appears (rendering inside the click would flash and vanish).
        if st.button("Allow / use my location as the class centre"):
            st.session_state["lec_loc_on"] = True
        if st.session_state.get("lec_loc_on"):
            here = request_location(key="lecturer_gps")
            if here:
                st.session_state["lec_lat"] = here["lat"]
                st.session_state["lec_lon"] = here["lon"]
                st.success("Location captured for this class.")
            else:
                st.info("Allow location in your browser when the popup appears.")

        lat = float(st.session_state.get("lec_lat", DEFAULT_CAMPUS_LAT))
        lon = float(st.session_state.get("lec_lon", DEFAULT_CAMPUS_LON))
        with st.expander("Adjust coordinates manually"):
            lat = st.number_input("Latitude", value=lat, format="%.5f")
            lon = st.number_input("Longitude", value=lon, format="%.5f")

        radius = st.slider("Geofence (metres)", GEOFENCE_MIN_RADIUS_M,
                           GEOFENCE_MAX_RADIUS_M, GEOFENCE_DEFAULT_RADIUS_M, 5)

        if st.button("Start session", use_container_width=True):
            att.open_session(lid, course_id, lat, lon, radius)
            st.rerun()
        return

    sid, session = next(iter(my_open.items()))
    st.success(f"Live: {session['course_code']} • zone {session['radius_m']} m")

    size = st.slider("QR size", 6, 18, 10,
                     help="Drag to enlarge the code for students further away.")
    _live_qr_fragment(sid, size)

    scans = att.session_scans(sid)
    present = sum(1 for r in scans.values() if r.get("status") == "present")
    flagged = len(scans) - present
    c1, c2, c3 = st.columns(3)
    tile(c1, len(scans), "Total"); tile(c2, present, "Present"); tile(c3, flagged, "Flagged")

    # live list, so the lecturer sees who is inside and who is outside
    if scans:
        rows = []
        for r in sorted(scans.values(), key=lambda x: x.get("timestamp", 0)):
            d = r.get("gps_distance", -1)
            where = "Not shared" if d is None or d < 0 else f"{d:.0f} m away"
            rows.append({
                "Name": r.get("name", ""), "Matric": r.get("matric", ""),
                "Zone": "Inside" if r.get("geofence_ok") else "Outside",
                "Distance": where,
                "Status": r.get("status", ""),
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)

    if st.button("End session now", use_container_width=True):
        att.close_session(sid); st.success("Session closed."); st.rerun()


@st.fragment(run_every="1s")
def _live_qr_fragment(sid, size):
    session = db.get_document("sessions", sid)
    if not session or session.get("status") != "open":
        return
    left = att.seconds_left(session)
    if left <= 0:
        att.close_session(sid); st.rerun(scope="app"); return
    payload, secs = qr_engine.generate_token(sid)
    b64 = qr_engine.make_qr_image_b64(payload, box_size=size)
    mins, s = divmod(left, 60)
    st.markdown(
        f"<div class='card' style='text-align:center'>"
        f"<img src='data:image/png;base64,{b64}' width='{size*22}'/>"
        f"<div style='color:#D6336C;font-weight:700'>Refreshes in {secs}s</div>"
        f"<div style='color:#E03131;font-weight:600'>Session ends in {mins}:{s:02d}</div>"
        f"</div>", unsafe_allow_html=True)


def _assignments(lid):
    """
    Create an assignment, then tick the students who submitted it. The system
    works out each student's submission rate from these ticks, so students
    never have to report it themselves.
    """
    courses = att.lecturer_courses(lid)
    if not courses:
        st.info("Create a course first."); return

    picks = {f"{c["course_code"]}, {c["title"]}": cid
             for cid, c in courses.items()}
    label = st.selectbox("Course", list(picks.keys()))
    course_id = picks[label]

    with st.expander("Add an assignment"):
        title = st.text_input("Assignment title", placeholder="Assignment 1")
        if st.button("Add assignment"):
            if title.strip():
                att.create_assignment(course_id, title, lid)
                st.success("Added."); st.rerun()
            else:
                st.error("Enter a title.")

    items = att.course_assignments(course_id)
    students = att.course_students(course_id)
    if not items:
        st.info("No assignments yet."); return
    if not students:
        st.info("No student has registered this course yet."); return

    for a in items:
        done = sum(1 for st_ in students if att.has_submitted(a["id"], st_["matric"]))
        with st.expander(f"{a['title']}, {done} of {len(students)} submitted"):
            for st_ in students:
                current = att.has_submitted(a["id"], st_["matric"])
                ticked = st.checkbox(f"{st_.get('name','')} ({st_['matric']})",
                                     value=current,
                                     key=f"sub_{a['id']}_{st_['matric']}")
                if ticked != current:
                    att.set_submission(a["id"], st_["matric"], ticked)
                    st.rerun()
            if st.button("Delete this assignment", key=f"da_{a['id']}"):
                att.delete_assignment(a["id"]); st.rerun()


def _flagged(lid):
    st.caption("Scans made outside the zone, with no location, or with an "
               "expired code.")
    items = att.flagged_for_lecturer(lid)
    pending = [r for r in items if r.get("review") == "pending"]
    if not pending:
        st.success("No flagged students pending review."); return
    for r in pending:
        d = r.get("gps_distance", -1)
        where = ("location not shared" if d is None or d < 0
                 else f"{d:.0f} m from the class centre")
        st.markdown(
            f"<div class='card'><b>{r['name']}</b> ({r['matric']}), "
            f"{r['course_code']}<br><span class='bad'>Reason: "
            f"{r.get('reasons') or 'flagged'}</span>"
            f"<br><small style='color:#6B7280'>Recorded {where} • "
            f"{r.get('timestamp_iso','')[:19]}</small></div>",
            unsafe_allow_html=True)
        c1, c2, _ = st.columns([1, 1, 4])
        if c1.button("Confirm", key=f"ok_{r['attendance_id']}"):
            att.set_review(r["attendance_id"], "confirmed"); st.rerun()
        if c2.button("Reject", key=f"no_{r['attendance_id']}"):
            att.set_review(r["attendance_id"], "rejected"); st.rerun()


def _reports(lid):
    courses = att.lecturer_courses(lid)
    if not courses:
        st.info("No courses yet."); return

    picks = {f"{c["course_code"]}, {c["title"]}": cid
             for cid, c in courses.items()}
    label = st.selectbox("Course", list(picks.keys()))
    course_id = picks[label]

    # Only the students who registered THIS course under THIS lecturer.
    enrolled = att.course_students(course_id)
    if not enrolled:
        st.info("No student has registered this course yet.")
        return

    rows = []
    for e in enrolled:
        summ = next((x for x in att.attendance_summary(e["matric"])
                     if x["course_id"] == course_id), None)
        if not summ:
            continue
        rows.append({"Name": e.get("name", ""), "Matric": e["matric"],
                     "Attended": f"{summ['attended']}/{summ['total']}",
                     "Percent": f"{summ['percent']}%",
                     "Status": "Eligible" if summ["eligible"] else "Ineligible"})
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No attendance recorded for this course yet.")


def _at_risk(lid):
    """The flagged students for one course, newest prediction first."""
    courses = att.lecturer_courses(lid)
    if not courses:
        st.info("No courses yet."); return

    picks = {f"{c["course_code"]}, {c["title"]}": c["course_code"]
             for c in courses.values()}
    label = st.selectbox("Course", list(picks.keys()))
    code = picks[label]

    rows = att.predictions_for_course(code)
    if not rows:
        st.info("No predictions yet. A prediction is created when a student "
                "opens their prediction page, once they are eligible.")
        return

    at_risk = [r for r in rows if r.get("at_risk")]
    not_eligible = [r for r in rows if not r.get("eligible")]
    c1, c2, c3 = st.columns(3)
    tile(c1, len(rows), "Assessed"); tile(c2, len(at_risk), "At risk")
    tile(c3, len(not_eligible), "Not eligible")
    st.write("")

    st.dataframe(
        [{"Name": r.get("name", ""), "Matric": r.get("matric", ""),
          "Attendance": f"{r.get('attendance_percent', 0):.0f}%",
          "Eligible": "Yes" if r.get("eligible") else "No",
          "Result": ("At risk" if r.get("at_risk")
                     else "On track" if r.get("eligible") else "Not assessed")}
         for r in sorted(rows, key=lambda x: not x.get("at_risk"))],
        use_container_width=True, hide_index=True)

    # The advice each student was given, so the lecturer can follow it up
    # instead of guessing what the system told them.
    st.write("")
    st.markdown("**Recommendations these students received**")
    for r in sorted(rows, key=lambda x: not x.get("at_risk")):
        if not r.get("advice"):
            continue
        label = ("At risk" if r.get("at_risk")
                 else "On track" if r.get("eligible") else "Not eligible")
        with st.expander(f"{r.get('name','')} ({r.get('matric','')}), {label}"):
            for line in r["advice"]:
                st.write("• " + line)