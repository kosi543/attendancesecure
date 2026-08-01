"""
views/student.py
================
Student portal.
  * Register (department is a strict dropdown of admin-created departments)
  * Login with matric number
  * Scan attendance: only for courses this student registered, and only the
    live code of that course's own lecturer. Shows inside/outside the zone.
  * My courses: register a real course from a real lecturer, edit the reason,
    or drop it with a reason.
  * My attendance and eligibility
  * Check my location / Check my camera (grant permission once)
  * Prediction / Recommendation (placeholder)
"""

import altair as alt
import pandas as pd
import streamlit as st

from core.ui import brand_title, nav_menu, tile, logout_button
from core import auth, attendance as att, qr_engine
from core.fingerprint import get_device_fingerprint
from core.location import request_location, permission_warning
from core.geofence import check_location
from ml import predictor
from config import NIGERIA_DIAL_CODE, QR_REFRESH_SECONDS

# Preset reasons shown as clickable buttons instead of free text
COURSE_REASONS = ["Registering course", "Carry-over", "Retake", "Other"]


def render():
    if not st.session_state.get("auth") or st.session_state.get("role") != "student":
        _auth_screen()
        return
    _dashboard()


# ---------------------------------------------------------------------------
def _auth_screen():
    brand_title("Student portal")
    if st.button("← Back", key="s_back"):
        st.session_state["page"] = "intro"; st.rerun()

    tab_login, tab_reg = st.tabs(["Login", "Register"])

    with tab_login:
        matric = st.text_input("Matric number", key="s_login_matric")
        pwd = st.text_input("Password", type="password", key="s_login_pwd")
        if st.button("Log in", key="s_login_btn"):
            ok, res = auth.login_student(matric, pwd)
            if ok:
                st.session_state.update(auth=True, role="student", user=res)
                st.rerun()
            else:
                st.error(res)

    with tab_reg:
        departments = auth.list_department_names()
        if not departments:
            st.info("Registration opens once the administrator has added "
                    "departments.")
            return
        c1, c2 = st.columns(2)
        name = c1.text_input("Full name")
        matric = c2.text_input("Matric number")
        dept = c1.selectbox("Department", departments)   # strict dropdown
        level = c2.selectbox("Level", ["100", "200", "300", "400", "500"])
        email = c1.text_input("Email")
        cemail = c2.text_input("Confirm email")
        phone = c1.text_input(f"Phone ({NIGERIA_DIAL_CODE}...)", value=NIGERIA_DIAL_CODE)
        pwd = c1.text_input("Password", type="password")
        cpwd = c2.text_input("Confirm password", type="password")
        if st.button("Register", key="s_reg_btn"):
            ok, msg = auth.register_student(name, matric, dept, level, email,
                                            cemail, phone, pwd, cpwd)
            (st.success if ok else st.error)(msg)


# ---------------------------------------------------------------------------
def _dashboard():
    user = st.session_state["user"]
    st.sidebar.markdown(f"**{user['name']}**")
    st.sidebar.caption(f"{user['matric']} • {user.get('department','')}")
    logout_button()

    choice = nav_menu(
        ["Scan attendance", "My courses", "My attendance",
         "Location Check", "Camera Check", "Risk Alerts"],
        "student_menu")

    brand_title(choice)

    if choice == "Scan attendance":
        _scan(user)
    elif choice == "My courses":
        _my_courses(user)
    elif choice == "My attendance":
        _my_attendance(user)
    elif choice == "Location Check":
        _check_location(user)
    elif choice == "Camera Check":
        _check_camera()
    else:
        _risk_alerts(user)


