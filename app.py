import streamlit as st
import datetime
import os
import shutil
import db
from config import RESTAURANT_NAME
from frontend.styles import inject_custom_css
from frontend.components import render_sidebar
from frontend.pages import render_customer_page, render_manager_page

# 1. Page settings
st.set_page_config(
    page_title="AI Restaurant Ordering System",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. Database initialization
db.initialize_database()


# 4. Session State Initialization
if "active_mode" not in st.session_state:
    st.session_state.active_mode = "Customer"

if "thread_id" not in st.session_state:
    st.session_state.thread_id = "customer_001"

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

# 5. Inject styles
inject_custom_css(dark_mode=st.session_state.dark_mode)

# 6. Render TOP BAR
# Wrapper container using HTML
st.markdown("<div class='top-bar-container'>", unsafe_allow_html=True)
col_title, col_controls = st.columns([2, 3])

with col_title:
    st.markdown(f"<p class='top-bar-title'>✨ {RESTAURANT_NAME}</p>", unsafe_allow_html=True)

with col_controls:
    c_time, c_thread, c_theme, c_mode = st.columns([1.5, 2.0, 1.2, 1.8])
    
    with c_time:
        current_time = datetime.datetime.now().strftime("%I:%M %p")
        st.markdown(f"<div style='margin-top: 10px;'>🕒 <b>Time:</b> {current_time}</div>", unsafe_allow_html=True)
        
    with c_thread:
        new_thread = st.text_input(
            "Thread ID:", 
            value=st.session_state.thread_id, 
            key="thread_input",
            label_visibility="collapsed"
        )
        if new_thread != st.session_state.thread_id:
            st.session_state.thread_id = new_thread
            st.rerun()
            
    with c_theme:
        theme_toggle = st.checkbox("Dark Mode", value=st.session_state.dark_mode, key="theme_chk")
        if theme_toggle != st.session_state.dark_mode:
            st.session_state.dark_mode = theme_toggle
            st.rerun()
            
    with c_mode:
        current_mode = st.session_state.active_mode
        btn_cols = st.columns(2)
        with btn_cols[0]:
            if st.button("👤 Cust", key="btn_cust", type="primary" if current_mode == "Customer" else "secondary", use_container_width=True):
                st.session_state.active_mode = "Customer"
                st.rerun()
        with btn_cols[1]:
            if st.button("👔 Mgr", key="btn_mgr", type="primary" if current_mode == "Manager" else "secondary", use_container_width=True):
                st.session_state.active_mode = "Manager"
                st.rerun()

st.markdown("</div>", unsafe_allow_html=True)

# 7. Sidebar and Main Layout
menu_items = db.get_menu()
render_sidebar(st.session_state.thread_id, menu_items)

# 8. Main content routing
if st.session_state.active_mode == "Customer":
    render_customer_page(st.session_state.thread_id, menu_items)
else:
    render_manager_page(menu_items)
