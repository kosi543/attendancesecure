"""
app.py  -  AttendanceSecure
===========================
A secure web-based QR code attendance monitoring system with a place for
machine-learning based early-warning student performance prediction.

Run it with:   streamlit run app.py

Flow:
    Intro (choose role) -> Student / Lecturer / Admin portals.

The app runs out of the box on a local demo database so you can see it
immediately. Drop your `firebase_credentials.json` in this folder to switch
to live Firebase (see README).
"""

import streamlit as st

from core.ui import inject_css
from core import database as db
from views import intro, student, lecturer, admin

st.set_page_config(page_title="AttendanceSecure", page_icon="✓", layout="wide")
inject_css()

if "page" not in st.session_state:
    st.session_state["page"] = "intro"

# small backend indicator in the sidebar
st.sidebar.markdown(
    f"<div style='font-size:11px;color:#8E95BE'>Database: "
    f"<b>{db.backend_name()}</b></div>", unsafe_allow_html=True)

PAGES = {
    "intro": intro.render,
    "student": student.render,
    "lecturer": lecturer.render,
    "admin": admin.render,
}
PAGES.get(st.session_state["page"], intro.render)()