def _scan(user):
    permission_warning()

    # Only sessions for courses this student registered, from that course's
    # own lecturer. Another department's live class is simply not listed.
    sessions = att.sessions_for_student(user["matric"])
    if not sessions:
        st.info("No live session for any of your registered courses.")
        return

    options = {f"{s['course_code']} (live)": sid for sid, s in sessions.items()}
    label = st.selectbox("Active session", list(options.keys()))
    sid = options[label]
    session = sessions[sid]

    left = att.seconds_left(session)
    st.caption(f"Session closes in {left // 60}m {left % 60}s • "
               f"code refreshes every {QR_REFRESH_SECONDS}s.")

    if att.already_scanned(sid, user["matric"]):
        st.success("You have already been recorded for this session.")
        return

    device_id = get_device_fingerprint()

    # ---------------- Step 1: location, and say clearly where they are -----
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.write("**Step 1: allow location**")
    loc = request_location(key=f"gps_{sid}")
    if loc:
        location_shared, gps_lat, gps_lon = True, loc["lat"], loc["lon"]
    else:
        st.caption("Allow location in your browser when asked.")
        location_shared, gps_lat, gps_lon = False, None, None

    accuracy = loc["accuracy"] if loc else 0.0
    geo = check_location(gps_lat, gps_lon, session["class_lat"],
                         session["class_lon"], session["radius_m"],
                         accuracy_m=accuracy)

    if not location_shared:
        st.error("Location not shared. You can still scan, but the scan will "
                 "be flagged for your lecturer to review.")
    elif geo.inside:
        st.success(f"Inside the class zone: you are {geo.distance_m:.0f} m "
                   f"from the class centre (allowed {geo.radius_m:.0f} m).")
    else:
        st.error(f"Outside the class zone: you are {geo.distance_m:.0f} m "
                 f"from the class centre, and the allowed radius is "
                 f"{geo.radius_m:.0f} m. A scan from here will be flagged.")
    st.markdown("</div>", unsafe_allow_html=True)

    # ---------------- Step 2: scan the live code ---------------------------
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.write("**Step 2: scan the live code**")
    photo = st.camera_input("Point at the QR and capture")
    if photo is not None:
        # Some browsers block the signals the fingerprint is built from,
        # for example in private mode or with strict privacy settings. The
        # scan is still accepted, but it is flagged, because an unidentifiable
        # device is exactly what a proxy scanner would present.
        device_known = bool(device_id)
        if not device_known:
            device_id = "unreadable"

        payload = qr_engine.decode_qr_from_image(photo.getvalue())
        if not payload:
            st.error("No QR code found. Try again.")
            st.markdown("</div>", unsafe_allow_html=True); return
        if qr_engine.session_id_from_payload(payload) != sid:
            st.error("That code belongs to a different class.")
            st.markdown("</div>", unsafe_allow_html=True); return

        # re-read the position at the moment of the scan
        geo = check_location(gps_lat, gps_lon, session["class_lat"],
                             session["class_lon"], session["radius_m"],
                             accuracy_m=accuracy)
        qr_ok, qr_msg = qr_engine.validate_token(payload)
        ip = st.session_state.get("ip", "102.89.0.10")

        # short, specific reasons, not one vague label
        flags = []
        if not qr_ok:
            flags.append(qr_msg)
        if not geo.inside:
            flags.append(geo.reason)
        if not device_known:
            flags.append("device fingerprint could not be read")
        device_reused = att.device_used_in_session(sid, device_id,
                                                   user["matric"])
        if device_reused:
            flags.append("this device already scanned for another student "
                         "in this session")

        att.record_scan(session, user, device_id, ip, gps_lat, gps_lon,
                        geo.distance_m, geo.inside, qr_ok, location_shared,
                        reason="; ".join(flags), device_known=device_known)
        reason="; ".join(flags), device_known=device_known,
                        device_reused=device_reused)

        if qr_ok and geo.inside and device_known:
            st.success(f"Attendance recorded. You were {geo.distance_m:.0f} m "
                       f"from the class centre.")
        else:
            st.error("Recorded but flagged for review: " + "; ".join(flags))
    st.markdown("</div>", unsafe_allow_html=True)


