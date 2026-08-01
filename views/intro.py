"""
views/intro.py
==============
Landing page. Just the AttendanceSecure name and three clean options:
Student, Lecturer, Administrator. Each is a clickable card that highlights
on hover. No quote, no fine print.
"""

import streamlit as st
from core.ui import brand_title


def render():
    # centre the content in a narrow column so it looks calm, not stretched
    left, mid, right = st.columns([1, 2, 1])
    with mid:
        brand_title("A secure QR attendance system")
        st.write("")
        st.markdown("<p style='color:#6B7280;margin-bottom:6px'>Continue as</p>",
                    unsafe_allow_html=True)

        if st.button("Student", key="go_student", use_container_width=True):
            st.session_state["page"] = "student"; st.rerun()
        if st.button("Lecturer", key="go_lecturer", use_container_width=True):
            st.session_state["page"] = "lecturer"; st.rerun()
        if st.button("Administrator", key="go_admin", use_container_width=True):
            st.session_state["page"] = "admin"; st.rerun()
