# ============================================================
# app_optimized.py — Med-X Operational Excellence Portal (Optimized)
# UI polish: logo in sidebar bottom, toasts, spinners, sidebar card
# Goals: identical functionality, fewer Google Sheets round-trips,
# faster UI by using session cache, partial updates, and O(1) lookups.
# ============================================================

import streamlit as st
import pandas as pd
from datetime import datetime, date
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport import requests
from urllib.parse import urlencode
from google.oauth2.service_account import Credentials
import gspread
import os

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(page_title="Med-X Operational Excellence Portal", layout="wide")

# ============================================================
# Image Loader for Icons (Base64)
# ============================================================
import base64
import os

def load_base64_image(path):
    """Load an image file as base64 (used for title icon)."""
    try:
        with open(path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except Exception:
        return None

# Prepare icon for title (icon.png must exist in app folder)
TITLE_ICON_BASE64 = None
if os.path.exists("icon.png"):
    TITLE_ICON_BASE64 = load_base64_image("icon.png")


# ============================================================
# UI CSS (sidebar profile card, logo styling, toast fallback)
# + Fullscreen Exit Button Styling
# ============================================================
st.markdown(
    """
    <style>
    /* Make main area slightly spaced */
    .block-container {
        padding-top: 18px;
        padding-left: 28px;
        padding-right: 28px;
    }

    /* --------------------------------------------- */
    /* SIDEBAR STYLING */
    /* --------------------------------------------- */

    [data-testid="stSidebar"] {
        position: relative !important;
    }

    [data-testid="stSidebar"]::-webkit-scrollbar {
        display: none;
    }
    [data-testid="stSidebar"] {
        scrollbar-width: none;
        -ms-overflow-style: none;
    }

    .profile-card {
        background: rgba(255,255,255,0.02);
        padding: 14px 12px;
        border-radius: 8px;
        margin-bottom: 12px;
        margin-top: -18px;
    }

    .profile-card h4 {
        margin: 0 0 6px 0;
        font-size: 18px;
    }

    .profile-card p {
        margin: 4px 0;
        color: #c7ced6;
        font-size: 14px;
    }

    .profile-label { 
        color: #9aa3ad; 
        display:inline-block; 
        width: 70px; 
    }

    .profile-card .email-link {
        white-space: nowrap;
    }

    /* --------------------------------------------- */
    /* SIDEBAR FOOTER */
    /* --------------------------------------------- */

    .sidebar-footer {
        position: fixed;
        bottom: 20px;
        left: 0;
        width: 260px;
        padding-left: 20px;
        padding-right: 20px;
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 6px;
        text-align: center;
    }

    .sidebar-footer-text {
        color: #c7ced6;
        font-size: 13px;
    }

    .sidebar-footer-logo {
        width: 95px;
        opacity: 0.98;
    }

    /* --------------------------------------------- */
    /* TOAST (fallback) */
    /* --------------------------------------------- */
    .toast-wrap {
        position: fixed;
        right: 24px;
        top: 24px;
        z-index: 9999;
    }

    .toast {
        background: rgba(17,24,39,0.96);
        color: #e6eef8;
        padding: 10px 14px;
        border-radius: 9px;
        box-shadow: 0 6px 18px rgba(2,6,23,0.6);
        margin-bottom: 8px;
        border-left: 4px solid #10b981;
        font-size: 14px;
    }
    .toast.info  { border-left-color: #0284c7; }
    .toast.warn  { border-left-color: #f59e0b; }
    .toast.error { border-left-color: #ef4444; }

    /* Green highlight for completed status */
    [data-testid="stDataFrame"] td div:contains("Completed") {
        color: #10b981 !important;
        font-weight: 600 !important;
    }

    /* Fix sticky scrolling bug */
    .stDataFrame {
        position: static !important;
    }
    .stDataFrame td:focus-within {
        position: static !important;
    }

    /* --------------------------------------------- */
    /* FULLSCREEN EXIT BUTTON STYLING */
    /* --------------------------------------------- */

    .stDataFrameFullscreen {
        position: relative !important;
    }

    .exit-fullscreen-btn {
        position: absolute;
        top: 12px;
        right: 18px;
        background: #1e293b;
        color: #ffffff;
        padding: 6px 10px;
        border-radius: 6px;
        cursor: pointer;
        z-index: 9999;
        font-size: 13px;
        border: 1px solid #334155;
    }

    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# Fullscreen Exit Fix (JS helper)
# ============================================================
st.markdown(
    """
    <script>
    // Add an "Exit Fullscreen" button inside the fullscreen container
    function attachExitButton() {
        const fsWrapper = document.querySelector("div[data-testid='stElementFullscreen']");
        if (!fsWrapper) return;

        // Avoid duplicates
        if (fsWrapper.querySelector(".exit-fullscreen-btn")) return;

        const btn = document.createElement("div");
        btn.innerText = "Exit Fullscreen";
        btn.className = "exit-fullscreen-btn";

        // Clicking this simulates exiting fullscreen
        btn.onclick = function () {
            fsWrapper.click();
        };

        fsWrapper.classList.add("stDataFrameFullscreen");
        fsWrapper.appendChild(btn);
    }

    // Check regularly if fullscreen is active
    const fsInterval = setInterval(attachExitButton, 400);

    // ESC key also exits fullscreen
    document.addEventListener("keydown", function(e) {
        if (e.key === "Escape") {
            const fsWrapper = document.querySelector("div[data-testid='stElementFullscreen']");
            if (fsWrapper) fsWrapper.click();
        }
    });
    </script>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# Load OAuth Credentials (from Streamlit secrets)
# ============================================================
CLIENT_ID = st.secrets["oauth"]["client_id"]
CLIENT_SECRET = st.secrets["oauth"]["client_secret"]
REDIRECT_URI = st.secrets["oauth"]["redirect_uri"]
ALLOWED_DOMAINS = st.secrets["oauth"]["allowed_domains"]

# ============================================================
# ROLE HIERARCHY (Roles only for display – no restrictions)
# ============================================================
ROLES = {
    "kshukla@med-x.ai": "ceo",
    "jenny@med-x.ai": "cgo",
    "shalabh@med-x.ai": "cto",
}

# Everyone can assign tasks to everyone
ALLOWED_ASSIGN = {
    "ceo": ["ceo", "cgo", "cto", "employee"],
    "cgo": ["ceo", "cgo", "cto", "employee"],
    "cto": ["ceo", "cgo", "cto", "employee"],
    "employee": ["ceo", "cgo", "cto", "employee"],
}

# ============================================================
# Google Sheets Setup
# ============================================================
SERVICE_ACCOUNT_INFO = st.secrets["gcp_service_account"]["service_account_json"]
SHEET_ID = st.secrets["google_sheets"]["sheet_id"]


def connect_to_gspread():
    import json
    service_account_info = json.loads(SERVICE_ACCOUNT_INFO)

    creds = Credentials.from_service_account_info(
        service_account_info,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    return gspread.authorize(creds)


gc = connect_to_gspread()
sheet = gc.open_by_key(SHEET_ID).sheet1

# ============================================================
# Audit Log Sheet (kept as before)
# ============================================================
def get_audit_sheet():
    try:
        return gc.open_by_key(SHEET_ID).worksheet("audit_log")
    except Exception:
        sh = gc.open_by_key(SHEET_ID)
        audit = sh.add_worksheet("audit_log", rows=2000, cols=10)
        audit.update([["timestamp", "action", "task", "user", "old_value", "new_value"]])
        return audit


audit_sheet = get_audit_sheet()


def log_audit(action, task, user, old_value="", new_value=""):
    try:
        audit_sheet.append_row([
            str(datetime.now()), action, task, user, old_value, new_value
        ])
    except Exception:
        # Never break the app for audit failures
        pass

# ============================================================
# Column mapping (sheet-level). Keep sync with sheet header.
# ============================================================
COLS = ["task", "description", "assigned_to", "assigned_by", "due_date", "status", "created_at"]
COL_IDX = {c: i + 1 for i, c in enumerate(COLS)}  # 1-based for gspread

# ============================================================
# Caching helpers — we keep a single authoritative cache in session
# ============================================================
def load_tasks_from_sheet(force_reload=False):
    """
    Load tasks into session cache. If available and not forced, return cached.
    SAFE against broken / partially empty Google Sheet rows.
    """
    if not force_reload and "tasks_cache" in st.session_state:
        return st.session_state["tasks_cache"]

    # ✅ SAFETY FIX: default_blank prevents crashes
    data = sheet.get_all_records(default_blank="")

    cols = COLS.copy()

    if not data:
        df = pd.DataFrame(columns=cols)
    else:
        df = pd.DataFrame(data)

        # Ensure all expected columns exist
        for c in cols:
            if c not in df.columns:
                df[c] = ""

        # Enforce strict column order
        df = df[cols].fillna("")

    # Store cache and rebuild index
    st.session_state["tasks_cache"] = df.reset_index(drop=True)
    build_index_map()

    return st.session_state["tasks_cache"]


def build_index_map():
    """
    Build a dictionary to lookup row index (0-based) by signature.
    Signature uses (created_at, assigned_by, task) with safe fallbacks.
    """
    df = st.session_state.get("tasks_cache")
    idx = {}

    if df is None or df.empty:
        st.session_state["tasks_index_map"] = idx
        return idx

    for i, r in df.reset_index(drop=True).iterrows():
        created_at = r.get("created_at", "")
        assigned_by = r.get("assigned_by", "")
        task = r.get("task", "")

        idx[(created_at, assigned_by, task)] = i
        idx.setdefault((created_at, assigned_by, None), i)
        idx.setdefault((None, assigned_by, task), i)

    st.session_state["tasks_index_map"] = idx
    return idx


def find_task_index_by_signature(created_at_ts, assigned_by_val, task_name):
    """
    Fast lookup using pre-built index map.
    """
    idx = st.session_state.get("tasks_index_map", {})

    for key in [
        (created_at_ts, assigned_by_val, task_name),
        (created_at_ts, assigned_by_val, None),
        (None, assigned_by_val, task_name),
    ]:
        if key in idx:
            return idx[key]

    # Final fallback
    for k, v in idx.items():
        if k[0] == created_at_ts:
            return v

    return None


# ============================================================
# Sheet update primitives (partial updates to minimize round-trips)
# ============================================================
def append_task_to_sheet(row: dict):
    """
    SAFELY append a new row to sheet using header-based mapping.
    This GUARANTEES correct column order forever.
    """

    # ✅ SOURCE OF TRUTH: read headers from sheet
    headers = sheet.row_values(1)

    # Build row strictly in header order
    values = [row.get(h, "") for h in headers]

    sheet.append_row(
        values,
        value_input_option="USER_ENTERED"
    )

    # Update local cache safely
    df = st.session_state.get("tasks_cache")
    if df is None:
        df = load_tasks_from_sheet(force_reload=True)
    else:
        df.loc[len(df)] = values
        st.session_state["tasks_cache"] = df
        build_index_map()

    return len(st.session_state["tasks_cache"]) - 1


def update_single_cell_in_sheet(row_idx_zero_based: int, col_name: str, value):
    """
    Update a single cell (safe, minimal payload).
    """
    row_num = row_idx_zero_based + 2  # header offset
    col_num = COL_IDX[col_name]

    sheet.update_cell(row_num, col_num, value)

    # Reflect in cache
    df = st.session_state.get("tasks_cache")
    if df is not None and row_idx_zero_based < len(df):
        df.at[row_idx_zero_based, col_name] = value
        st.session_state["tasks_cache"] = df
        build_index_map()


def delete_row_in_sheet(row_idx_zero_based: int):
    """
    Delete a row safely and sync cache.
    """
    row_num = row_idx_zero_based + 2

    try:
        sheet.delete_rows(row_num)
    except Exception:
        # Rare fallback: rewrite entire sheet safely
        df = st.session_state.get("tasks_cache")
        if df is not None:
            df2 = df.drop(index=row_idx_zero_based).reset_index(drop=True)
            sheet.clear()
            sheet.update([COLS] + df2.values.tolist())
            st.session_state["tasks_cache"] = df2
            build_index_map()
            return

    # Update cache
    df = st.session_state.get("tasks_cache")
    if df is not None:
        df2 = df.drop(index=row_idx_zero_based).reset_index(drop=True)
        st.session_state["tasks_cache"] = df2
        build_index_map()

# ============================================================
# Google OAuth Helpers (unchanged)
# ============================================================
SCOPES = ["openid",
          "https://www.googleapis.com/auth/userinfo.profile",
          "https://www.googleapis.com/auth/userinfo.email"]


def build_flow():
    cfg = {
        "web": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uris": [REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    }
    f = Flow.from_client_config(cfg, scopes=SCOPES)
    f.redirect_uri = REDIRECT_URI
    return f


def get_google_login_url():
    f = build_flow()
    url, _ = f.authorization_url(
        prompt="consent",
        access_type="offline",
        include_granted_scopes="true"
    )
    return url

# ============================================================
# Helpers: Toast (st.toast if available else HTML fallback)
# ============================================================
def _render_html_toast(msg, tone="info"):
    st.markdown(f"""
        <div class="toast-wrap">
            <div class="toast {tone}">{msg}</div>
        </div>
        """, unsafe_allow_html=True)


def show_toast(message, tone="info", icon=None):
    """
    Display a small toast. Prefer st.toast (newer Streamlit), fallback to HTML or st.success.
    tone: info|warn|error
    icon: optional emoji string (e.g. '🎉')
    """
    # Try using st.toast if available (Streamlit >= some version)
    try:
        toast_fn = getattr(st, "toast", None)
        if callable(toast_fn):
            # Some Streamlit versions allow icon param, try with it, else without
            try:
                if icon:
                    st.toast(message, icon=icon)
                else:
                    st.toast(message)
                return
            except Exception:
                try:
                    st.toast(message)
                    return
                except Exception:
                    pass
    except Exception:
        pass

    # HTML fallback
    try:
        _render_html_toast((icon + " " + message) if icon else message, tone=tone)
        return
    except Exception:
        pass

    # Final fallback
    if tone == "info":
        st.success(message)
    elif tone == "warn":
        st.warning(message)
    elif tone == "error":
        st.error(message)
    else:
        st.info(message)

# ============================================================
# Session Handling
# ============================================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

params = dict(st.query_params)

if "code" in params and not st.session_state.logged_in:
    try:
        f = build_flow()
        full = REDIRECT_URI + "?" + urlencode(params)
        f.fetch_token(authorization_response=full)
        creds = f.credentials

        req = requests.Request()
        info = id_token.verify_oauth2_token(creds.id_token, req, CLIENT_ID)

        email = info.get("email", "").lower()
        if not email:
            st.error("Google login failed.")
            st.stop()

        if email.split("@")[1] not in ALLOWED_DOMAINS:
            st.error("Unauthorized domain.")
            st.stop()

        st.session_state.role = ROLES.get(email, "employee")
        st.session_state.email = email
        st.session_state.name = info.get("name", email.split("@")[0])
        st.session_state.logged_in = True

        # Clear query params and rerun
        st.query_params.clear()
        st.rerun()

    except Exception as e:
        st.error("Login failed: " + str(e))
        st.stop()

# ============================
# LOGIN PAGE (Full White Theme — No Black Strip)
# ============================
if not st.session_state.logged_in:

    import base64

    def load_base64(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()

    logo_html = ""
    if os.path.exists("logo2.png"):
        b64 = load_base64("logo2.png")
        logo_html = f"<img src='data:image/png;base64,{b64}' class='login-logo' />"

    login_html = f"""
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@700;800&family=Inter:wght@300;400;600&display=swap" rel="stylesheet">

    <style>

      /* Remove ALL dark Streamlit backgrounds */
      html, body, 
      [data-testid="stApp"], 
      [data-testid="stAppViewContainer"], 
      [data-testid="stDecoration"],
      [data-testid="stHeader"],
      [data-testid="stToolbar"] {{
        background: #ffffff !important;
        color: #000000 !important;
      }}

      .login-wrap {{
        display: flex;
        align-items: center;
        justify-content: center;
        height: 88vh;
      }}

      .login-card {{
        background: #ffffff;
        border-radius: 18px;
        padding: 60px 60px;
        width: 750px;
        max-width: 95%;
        box-shadow: 0 10px 28px rgba(0,0,0,0.12);
        text-align: center;
      }}

      .login-logo {{
        width: 150px;
        margin-bottom: 26px;
        opacity: 0.92;
      }}

      .login-title {{
        font-family: 'Montserrat', sans-serif;
        font-weight: 800;
        font-size: 32px;
        color: #0f172a;
        margin: 10px 0 18px;
      }}

      .login-sub {{
        font-family: 'Inter', sans-serif;
        color: #475569;
        margin-bottom: 36px;
        font-size: 16px;
      }}

      /* Google Login Button */
      .google-login-btn {{
        display: inline-block;
        background: #ffffff;
        border-radius: 8px;
        border: 1px solid #dadce0;
        text-decoration: none;
        box-shadow: 0 1px 3px rgba(60,64,67,.3), 0 4px 8px rgba(60,64,67,.15);
        transition: box-shadow .15s ease, transform .08s ease;
      }}

      .google-login-btn:hover {{
        box-shadow: 0 2px 6px rgba(60,64,67,.35), 0 6px 14px rgba(60,64,67,.18);
        transform: translateY(-1px);
      }}

      .google-btn-content {{
        display: flex;
        align-items: center;
        padding: 12px 24px;
      }}

      .google-icon-wrapper {{
        width: 20px;
        height: 20px;
        margin-right: 14px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #ffffff;
      }}

      .google-icon {{
        width: 20px;
        height: 20px;
      }}

      .google-btn-text {{
        font-family: 'Inter', sans-serif;
        color: #3c4043;
        font-size: 15px;
        font-weight: 500;
      }}

    </style>

    <div class="login-wrap">
      <div class="login-card">

        {logo_html}

        <div class="login-title">Med-X Operational Excellence Portal Login</div>

        <div class="login-sub">
          Welcome — please sign in with your company Google account to continue.
        </div>

        <a class="google-login-btn" href="{get_google_login_url()}">
          <div class="google-btn-content">
            <div class="google-icon-wrapper">
              <img class="google-icon"
                   src="https://developers.google.com/identity/images/g-logo.png"
                   alt="Google">
            </div>
            <span class="google-btn-text">Continue with Google</span>
          </div>
        </a>

      </div>
    </div>
    """

    st.html(login_html)
    st.stop()



# ============================================================
# MAIN UI (Sidebar + Title)
# ============================================================

# Load sidebar icon
USER_ICON_BASE64 = None
if os.path.exists("icon2.png"):
    with open("icon2.png", "rb") as f:
        USER_ICON_BASE64 = base64.b64encode(f.read()).decode()

TABLE_ICON_BASE64 = None
if os.path.exists("table.png"):
    with open("table.png", "rb") as f:
        TABLE_ICON_BASE64 = base64.b64encode(f.read()).decode()


# ===========================
# USER INFO BLOCK (ICON OUTSIDE CARD) — FIXED HTML
# ===========================
st.sidebar.markdown(f"""
<div style="display:flex; align-items:center; gap:10px; margin-bottom:2px; margin-top:-10px;">
<img src="data:image/png;base64,{USER_ICON_BASE64}" style="width:22px; height:22px;"/>
<h4 style="margin:0; font-size:18px;">User Info</h4>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown(f"""
<div class="profile-card" style="margin-top:0;">

<div style="display:flex; align-items:center;">
<span class="profile-label">Name:</span>
<span style="margin-left:6px;">{st.session_state.name}</span>
</div>

<div style="display:flex; align-items:center;">
<span class="profile-label">Email:</span>
<a class="email-link" href="mailto:{st.session_state.email}" style="color:#6ee7b7; margin-left:6px;">
{st.session_state.email}
</a>
</div>

<div style="display:flex; align-items:center;">
<span class="profile-label">Role:</span>
<span style="margin-left:6px;">{st.session_state.role.upper()}</span>
</div>

</div>
""", unsafe_allow_html=True)

# IMPORTANT: define email + role early
role = st.session_state.role
email = st.session_state.email

# Load tasks into a df
df_all = st.session_state.get("tasks_cache", load_tasks_from_sheet())

# ============================================================
# SIDEBAR TASK DASHBOARD  (FINAL NON-TYPEABLE VERSION)
# ============================================================

# Load dashboard icon you uploaded
DASH_ICON_BASE64 = load_base64_image("dashboard.png")

st.sidebar.markdown(f"""
<div style="display:flex; align-items:center; gap:10px; margin-top:14px;">
    <img src="data:image/png;base64,{DASH_ICON_BASE64}" style="width:22px; height:22px;"/>
    <h4 style="margin:0;">Task Overview</h4>
</div>
""", unsafe_allow_html=True)

# Completely non-typeable selector (recommended)
dashboard_view = st.sidebar.radio(
    "Select View",
    ["Tasks Assigned", "Your Tasks"],
    key="sidebar_dashboard_view"
)

# VIEW 1 → Tasks Assigned
if dashboard_view == "Tasks Assigned":
    df_view = df_all[(df_all["assigned_by"] == email) & (df_all["assigned_to"] != email)]

# VIEW 2 → Your Tasks
else:
    df_view = df_all[df_all["assigned_to"] == email]

# Stats
total_tasks = len(df_view)
completed_tasks = (df_view["status"] == "Completed").sum()
inprogress_tasks = (df_view["status"] == "In-Progress").sum()
pending_tasks = (df_view["status"] == "Pending").sum()
progress_percent = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0

# Sidebar card
st.sidebar.markdown(f"""
<div style="background: rgba(255,255,255,0.05); padding: 14px 16px; border-radius: 12px; margin-bottom: 14px; font-size: 14px;">
<b>Total Tasks:</b> {total_tasks}<br>
<b>Completed:</b> {completed_tasks}<br>
<b>In-Progress:</b> {inprogress_tasks}<br>
<b>Pending:</b> {pending_tasks}<br><br>

<div style="color:#c7ced6; margin-bottom:4px;"><b>Overall Progress: {progress_percent}%</b></div>

<div style="width:100%; background: rgba(255,255,255,0.08); border-radius:6px; height:9px; overflow:hidden;">
    <div style="height:9px; width:{progress_percent}%; background:#10b981; transition: width 0.4s ease;"></div>
</div>
</div>
""", unsafe_allow_html=True)

# Logout button
if st.sidebar.button("Log out"):
    for k in ["tasks_cache", "tasks_index_map", "edited_assigned_tasks", "edited_tasks"]:
        st.session_state.pop(k, None)
    st.session_state.logged_in = False
    st.query_params.clear()
    st.rerun()

# ============================================================
# SIDEBAR FOOTER — FIXED, BOTTOM CENTER INSIDE SIDEBAR
# ============================================================
if os.path.exists("logo.png"):
    with open("logo.png", "rb") as f:
        b64_logo = base64.b64encode(f.read()).decode()

    with st.sidebar:
        st.markdown(f"""
        <div class="sidebar-footer">
            <span class="sidebar-footer-text">Powered by</span>
            <img src="data:image/png;base64,{b64_logo}" class="sidebar-footer-logo" />
        </div>
        """, unsafe_allow_html=True)


# ============================================================
# CUSTOM TITLE WITH ICON  (Fixed Padding)
# ============================================================
if TITLE_ICON_BASE64:
    st.markdown(
        f"""
        <div style="
            padding-top: 20px;
            margin-bottom: 18px; 
            display:flex; 
            align-items:center; 
            gap:14px;
        ">
            <img src="data:image/png;base64,{TITLE_ICON_BASE64}"
                 style="width:38px; height:38px; vertical-align:middle; margin-top:2px;"/>
            <h1 style="margin:0; padding:0; font-size:2.4rem;">
                Med-X Operational Excellence Portal
            </h1>
        </div>
        """,
        unsafe_allow_html=True
    )
else:
    st.title("Med-X Operational Excellence Portal")

# ⭐⭐⭐ IMPORTANT — THIS LINE WAS MISSING ⭐⭐⭐
tasks = load_tasks_from_sheet()
# ⭐⭐⭐ WITHOUT THIS, 'tasks' is undefined ⭐⭐⭐

# ============================================================
# ASSIGN NEW TASK
# ============================================================
st.subheader("Create New Task")
title = st.text_input("Task Title", key="new_task_title")
desc = st.text_area("Description", key="new_task_desc")
assign_to_input = st.text_input("Assign To (email)", key="new_task_assign")
due_date = st.date_input("Due Date (Optional)", value=None, key="new_task_due")

if st.button("Create Task", key="create_task_btn"):
    assign_to = (assign_to_input or "").strip().lower()
    if not title.strip() or "@med-x.ai" not in assign_to:
        st.error("Enter valid title + company email.")
    else:
        # No assignment restriction anymore
        new = {
            "task": title,
            "description": desc,
            "assigned_to": assign_to,
            "assigned_by": email,
            "due_date": str(due_date) if due_date else "",
            "status": "Pending",
            "created_at": datetime.now().isoformat()
        }

        # append to sheet (partial update) and update cache
        with st.spinner("Creating task..."):
            new_idx = append_task_to_sheet(new)
            log_audit("created", title, email, "", f"assigned_to={assign_to}")

            # clear any editor session copies and rebuild on next render
            st.session_state.pop("edited_assigned_tasks", None)
            st.session_state.pop("edited_tasks", None)

        show_toast("Task created successfully!", tone="info", icon="🎉")
        st.rerun()

# ============================================================
# UTILS
# ============================================================
def is_overdue_vec(due_series, status_series):
    """Vectorized overdue check for speed."""
    try:
        due_dates = pd.to_datetime(due_series, errors='coerce').dt.date
        today = date.today()
        return (due_dates.notna()) & (status_series != "Completed") & (due_dates < today)
    except Exception:
        return pd.Series([False] * len(due_series))

def created_date_only(ts):
    if not ts:
        return ""
    try:
        base = str(ts).split("T")[0].split(" ")[0]
        # quick validation
        _ = datetime.fromisoformat(base) if "-" in base and len(base.split("-")) == 3 else None
        return base
    except Exception:
        try:
            return str(ts).split(" ")[0]
        except Exception:
            return str(ts)

# ============================================================
# HELPER: PAGINATION FOR TABLES
# ============================================================
def paginate_dataframe(df, key_prefix, rows_per_page=10):
    total_rows = len(df)
    total_pages = max(1, (total_rows - 1) // rows_per_page + 1)

    # page state key stays unique for each table
    page_key = f"{key_prefix}_page"

    if page_key not in st.session_state:
        st.session_state[page_key] = 1

    # Navigation buttons
    colA, colB, colC = st.columns([1, 1, 8])

    with colA:
        if st.button("⬅ Previous", key=f"{key_prefix}_prev", disabled=st.session_state[page_key] == 1):
            st.session_state[page_key] -= 1
            st.rerun()

    with colB:
        if st.button("Next ➡", key=f"{key_prefix}_next", disabled=st.session_state[page_key] == total_pages):
            st.session_state[page_key] += 1
            st.rerun()

    st.caption(f"Page {st.session_state[page_key]} of {total_pages}")

    # Compute slice
    start = (st.session_state[page_key] - 1) * rows_per_page
    end = start + rows_per_page

    return df.iloc[start:end]


# ============================================================
# TASKS ASSIGNED (what I created and assigned to others)
# ============================================================
st.markdown(
    f"""
    <div style="display:flex; align-items:center; gap:10px; margin-top:10px;">
        <img src="data:image/png;base64,{TABLE_ICON_BASE64}" 
             style="width:20px; height:20px;"/>
        <h3 style="margin:0;">Tasks Assigned</h3>
    </div>
    """,
    unsafe_allow_html=True
)

# ---------------------------
# FILTER BAR (WITHOUT TITLE)
# ---------------------------
col1, col2, col3, col4 = st.columns(4)

with col1:
    status_filter = st.multiselect(
        "Status",
        ["Pending", "In-Progress", "Completed"],
        default=["Pending", "In-Progress"],  # Default: do NOT show completed
        key="assigned_status_filter"
    )

with col2:
    date_filter = st.selectbox(
        "Date Range",
        ["All", "This Week", "Last Week", "This Month", "Last Month", "Custom"],
        key="assigned_date_filter"
    )

with col3:
    overdue_only = st.checkbox(
        "Overdue Only",
        value=False,
        key="assigned_overdue_filter"
    )

with col4:
    if date_filter == "Custom":
        start_date = st.date_input("From", value=date.today(), key="assigned_custom_start")
        end_date = st.date_input("To", value=date.today(), key="assigned_custom_end")
    else:
        start_date = None
        end_date = None

# ---------------------------
# APPLY FILTERS
# ---------------------------
assigned_by_me = tasks[(tasks["assigned_by"] == email) & (tasks["assigned_to"] != email)].copy()

if not assigned_by_me.empty:

    assigned_by_me["created_at_date"] = pd.to_datetime(
        assigned_by_me["created_at"], errors="coerce"
    ).dt.date

    # Status filter
    assigned_by_me = assigned_by_me[assigned_by_me["status"].isin(status_filter)]

    # Overdue filter
    if overdue_only:
        assigned_by_me = assigned_by_me[
            is_overdue_vec(assigned_by_me["due_date"], assigned_by_me["status"])
        ]

    # Date filtering
    today = date.today()

    if date_filter == "This Week":
        week_start = today - pd.to_timedelta(today.weekday(), unit="day")
        assigned_by_me = assigned_by_me[assigned_by_me["created_at_date"] >= week_start]

    elif date_filter == "Last Week":
        last_week_start = today - pd.to_timedelta(today.weekday() + 7, unit="day")
        last_week_end = last_week_start + pd.to_timedelta(6, unit="day")
        assigned_by_me = assigned_by_me[
            (assigned_by_me["created_at_date"] >= last_week_start) &
            (assigned_by_me["created_at_date"] <= last_week_end)
        ]

    elif date_filter == "This Month":
        month_start = today.replace(day=1)
        assigned_by_me = assigned_by_me[assigned_by_me["created_at_date"] >= month_start]

    elif date_filter == "Last Month":
        first_this_month = today.replace(day=1)
        last_month_end = first_this_month - pd.to_timedelta(1, unit="day")
        last_month_start = last_month_end.replace(day=1)
        assigned_by_me = assigned_by_me[
            (assigned_by_me["created_at_date"] >= last_month_start) &
            (assigned_by_me["created_at_date"] <= last_month_end)
        ]

    elif date_filter == "Custom" and start_date and end_date:
        assigned_by_me = assigned_by_me[
            (assigned_by_me["created_at_date"] >= start_date) &
            (assigned_by_me["created_at_date"] <= end_date)
        ]

    # Sort newest first
    assigned_by_me = assigned_by_me.sort_values("created_at", ascending=False).reset_index(drop=True)

    # Create display columns
    assigned_by_me["Serial No"] = range(1, len(assigned_by_me) + 1)
    assigned_by_me["Created At (display)"] = assigned_by_me["created_at"].apply(created_date_only)

    def to_date_obj(s):
        if not s:
            return None
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except:
            try:
                return pd.to_datetime(s).date()
            except:
                return None

    assigned_by_me["Due Date"] = assigned_by_me["due_date"].apply(to_date_obj)
    assigned_by_me["Delete"] = "No"
    assigned_by_me["Status"] = assigned_by_me["status"]

    # Remove "Overdue" column completely
    view = assigned_by_me[[
        "Serial No",
        "task",
        "description",
        "Status",
        "assigned_to",
        "Created At (display)",
        "Due Date",
        "Delete"
    ]].copy()

    view.rename(columns={
        "task": "Task",
        "description": "Description",
        "assigned_to": "Assigned To",
        "Created At (display)": "Created At"
    }, inplace=True)

    # Save for row tracking
    created_at_internal = assigned_by_me["created_at"].tolist()

    # ---------------------------
    # PAGINATION (10 rows)
    # ---------------------------
    paginated_view = paginate_dataframe(view, "assigned_tasks", rows_per_page=10)

    st.session_state["edited_assigned_tasks"] = paginated_view.copy()

    # ⭐ FULLSCREEN WRAPPER ⭐
    with st.container():
        st.markdown('<div class="stDataFrameFullscreen">', unsafe_allow_html=True)

        edited = st.data_editor(
            st.session_state["edited_assigned_tasks"],
            use_container_width=True,
            num_rows="fixed",
            hide_index=True,
            key="assigned_tasks_editor_ui",
            column_config={
                "Serial No": st.column_config.TextColumn("Serial No", disabled=True),
                "Task": st.column_config.TextColumn("Task"),
                "Description": st.column_config.TextColumn("Description"),
                "Status": st.column_config.TextColumn("Status", disabled=True),
                "Assigned To": st.column_config.TextColumn("Assigned To"),
                "Created At": st.column_config.TextColumn("Created At", disabled=True),
                "Due Date": st.column_config.DateColumn("Due Date", format="YYYY-MM-DD"),
                "Delete": st.column_config.SelectboxColumn("Delete", options=["No", "Yes"])
            }
        )

        st.markdown("</div>", unsafe_allow_html=True)

    # ⭐ NEW FIX: REAL EXIT FULLSCREEN BUTTON ⭐
    st.markdown(
        """
        <script>
        function attachExitBtn() {
            const fs = document.querySelector("div[data-testid='stElementFullscreen']");
            if (!fs) return;

            if (fs.querySelector("#exitFS")) return;

            const btn = document.createElement("button");
            btn.innerText = "Exit Fullscreen";
            btn.id = "exitFS";
            btn.style.position = "absolute";
            btn.style.top = "10px";
            btn.style.right = "15px";
            btn.style.padding = "6px 10px";
            btn.style.zIndex = "99999";
            btn.style.background = "#1e293b";
            btn.style.color = "white";
            btn.style.border = "1px solid #334155";
            btn.style.borderRadius = "6px";
            btn.onclick = () => fs.click();

            fs.appendChild(btn);
        }

        setInterval(attachExitBtn, 500);
        </script>
        """,
        unsafe_allow_html=True,
    )

    # ---------------------------
    # SAVE LOGIC (unchanged)
    # ---------------------------
    if st.button("💾 Save Assigned Tasks", key="save_assigned_tasks_btn"):
        deletions = []
        updates = []
        errors = []

        for i in range(len(edited)):
            created_at_ts = created_at_internal[i]
            task_display_name = edited.iloc[i]["Task"]

            found_idx = find_task_index_by_signature(
                created_at_ts, email, task_display_name
            )

            if found_idx is None:
                errors.append(f"Could not find row for '{task_display_name}', skipping.")
                continue

            original = st.session_state["tasks_cache"].iloc[found_idx]

            # DELETE
            if edited.iloc[i]["Delete"] == "Yes":
                deletions.append(found_idx)
                continue

            # REASSIGN
            new_assigned_to = str(edited.iloc[i]["Assigned To"]).strip().lower()
            if new_assigned_to != original["assigned_to"]:
                if "@med-x.ai" not in new_assigned_to:
                    errors.append(f"Invalid email: {new_assigned_to}")
                else:
                    updates.append(("assigned_to", found_idx, original["assigned_to"], new_assigned_to, task_display_name))

            # TITLE
            if edited.iloc[i]["Task"] != original["task"]:
                updates.append(("task", found_idx, original["task"], edited.iloc[i]["Task"], original["task"]))

            # DESCRIPTION
            if edited.iloc[i]["Description"] != original["description"]:
                updates.append(("description", found_idx, original["description"], edited.iloc[i]["Description"], original["task"]))

            # DUE DATE
            orig_due = original.get("due_date", "") or ""
            new_due_obj = edited.iloc[i]["Due Date"]
            new_due_str = new_due_obj.isoformat() if isinstance(new_due_obj, date) else ""
            if new_due_str != orig_due:
                updates.append(("due_date", found_idx, orig_due, new_due_str, original["task"]))

        # Deletions
        if deletions:
            with st.spinner("Deleting rows..."):
                for ridx in sorted(set(deletions), reverse=True):
                    task_name = st.session_state["tasks_cache"].at[ridx, "task"]
                    delete_row_in_sheet(ridx)
                    log_audit("deleted", task_name, email, "", "")

        # Updates
        change_count = 0
        if updates:
            with st.spinner("Saving changes..."):
                for field, orig_idx, oldv, newv, task_ref in updates:

                    found_idx = find_task_index_by_signature(
                        st.session_state["tasks_cache"].at[orig_idx, "created_at"],
                        email,
                        task_ref
                    )
                    if found_idx is None:
                        found_idx = orig_idx

                    update_single_cell_in_sheet(found_idx, field, newv)
                    change_count += 1

        if change_count > 0 or deletions:
            st.session_state.pop("edited_assigned_tasks", None)
            st.session_state.pop("edited_tasks", None)

        if errors:
            for e in errors:
                st.error(e)

        total_changes = len(deletions) + change_count

        if total_changes > 0:
            show_toast(f"Saved {total_changes} change(s)!", tone="info")
            st.rerun()
        else:
            if not errors:
                st.info("No changes to save.")
else:
    st.info("You have not assigned any tasks to others.")

# ============================================================
# YOUR TASKS (Assigned To You)
# ============================================================
st.markdown(
    f"""
    <div style="display:flex; align-items:center; gap:10px; margin-top:20px;">
        <img src="data:image/png;base64,{TABLE_ICON_BASE64}" 
             style="width:20px; height:20px;"/>
        <h3 style="margin:0;">Your Tasks</h3>
    </div>
    """,
    unsafe_allow_html=True
)

# ---------------------------
# FILTER BAR (NO HEADING)
# ---------------------------
col1, col2, col3, col4 = st.columns(4)

with col1:
    status_filter = st.multiselect(
        "Status",
        ["Pending", "In-Progress", "Completed"],
        default=["Pending", "In-Progress"],  # completed NOT shown by default
        key="your_status_filter"
    )

with col2:
    date_filter = st.selectbox(
        "Date Range",
        ["All", "This Week", "Last Week", "This Month", "Last Month", "Custom"],
        key="your_date_filter"
    )

with col3:
    overdue_only = st.checkbox(
        "Overdue Only",
        value=False,
        key="your_overdue_filter"
    )

with col4:
    if date_filter == "Custom":
        start_date = st.date_input("From", value=date.today(), key="your_custom_start")
        end_date = st.date_input("To", value=date.today(), key="your_custom_end")
    else:
        start_date = None
        end_date = None


# --------------------------------------------------
# FILTER DATA
# --------------------------------------------------
df = tasks[tasks["assigned_to"] == email].copy()

if df.empty:
    st.info("No tasks assigned to you.")
else:

    df["created_at_date"] = pd.to_datetime(df["created_at"], errors="coerce").dt.date

    # Status filter
    df = df[df["status"].isin(status_filter)]

    # Overdue filter
    if overdue_only:
        df = df[is_overdue_vec(df["due_date"], df["status"])]

    today = date.today()

    # Date filtering
    if date_filter == "This Week":
        week_start = today - pd.to_timedelta(today.weekday(), unit="day")
        df = df[df["created_at_date"] >= week_start]

    elif date_filter == "Last Week":
        last_week_start = today - pd.to_timedelta(today.weekday() + 7, unit="day")
        last_week_end = last_week_start + pd.to_timedelta(6, unit="day")
        df = df[
            (df["created_at_date"] >= last_week_start) &
            (df["created_at_date"] <= last_week_end)
        ]

    elif date_filter == "This Month":
        month_start = today.replace(day=1)
        df = df[df["created_at_date"] >= month_start]

    elif date_filter == "Last Month":
        first_this_month = today.replace(day=1)
        last_month_end = first_this_month - pd.to_timedelta(1, unit="day")
        last_month_start = last_month_end.replace(day=1)
        df = df[
            (df["created_at_date"] >= last_month_start) &
            (df["created_at_date"] <= last_month_end)
        ]

    elif date_filter == "Custom" and start_date and end_date:
        df = df[
            (df["created_at_date"] >= start_date) &
            (df["created_at_date"] <= end_date)
        ]

    # Sort newest → oldest
    df = df.sort_values("created_at", ascending=False).reset_index(drop=True)

    # Create display columns
    df["Serial No"] = range(1, len(df) + 1)
    df["Created At (display)"] = df["created_at"].apply(created_date_only)
    df["Due Date"] = df["due_date"].replace("", "—")
    df["Delete"] = "No"

    # FINAL TABLE — **WITHOUT Overdue column**
    view = df[[
        "Serial No",
        "task",
        "description",
        "status",
        "assigned_by",
        "Created At (display)",
        "Due Date",
        "Delete"
    ]].copy()

    view.rename(columns={
        "task": "Task",
        "description": "Description",
        "status": "Status",
        "assigned_by": "Assigned By",
        "Created At (display)": "Created At"
    }, inplace=True)

    created_at_internal_for_assignee = df["created_at"].tolist()

    # ---------------------------
    # PAGINATION (10 rows per page)
    # ---------------------------
    paginated_view = paginate_dataframe(view, "your_tasks", rows_per_page=10)

    st.session_state["edited_tasks"] = paginated_view.copy()

    # ⭐ FULLSCREEN WRAPPER ⭐
    with st.container():
        st.markdown('<div class="stDataFrameFullscreen">', unsafe_allow_html=True)

        edited = st.data_editor(
            st.session_state["edited_tasks"],
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            key="your_tasks_editor_ui",
            column_config={
                "Serial No": st.column_config.TextColumn("Serial No", disabled=True),
                "Task": st.column_config.TextColumn("Task", disabled=True),
                "Description": st.column_config.TextColumn("Description", disabled=True),
                "Status": st.column_config.SelectboxColumn(
                    "Status", options=["Pending", "In-Progress", "Completed"]
                ),
                "Assigned By": st.column_config.TextColumn("Assigned By", disabled=True),
                "Created At": st.column_config.TextColumn("Created At", disabled=True),
                "Due Date": st.column_config.TextColumn("Due Date", disabled=True),
                "Delete": st.column_config.SelectboxColumn("Delete", options=["No", "Yes"])
            }
        )

        st.markdown("</div>", unsafe_allow_html=True)

    # ⭐ NEW FULLSCREEN EXIT BUTTON ⭐
    st.markdown(
        """
        <script>
        function addExitFS() {
            const fs = document.querySelector("div[data-testid='stElementFullscreen']");
            if (!fs) return;
            if (fs.querySelector("#exitFS")) return;

            const btn = document.createElement("button");
            btn.id = "exitFS";
            btn.innerText = "Exit Fullscreen";
            btn.style.position = "absolute";
            btn.style.top = "10px";
            btn.style.right = "15px";
            btn.style.padding = "6px 10px";
            btn.style.zIndex = "99999";
            btn.style.background = "#1e293b";
            btn.style.color = "white";
            btn.style.border = "1px solid #334155";
            btn.style.borderRadius = "6px";

            btn.onclick = () => fs.click();
            fs.appendChild(btn);
        }

        setInterval(addExitFS, 500);
        </script>
        """,
        unsafe_allow_html=True,
    )

    # --------------------------------------------------------
    # SAVE LOGIC  (unchanged)
    # --------------------------------------------------------
    if st.button("💾 Save Your Tasks", key="save_your_tasks_btn"):
        changes = 0
        deletions = []
        errors = []

        for i in range(len(edited)):
            created_at_ts = created_at_internal_for_assignee[i]
            task_display_name = edited.iloc[i]["Task"]
            assigned_by_val = edited.iloc[i]["Assigned By"]

            found_idx = find_task_index_by_signature(
                created_at_ts, assigned_by_val, task_display_name
            )

            if found_idx is None:
                errors.append(f"Could not find row for '{task_display_name}', skipping.")
                continue

            original = st.session_state["tasks_cache"].iloc[found_idx]

            # DELETE possible only if user created the task
            if edited.iloc[i]["Delete"] == "Yes":
                if original["assigned_by"] == email:
                    deletions.append(found_idx)
                else:
                    st.warning(f"Cannot delete '{task_display_name}' — you did not create it.")
                continue

            # STATUS CHANGE
            old_status = original["status"]
            new_status = edited.iloc[i]["Status"]

            if new_status != old_status:
                with st.spinner("Saving status..."):
                    update_single_cell_in_sheet(found_idx, "status", new_status)
                    log_audit("status_change", task_display_name, email, old_status, new_status)
                    changes += 1

        # Deletions
        if deletions:
            with st.spinner("Deleting rows..."):
                for ridx in sorted(set(deletions), reverse=True):
                    task_name = st.session_state["tasks_cache"].at[ridx, "task"]
                    delete_row_in_sheet(ridx)
                    log_audit("deleted", task_name, email, "", "")

        # Refresh
        if changes > 0 or deletions:
            st.session_state.pop("edited_assigned_tasks", None)
            st.session_state.pop("edited_tasks", None)
            total = changes + len(deletions)
            show_toast(f"Saved {total} change(s)!", tone="info")
            st.rerun()

        else:
            if errors:
                for e in errors:
                    st.error(e)
            else:
                st.info("No changes to save.")

# ============================================================
# End
# ============================================================