def _my_courses(user):
    st.caption("Create or join a course.")
    with st.expander("Create / join a course"):
        c1, c2 = st.columns(2)
        code = c1.text_input("Course code", placeholder="CSC401")
        title = c2.text_input("Course title", placeholder="Machine Learning")
        st.write("Reason")
        # preset reason buttons instead of free text
        if "s_course_reason" not in st.session_state:
            st.session_state.s_course_reason = COURSE_REASONS[0]
        rc = st.columns(len(COURSE_REASONS))
        for i, r in enumerate(COURSE_REASONS):
            mark = f"● {r}" if st.session_state.s_course_reason == r else r
            if rc[i].button(mark, key=f"rsn_{r}"):
                st.session_state.s_course_reason = r; st.rerun()
        if st.button("Submit course", key="s_course_submit"):
            ok, msg = att.student_request_course(
                user["matric"], user["name"], code, title,
                st.session_state.s_course_reason,
                department=user.get("department", ""))
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()

    mine = att.student_enrolments(user["matric"])
    if not mine:
        st.info("You have not created or joined any course yet.")
        return
    for eid, e in mine.items():
        linked = "Linked to lecturer" if e.get("lecturer_id") else "Awaiting lecturer"
        st.markdown(
            f"<div class='card'><b>{e['course_code']}</b>, {e.get('title','')}"
            f"<br><small style='color:#6B7280'>{linked} • {e.get('reason','')}"
            f"</small></div>", unsafe_allow_html=True)
        with st.expander(f"Edit {e['course_code']}"):
            # A course still waiting for a lecturer was typed by the student,
            # so they can correct all of it. Once a lecturer owns the course,
            # only the reason is theirs to change.
            pending = not e.get("lecturer_id")
            if pending:
                f1, f2 = st.columns(2)
                new_code = f1.text_input("Course code",
                                         value=e.get("course_code", ""),
                                         key=f"ec_{eid}")
                new_title = f2.text_input("Course title",
                                          value=e.get("title", ""),
                                          key=f"et_{eid}")
            else:
                new_code, new_title = e.get("course_code"), e.get("title")
                st.caption("The code and title belong to the lecturer who "
                           "created this course, so only the reason can be "
                           "changed here.")
            reason = st.text_input("Reason", value=e.get("reason", ""),
                                   key=f"er_{eid}")
            c1, c2 = st.columns(2)
            if c1.button("Save", key=f"esave_{eid}"):
                ok, msg = att.update_enrolment(eid, new_code, new_title, reason,
                                               actor=user["matric"])
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()
            if c2.button("Remove course", key=f"edrop_{eid}"):
                ok, msg = att.drop_enrolment(eid, reason or "Removed by student",
                                             actor=user["matric"])
                (st.warning if ok else st.error)(msg)
                if ok:
                    st.rerun()


def _my_attendance(user):
    summary = att.attendance_summary(user["matric"])
    if not summary:
        st.info("Register a course first, then your attendance shows here.")
        return
    elig = sum(1 for s in summary if s["eligible"])
    c1, c2, c3 = st.columns(3)
    tile(c1, len(summary), "Courses")
    tile(c2, elig, "Eligible")
    tile(c3, len(summary) - elig, "Not eligible")
    st.write("")
    for s in summary:
        if s.get("pending"):
            st.markdown(
                f"<div class='card'><b>{s['course_code']}</b>, {s['title']}<br>"
                f"<small style='color:#6B7280'>Awaiting lecturer</small></div>",
                unsafe_allow_html=True)
            continue
        cls = "ok" if s["eligible"] else "bad"
        status = "Eligible" if s["eligible"] else "Not eligible"
        note = f"<br><small style='color:#6B7280'>{s['note']}</small>" if s["note"] else ""
        st.markdown(
            f"<div class='card'><b>{s['course_code']}</b>, {s['title']}<br>"
            f"<small style='color:#6B7280'>{s['lecturer']}</small><br>"
            f"{s['attended']}/{s['total']} classes • <b>{s['percent']}%</b> • "
            f"<span class='{cls}'>{status}</span>{note}</div>",
            unsafe_allow_html=True)
        st.progress(min(s["percent"] / 100, 1.0))


