"""
core/ui.py
==========
Shared look-and-feel helpers. One light theme, one calm accent, simple flat
cards with a soft hover highlight, and a clickable nav menu that replaces the
default radio buttons. Kept plain on purpose.
"""

import streamlit as st
from config import (BRAND_PRIMARY, BRAND_DARK, BRAND_PANEL, BRAND_LIGHT,
                    BRAND_MUTED, BRAND_BORDER, BRAND_TINT)


def inject_css():
    """Inject the app-wide theme once per page."""
    st.markdown(
        f"""
        <style>
        /* Shallow pink gradient*/
        .stApp {{
            background: linear-gradient(160deg, #FFFFFF 0%, #FDF4F8 55%, #FBEAF1 100%);
            background-attachment: fixed;
        }}

        /* Simple flat card with a faint warm tint */
        .card {{
            background: rgba(255,255,255,0.75);
            border: 1px solid {BRAND_BORDER};
            border-radius: 10px;
            padding: 18px 20px;
            margin-bottom: 14px;
        }}

        /* Sidebar gets a soft pink tint so it isn't plain white */
        section[data-testid="stSidebar"] {{
            background: linear-gradient(180deg, #FDF4F8 0%, #FBEAF1 100%);
            border-right: 1px solid {BRAND_BORDER};
        }}

        /* Top title */
        .title {{ font-size: 1.5rem; font-weight: 700; color: {BRAND_LIGHT};
                  margin: 4px 0 2px 0; }}
        .title .accent {{ color: {BRAND_PRIMARY}; }}
        .subtitle {{ color: {BRAND_MUTED}; font-size: 0.92rem; margin-bottom: 14px; }}

        /* Clickable nav / choice buttons: hover highlight, active accent */
        div.stButton > button {{
            background: {BRAND_PANEL};
            color: {BRAND_LIGHT};
            border: 1px solid {BRAND_BORDER};
            border-radius: 8px;
            padding: 10px 14px;
            font-weight: 500;
            transition: all 0.15s ease;
            text-align: left;
        }}
        div.stButton > button:hover {{
            border-color: {BRAND_PRIMARY};
            background: {BRAND_TINT};
            color: {BRAND_PRIMARY};
        }}

        /* Metric tile */
        .tile {{ background:{BRAND_PANEL}; border:1px solid {BRAND_BORDER};
                 border-radius:10px; padding:14px; text-align:center; }}
        .tile .num {{ font-size:1.6rem; font-weight:700; color:{BRAND_PRIMARY}; }}
        .tile .lbl {{ color:{BRAND_MUTED}; font-size:0.82rem; }}

        .ok {{ color:#2F9E44; font-weight:600; }}
        .bad {{ color:#E03131; font-weight:600; }}
        .warn {{ color:#F08C00; font-weight:600; }}
        .warn {{ color:#F08C00; font-weight:600; }}

        /* Early warning result banner: one clear colour, readable size */
        .verdict {{ border-radius:14px; padding:22px 24px; margin:6px 0 4px 0;
                    color:#fff; }}
        .verdict .big {{ font-size:1.7rem; font-weight:700; line-height:1.2; }}
        .verdict .sub {{ font-size:1rem; opacity:.92; margin-top:6px; }}
        .v-good {{ background:linear-gradient(135deg,#2F9E44,#40C057); }}
        .v-risk {{ background:linear-gradient(135deg,#C92A2A,#F03E3E); }}
        .v-gate {{ background:linear-gradient(135deg,#7048E8,#9775FA); }}

        /* Reason and advice lines, bigger than the default caption */
        .reason {{ font-size:1rem; padding:9px 0; border-bottom:1px solid #F1F3F5; }}
        .advice {{ font-size:1rem; padding:10px 14px; margin:7px 0;
                   background:#FFF4F8; border-left:4px solid #D6336C;
                   border-radius:6px; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def title(main_html, sub=""):
    """Plain page title: 'AttendanceSecure' + a small subtitle."""
    st.markdown(f"<div class='title'>{main_html}</div>", unsafe_allow_html=True)
    if sub:
        st.markdown(f"<div class='subtitle'>{sub}</div>", unsafe_allow_html=True)


def brand_title(sub=""):
    """The AttendanceSecure wordmark used at the top of each portal."""
    title("Attendance<span class='accent'>Secure</span>", sub)


def nav_menu(items, state_key):
    """
    A clickable side menu that replaces the radio buttons. `items` is a list of
    labels; the selected one is stored in st.session_state[state_key] and given
    the accent highlight. Returns the selected label.
    """
    if state_key not in st.session_state:
        st.session_state[state_key] = items[0]
    for label in items:
        active = (st.session_state[state_key] == label)
        # Active item is shown with the accent via a marker prefix
        shown = f"● {label}" if active else label
        if st.sidebar.button(shown, key=f"{state_key}_{label}",
                             use_container_width=True):
            st.session_state[state_key] = label
            st.rerun()
    return st.session_state[state_key]


def tile(column, number, label):
    column.markdown(
        f"<div class='tile'><div class='num'>{number}</div>"
        f"<div class='lbl'>{label}</div></div>", unsafe_allow_html=True)


def logout_button():
    if st.sidebar.button("Log out", key="logout_btn", use_container_width=True):
        for k in ("auth", "role", "user"):
            st.session_state.pop(k, None)
        st.session_state["page"] = "intro"
        st.rerun()