def _check_location(user):
    permission_warning()
    if st.button("Test my location", key="loc_test"):
        st.session_state["loc_check_on"] = True

    if not st.session_state.get("loc_check_on"):
        return

    loc = request_location(key="loc_dash")
    if not loc:
        st.info("Allow location in your browser when the popup appears.")
        return

    sessions = att.sessions_for_student(user["matric"])
    note = ""
    if not sessions:
        # No class is running, so measure against the last place each of the
        # student's lecturers held a session. That lets them check they are
        # inside the boundary before the class even starts.
        sessions = att.last_session_zones(user["matric"])
        note = " (last known class location)"
    if not sessions:
        st.success("Location is working. No class location on record yet.")
        return

    # just where they stand: inside or outside, and how far
    for s in sessions.values():
        geo = check_location(loc["lat"], loc["lon"], s["class_lat"],
                             s["class_lon"], s["radius_m"],
                             accuracy_m=loc["accuracy"])
        where = "Inside the zone" if geo.inside else "Outside the zone"
        st.write(f"**{s['course_code']}**{note}: {where}, "
                 f"{geo.distance_m:.0f} m from the class.")


def _check_camera():
    permission_warning()
    shot = st.camera_input("Tap to test your camera")
    if shot is not None:
        st.success("Your camera is working.")


def _risk_alerts(user):
    """
    Risk alerts screen.

    The student enters their test score and previous GPA. Everything else the
    system already knows: attendance from their own scans, assignments from
    what the lecturer ticked. No model names appear here, a student does not
    need to know which algorithm produced the answer.
    """
    summary = att.attendance_summary(user["matric"])
    ready = [row for row in summary if not row.get("pending")]
    if not ready:
        st.info("Register a course and attend some classes first.")
        return

    # The only thing the student supplies. Attendance and assignments are
    # taken from the system, and the previous GPA from their record.
    saved = att.get_academic_features(user["matric"])
    c1, c2 = st.columns([2, 1])
    score = c1.number_input("Your most recent test score (out of 30)",
                            0.0, 30.0,
                            float(saved["test_score"] or 0.0), 1.0)
    gpa = c2.number_input("Previous GPA (out of 5.00)", 0.0, 5.0,
                          float(saved["prior_gpa"] or 0.0), 0.01)
    if st.button("Predict my likelihood of passing or failing",
                 type="primary", use_container_width=True):
        att.save_academic_features(user["matric"], gpa, score,
                                   saved.get("assignment_rate") or 0)
        st.session_state["ew_ready"] = True

    if not st.session_state.get("ew_ready"):
        return

    for row in ready:
        rate, done, total = att.assignment_rate(user["matric"], row["course_id"])
        # The training data grades on a 4.0 scale, students here work on a
        # 5.0 scale, so the GPA is converted before the model sees it.
        features = {"prior_gpa": gpa / 5 * 4, "test_score": score,
                    "assignment_rate": rate}

        result = predictor.assess(row["percent"], features,
                                  eligible_override=row["eligible"])
        att.save_prediction(user["matric"], user["name"],
                            row["course_code"], result)

        if result["model_missing"]:
            st.warning("No trained model found. Run: python ml/train_models.py")
            return

        st.markdown(f"### {row['course_code']}, {row['title']}")

        # ---- the verdict, in one colour and plain words -------------------
        if not result["eligible"]:
            st.markdown(
                f"<div class='verdict v-gate'>"
                f"<div class='big'>Not yet eligible</div>"
                f"<div class='sub'>Attendance {row['percent']:.0f}%, "
                f"70% is needed to sit this exam.</div></div>",
                unsafe_allow_html=True)
        elif result["at_risk"]:
            st.markdown(
                f"<div class='verdict v-risk'>"
                f"<div class='big'>At risk of failing</div>"
                f"<div class='sub'>Based on your attendance, assignments, "
                f"test score and previous GPA.</div></div>",
                unsafe_allow_html=True)
        else:
            st.markdown(
                f"<div class='verdict v-good'>"
                f"<div class='big'>Likely to pass</div>"
                f"<div class='sub'>Based on your attendance, assignments, "
                f"test score and previous GPA.</div></div>",
                unsafe_allow_html=True)

        # ---- what is affecting the result --------------------------------
        # Each bar is measured against its own target, and coloured red when
        # it falls short, green when it clears it.
        st.write("")
        st.markdown("**What is affecting your result**")

        factors = pd.DataFrame([
            # Attendance carries two separate rules, so it gets three states
            # below: 70% is the eligibility rule for sitting the exam, and 85%
            # is the level at which risk actually falls away.
            {"Factor": "Attendance", "Percent": row["percent"], "Target": 70,
             "Detail": f"{row['attended']} of {row['total']} classes"},
            {"Factor": "Assignments", "Percent": rate, "Target": 60,
             "Detail": f"{done} of {total} submitted" if total else "none set yet"},
            {"Factor": "Test score", "Percent": score / 30 * 100, "Target": 60,
             "Detail": f"{score:.0f} out of 30"},
            {"Factor": "Previous GPA", "Percent": gpa / 5 * 100, "Target": 60,
             "Detail": f"{gpa:.2f} out of 5.00"},
        ])
        def standing(r):
            """Attendance sits in the middle band when it passes the 70% rule
            but has not reached the 85% where risk drops away."""
            if r["Factor"] == "Attendance":
                if r["Percent"] >= 85:
                    return "Good"
                if r["Percent"] >= 70:
                    return "Eligible, but low"
                return "Not so good"
            return "Good" if r["Percent"] >= r["Target"] else "Not so good"

        factors["Standing"] = factors.apply(standing, axis=1)

        chart = alt.Chart(factors).mark_bar(size=34).encode(
            x=alt.X("Percent", scale=alt.Scale(domain=[0, 100]), title=None),
            y=alt.Y("Factor", sort=None, title=None),
            color=alt.Color("Standing",
                            scale=alt.Scale(
                                domain=["Good", "Eligible, but low",
                                        "Not so good"],
                                range=["#2F9E44", "#F59F00", "#E03131"]),
                            legend=alt.Legend(orient="bottom", title=None)),
            tooltip=["Factor", "Percent", "Detail"],
        ).properties(height=260)
        st.altair_chart(chart, use_container_width=True)

        for _, f in factors.iterrows():
            colour = {"Good": "ok", "Eligible, but low": "warn"}.get(
                f["Standing"], "bad")
            note = f["Detail"]
            if f["Standing"] == "Eligible, but low":
                note += ", above the 70% rule but below the 85% that lowers risk"
            st.markdown(
                f"<div class='reason'>{f['Factor']}: "
                f"<b>{f['Percent']:.0f}%</b> "
                f"<span class='{colour}'>({f['Standing']})</span>"
                f"<span style='color:#6B7280'>, {note}</span></div>",
                unsafe_allow_html=True)

        # ---- study hours first, then the recommendations -----------------
        st.write("")
        _study_hours_guide(row["course_code"])

        st.write("")
        st.markdown("**Recommendations:**")
        for line in result["advice"]:
            st.markdown(f"<div class='advice'>{line}</div>",
                        unsafe_allow_html=True)
        st.write("")




def _study_hours_guide(course_code):
    """
    Not part of the prediction. This is straightforward guidance taken from
    the second dataset, where 16.9% of students studying under 10 hours a week
    ended up failing, against 0.4% of those studying 10 to 20 hours, and
    almost none above 20. The student enters their own hours and is told where
    they sit against that pattern.
    """
    with st.expander("How many hours do you study each week?"):
        hours = st.number_input("Hours of study per week", 0.0, 60.0, 0.0, 1.0,
                                key=f"hrs_{course_code}")
        if hours <= 0:
            st.caption("Enter your weekly study hours to see how they compare.")
            return
        if hours < 10:
            st.markdown(
                f"<div class='advice'>{hours:.0f} hours a week is low. "
                f"Raising it to 10 or 15 hours would put you on much safer "
                f"ground.</div>", unsafe_allow_html=True)
        elif hours < 20:
            st.markdown(
                f"<div class='advice'>{hours:.0f} hours a week is a healthy "
                f"amount. Keep it steady.</div>", unsafe_allow_html=True)
        else:
            st.markdown(
                f"<div class='advice'>{hours:.0f} hours a week is strong. "
                f"Keep it up.</div>", unsafe_allow_html=True)