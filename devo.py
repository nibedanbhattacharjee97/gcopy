import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date, datetime
import hashlib
import os
import re
from typing import Dict, Any, List, Optional, Tuple

# ============================================================
# ⚙️ PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="Student Verification Entry Form",
    page_icon="✅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# 🎨 GLOBAL STYLE
# ============================================================
st.markdown("""
<style>
    .main {
        background: linear-gradient(135deg, #00aaff, #00ffaa);
    }

    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
    }

    .login-card {
        background-color: white;
        border-radius: 18px;
        padding: 2rem;
        box-shadow: 0px 6px 18px rgba(0,0,0,0.18);
        width: 440px;
        margin: auto;
        text-align: center;
    }

    .login-title {
        color: #007bff;
        font-size: 1.6rem;
        font-weight: 800;
        margin-bottom: 1rem;
    }

    .section-card {
        background-color: rgba(255,255,255,0.94);
        padding: 1rem 1rem 1.2rem 1rem;
        border-radius: 14px;
        margin-bottom: 1rem;
        box-shadow: 0px 2px 12px rgba(0,0,0,0.08);
    }

    .section-title {
        font-size: 1.12rem;
        font-weight: 800;
        color: #0d47a1;
        margin-bottom: 0.55rem;
    }

    .small-muted {
        color: #5f6368;
        font-size: 0.85rem;
    }

    .info-box {
        background: #eef6ff;
        border-left: 5px solid #007bff;
        padding: 10px 12px;
        border-radius: 8px;
        margin-bottom: 12px;
    }

    .success-box {
        background: #eafaf1;
        border-left: 5px solid #28a745;
        padding: 10px 12px;
        border-radius: 8px;
        margin-bottom: 12px;
    }

    .warning-box {
        background: #fff8e5;
        border-left: 5px solid #ff9800;
        padding: 10px 12px;
        border-radius: 8px;
        margin-bottom: 12px;
    }

    .danger-box {
        background: #ffeef0;
        border-left: 5px solid #dc3545;
        padding: 10px 12px;
        border-radius: 8px;
        margin-bottom: 12px;
    }

    .footer {
        text-align: center;
        font-size: 0.9rem;
        color: #666;
        margin-top: 1rem;
        padding-top: 1rem;
    }

    .summary-chip {
        display: inline-block;
        padding: 5px 10px;
        margin-right: 6px;
        margin-bottom: 6px;
        background: #f1f5f9;
        border-radius: 999px;
        border: 1px solid #d9e2ec;
        font-size: 0.84rem;
    }

    .stButton > button {
        background-color: #007bff;
        color: white;
        font-weight: bold;
        border-radius: 10px;
        height: 2.8em;
        width: 100%;
        border: none;
    }

    .stButton > button:hover {
        background-color: #0056b3;
        color: white;
    }

    .action-green button {
        background-color: #16a34a !important;
    }

    .action-green button:hover {
        background-color: #15803d !important;
    }

    .action-orange button {
        background-color: #f59e0b !important;
    }

    .action-orange button:hover {
        background-color: #d97706 !important;
    }

    .action-red button {
        background-color: #dc3545 !important;
    }

    .action-red button:hover {
        background-color: #b02a37 !important;
    }

    .stTextInput input:disabled,
    .stDateInput input:disabled {
        background-color: #f7f7f7 !important;
        color: #6b7280 !important;
        opacity: 1 !important;
    }

    .top-banner {
        background: linear-gradient(90deg, #0ea5e9, #22c55e);
        color: white;
        border-radius: 16px;
        padding: 18px 20px;
        margin-bottom: 1rem;
        box-shadow: 0 6px 20px rgba(0,0,0,0.10);
    }

    .top-banner h2 {
        margin: 0;
        padding: 0;
        font-size: 1.45rem;
        font-weight: 800;
    }

    .top-banner p {
        margin: 0.35rem 0 0 0;
        padding: 0;
        font-size: 0.95rem;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 🔒 PASSWORD UTILITIES
# ============================================================
def hash_password(password: str) -> str:
    return hashlib.sha256(str(password).encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == safe_str(hashed)


# ============================================================
# 📌 CONSTANTS
# ============================================================
APP_TITLE = "Student Verification Entry Form"
SHEET_MAIN_NAME = "Test"
SHEET_LOGIN_NAME = "Test_Spoc_PassWord"
SHEET_FETCH_NAME = "Test2"

STUDENT_TOUCH_OPTIONS = [
    "Tikona_Call",
    "SPOC_call"
]

CONTACTABLE_OPTIONS = [
    "Yes",
    "No"
]

RETENTION_STATUS_OPTIONS = [
    "Unable_to_track",
    "Working in same job",
    "Not_working_at_all",
    "Working in different job",
    "Confirmed Name But Didn't Share Any Information.",
    "Confirmed Name & Disconnected",
    "Left_The_Job",
    "Not_joined_yet",
    "Hold",
    "Rejected"
]

AUTO_CLEAR_RETENTION_STATUSES = [
    "Unable_to_track",
    "Not_working_at_all",
    "Rejected",
    "Hold",
    "Confirmed Name But Didn't Share Any Information.",
    "Confirmed Name & Disconnected"
]

REASON_OPTIONS = [
    "",
    "Distance Issue",
    "Pursuing Higher Studies.",
    "Job Profile Did Not Match",
    "Family Issue",
    "Medical & Health Issue",
    "Casually Left The Job.",
    "Salary Issue",
    "Heavy Workload",
    "Unhealthy Work Environment.",
    "Office Timing",
    "Night Shift",
    "Internship/Project Completed",
    "Company Closed",
    "Others…",
    "Don't Want To Share"
]

NEED_JOB_OPTIONS = [
    "",
    "Yes",
    "No"
]

NPS_OPTIONS = [
    "--",
    "0",
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "10"
]

REMARKS_OPTIONS = [
    "Did not respond to our call",
    "Network issue",
    "Not a student of Anudip",
    "Language issue",
    "Switched off",
    "Incoming Call Is Not Avialable",
    "Wrong Number",
    "Did_not_joined_job_due_to_personal_issue",
    "Did_not_joined_job_due_to_profile_issue",
    "Did not get any information from the employer",
    "Did not get selected",
    "Did Not Attend Any Interview"
]

DATE_FORMAT_HINT = "YYYY-MM-DD"
DEFAULT_REASON = ""
DEFAULT_NEED_JOB = ""
DEFAULT_NPS = "--"
DEFAULT_MONTHS = 0

# ============================================================
# 🧰 GENERIC HELPERS
# ============================================================
def safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_blank(value: Any) -> bool:
    return safe_str(value) == ""


def normalize_contact(number: Any) -> str:
    value = safe_str(number)
    value = value.replace(" ", "")
    value = value.replace("-", "")
    value = value.replace("(", "")
    value = value.replace(")", "")
    value = value.replace(".", "")
    if value.startswith("+91"):
        value = value[3:]
    return value


def safe_index(options: List[Any], value: Any, default: int = 0) -> int:
    value = str(value) if value is not None else value
    options_as_str = [str(x) for x in options]
    if value in options_as_str:
        return options_as_str.index(value)
    return default


def parse_date_to_string(raw_value: Any) -> str:
    raw = safe_str(raw_value)
    if not raw:
        return ""

    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%d %b %Y",
        "%d %B %Y"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass

    try:
        return datetime.fromisoformat(raw).strftime("%Y-%m-%d")
    except Exception:
        return ""


def is_valid_date_string(value: Any) -> bool:
    value = safe_str(value)
    if value == "":
        return True
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except Exception:
        return False


def needs_auto_clear(retention_status: str) -> bool:
    return safe_str(retention_status) in AUTO_CLEAR_RETENTION_STATUSES


def normalize_choice(value: Any, allowed: List[str], default: str) -> str:
    val = safe_str(value)
    return val if val in allowed else default


def info_box(text: str):
    st.markdown(f'<div class="info-box">{text}</div>', unsafe_allow_html=True)


def success_box(text: str):
    st.markdown(f'<div class="success-box">{text}</div>', unsafe_allow_html=True)


def warning_box(text: str):
    st.markdown(f'<div class="warning-box">{text}</div>', unsafe_allow_html=True)


def danger_box(text: str):
    st.markdown(f'<div class="danger-box">{text}</div>', unsafe_allow_html=True)


# ============================================================
# 🗂️ SESSION STATE KEYS
# ============================================================
def init_app_state():
    defaults = {
        # Auth
        "logged_in": False,
        "spoc_name": "",

        # Banner / submit state
        "last_submit_success": False,
        "last_submit_message": "",
        "show_post_submit_actions": False,

        # Fetch / match state
        "match_found": False,
        "matched_source_note": "",

        # Form field states
        "student_touch_val": STUDENT_TOUCH_OPTIONS[0],
        "student_name_val": "",
        "cmisid_val": "",
        "contact_number_val": "",
        "contactable_val": CONTACTABLE_OPTIONS[0],
        "retention_status_val": RETENTION_STATUS_OPTIONS[0],
        "months_working_val": DEFAULT_MONTHS,
        "current_company_val": "",
        "current_salary_val": "",
        "current_designation_val": "",
        "doj_val": "",
        "reason_leaving_val": DEFAULT_REASON,
        "need_job_val": DEFAULT_NEED_JOB,
        "nps_val": DEFAULT_NPS,
        "verification_date_val": date.today(),
        "remarks_val": REMARKS_OPTIONS[0],

        # Control flags
        "clear_requested": False,
        "create_another_requested": False
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def clear_dependent_fields():
    st.session_state.current_company_val = ""
    st.session_state.current_salary_val = ""
    st.session_state.current_designation_val = ""
    st.session_state.doj_val = ""
    st.session_state.reason_leaving_val = DEFAULT_REASON
    st.session_state.need_job_val = DEFAULT_NEED_JOB
    st.session_state.nps_val = DEFAULT_NPS


def clear_all_form_fields():
    st.session_state.student_touch_val = STUDENT_TOUCH_OPTIONS[0]
    st.session_state.student_name_val = ""
    st.session_state.cmisid_val = ""
    st.session_state.contact_number_val = ""
    st.session_state.contactable_val = CONTACTABLE_OPTIONS[0]
    st.session_state.retention_status_val = RETENTION_STATUS_OPTIONS[0]
    st.session_state.months_working_val = DEFAULT_MONTHS
    st.session_state.current_company_val = ""
    st.session_state.current_salary_val = ""
    st.session_state.current_designation_val = ""
    st.session_state.doj_val = ""
    st.session_state.reason_leaving_val = DEFAULT_REASON
    st.session_state.need_job_val = DEFAULT_NEED_JOB
    st.session_state.nps_val = DEFAULT_NPS
    st.session_state.verification_date_val = date.today()
    st.session_state.remarks_val = REMARKS_OPTIONS[0]
    st.session_state.match_found = False
    st.session_state.matched_source_note = ""
    st.session_state.clear_requested = False
    st.session_state.create_another_requested = False
    st.session_state.last_submit_success = False
    st.session_state.last_submit_message = ""
    st.session_state.show_post_submit_actions = False


def on_retention_change():
    if needs_auto_clear(st.session_state.retention_status_val):
        clear_dependent_fields()


# ============================================================
# ✅ VALIDATION
# ============================================================
def validate_form() -> List[str]:
    errors = []

    if is_blank(st.session_state.student_name_val):
        errors.append("Student Name is required.")

    if is_blank(st.session_state.contact_number_val):
        errors.append("Contact Number is required.")

    if not needs_auto_clear(st.session_state.retention_status_val):
        if not is_valid_date_string(st.session_state.doj_val):
            errors.append(f"DOJ must be blank or in {DATE_FORMAT_HINT} format.")

    return errors


# ============================================================
# 📦 GOOGLE SHEETS CONNECTION
# ============================================================
@st.cache_resource(show_spinner=False)
def get_gspread_client():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    if "gcp_service_account" in st.secrets:
        credentials = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=scope
        )
        return gspread.authorize(credentials), "cloud"

    if os.path.exists("service_account.json"):
        credentials = Credentials.from_service_account_file(
            "service_account.json",
            scopes=scope
        )
        return gspread.authorize(credentials), "local"

    raise FileNotFoundError(
        "No credentials found. Add service_account.json locally or gcp_service_account in Streamlit Secrets."
    )


@st.cache_resource(show_spinner=False)
def get_sheets():
    client, mode = get_gspread_client()
    main_sheet = client.open(SHEET_MAIN_NAME).sheet1
    login_sheet = client.open(SHEET_LOGIN_NAME).sheet1
    fetch_sheet = client.open(SHEET_FETCH_NAME).sheet1
    return main_sheet, login_sheet, fetch_sheet, mode


def load_test2_records(fetch_sheet) -> List[Dict[str, Any]]:
    try:
        return fetch_sheet.get_all_records()
    except Exception:
        return []


def load_login_records(login_sheet) -> List[Dict[str, Any]]:
    try:
        return login_sheet.get_all_records()
    except Exception:
        return []


def fetch_matching_test2_row(records: List[Dict[str, Any]], contact_number: str) -> Optional[Dict[str, Any]]:
    target = normalize_contact(contact_number)
    if not target:
        return None

    for row in records:
        if normalize_contact(row.get("Contact Number", "")) == target:
            return row
    return None


def load_test2_row_into_session(row: Dict[str, Any]):
    st.session_state.cmisid_val = safe_str(row.get("CMIS ID", ""))
    st.session_state.current_company_val = safe_str(row.get("Company Name", ""))
    st.session_state.current_salary_val = safe_str(row.get("Salary", ""))
    st.session_state.current_designation_val = safe_str(row.get("Deg", ""))
    st.session_state.doj_val = parse_date_to_string(row.get("DOJ", ""))
    st.session_state.match_found = True
    st.session_state.matched_source_note = "✅ Test2 sheet match found. Fields auto-filled and still editable."

    if needs_auto_clear(st.session_state.retention_status_val):
        clear_dependent_fields()


def persist_current_form_to_session():
    if needs_auto_clear(st.session_state.retention_status_val):
        clear_dependent_fields()

    st.session_state.reason_leaving_val = normalize_choice(
        st.session_state.reason_leaving_val, REASON_OPTIONS, DEFAULT_REASON
    )
    st.session_state.need_job_val = normalize_choice(
        st.session_state.need_job_val, NEED_JOB_OPTIONS, DEFAULT_NEED_JOB
    )
    st.session_state.nps_val = normalize_choice(
        st.session_state.nps_val, NPS_OPTIONS, DEFAULT_NPS
    )


def build_submission_row() -> List[Any]:
    retention_status = safe_str(st.session_state.retention_status_val)

    current_company = safe_str(st.session_state.current_company_val)
    current_salary = safe_str(st.session_state.current_salary_val)
    current_designation = safe_str(st.session_state.current_designation_val)
    doj = safe_str(st.session_state.doj_val)
    reason_leaving = safe_str(st.session_state.reason_leaving_val)
    need_job = safe_str(st.session_state.need_job_val)
    nps = safe_str(st.session_state.nps_val)

    if needs_auto_clear(retention_status):
        current_company = ""
        current_salary = ""
        current_designation = ""
        doj = ""
        reason_leaving = DEFAULT_REASON
        need_job = DEFAULT_NEED_JOB
        nps = DEFAULT_NPS

    if not is_valid_date_string(doj):
        doj = ""

    return [
        safe_str(st.session_state.spoc_name),
        safe_str(st.session_state.student_touch_val),
        safe_str(st.session_state.student_name_val),
        safe_str(st.session_state.cmisid_val),
        safe_str(st.session_state.contact_number_val),
        safe_str(st.session_state.contactable_val),
        retention_status,
        safe_int(st.session_state.months_working_val, DEFAULT_MONTHS),
        current_company,
        current_salary,
        current_designation,
        doj,
        reason_leaving,
        need_job,
        nps,
        str(st.session_state.verification_date_val),
        safe_str(st.session_state.remarks_val)
    ]


# ============================================================
# 🧾 UI SECTIONS
# ============================================================
def render_top_banner():
    st.markdown("""
        <div class="top-banner">
            <h2>✅ Student Verification System</h2>
            <p>Capture verification outcomes, fetch prior records, clear forms safely, and create the next entry quickly.</p>
        </div>
    """, unsafe_allow_html=True)


def render_sidebar():
    st.sidebar.markdown("## Navigation")

    if st.session_state.logged_in:
        st.sidebar.success(f"👤 Logged in as: {st.session_state.spoc_name}")
        st.sidebar.markdown("---")
        st.sidebar.caption("Use the form to fetch old details, submit a record, clear the current form, or create another entry.")
        st.sidebar.markdown("---")

        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.spoc_name = ""
            clear_all_form_fields()
            st.success("👋 Logged out successfully.")
            st.rerun()
    else:
        return st.sidebar.selectbox("Select Option", ["Login", "Register"])

    return None


def render_environment_info(mode: str):
    if mode == "cloud":
        info_box("☁️ Running on Streamlit Cloud (Secrets Loaded)")
    elif mode == "local":
        info_box("💻 Running Locally (service_account.json Loaded)")


def render_post_submit_actions():
    if st.session_state.show_post_submit_actions:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">After Submission</div>', unsafe_allow_html=True)

        if st.session_state.last_submit_success:
            success_box(st.session_state.last_submit_message or "✅ Data submitted successfully.")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("➕ Create Another"):
                clear_all_form_fields()
                st.rerun()
        with col2:
            if st.button("Keep Current Screen"):
                st.session_state.show_post_submit_actions = False
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)


def render_fetch_section(test2_records: List[Dict[str, Any]]):
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🔎 Fetch Existing Data From Test2</div>', unsafe_allow_html=True)

    col1, col2 = st.columns([4, 1])

    with col1:
        fetch_contact = st.text_input(
            "Enter Contact Number to Auto Fetch",
            value=st.session_state.contact_number_val,
            key="fetch_contact_input"
        )

    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Fetch Data"):
            st.session_state.contact_number_val = fetch_contact
            row = fetch_matching_test2_row(test2_records, fetch_contact)
            if row:
                load_test2_row_into_session(row)
            else:
                st.session_state.match_found = False
                st.session_state.matched_source_note = "⚠️ No matching contact number found in Test2."
            st.rerun()

    if st.session_state.matched_source_note:
        if st.session_state.match_found:
            success_box(st.session_state.matched_source_note)
        else:
            warning_box(st.session_state.matched_source_note)

    st.markdown("</div>", unsafe_allow_html=True)


def render_form_summary():
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Quick Summary</div>', unsafe_allow_html=True)

    chips = [
        f"SPOC: {safe_str(st.session_state.spoc_name) or '-'}",
        f"Retention: {safe_str(st.session_state.retention_status_val) or '-'}",
        f"Contact: {safe_str(st.session_state.contact_number_val) or '-'}",
        f"Company: {safe_str(st.session_state.current_company_val) or '-'}",
        f"NPS: {safe_str(st.session_state.nps_val) or DEFAULT_NPS}"
    ]

    st.markdown("".join([f'<span class="summary-chip">{chip}</span>' for chip in chips]), unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_main_form(main_sheet):
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">📝 Verification Entry Form</div>', unsafe_allow_html=True)

    with st.form("entry_form", clear_on_submit=False):
        col1, col2, col3 = st.columns(3)

        # --------------------------------------------------------
        # COL 1: BASIC DETAILS
        # --------------------------------------------------------
        with col1:
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">👤 Basic Details</div>', unsafe_allow_html=True)

            st.text_input(
                "SPOC Name",
                value=st.session_state.spoc_name,
                disabled=True
            )

            st.selectbox(
                "Students Touch Method",
                options=STUDENT_TOUCH_OPTIONS,
                index=safe_index(STUDENT_TOUCH_OPTIONS, st.session_state.student_touch_val, 0),
                key="student_touch_val"
            )

            st.text_input(
                "Student Name",
                key="student_name_val"
            )

            st.text_input(
                "CMIS ID",
                key="cmisid_val"
            )

            st.text_input(
                "Contact Number",
                key="contact_number_val"
            )

            st.selectbox(
                "Contactable",
                options=CONTACTABLE_OPTIONS,
                index=safe_index(CONTACTABLE_OPTIONS, st.session_state.contactable_val, 0),
                key="contactable_val"
            )

            st.markdown("</div>", unsafe_allow_html=True)

        # --------------------------------------------------------
        # COL 2: EMPLOYMENT DETAILS
        # --------------------------------------------------------
        with col2:
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">🏢 Employment Details</div>', unsafe_allow_html=True)

            st.selectbox(
                "Retention Status",
                options=RETENTION_STATUS_OPTIONS,
                index=safe_index(RETENTION_STATUS_OPTIONS, st.session_state.retention_status_val, 0),
                key="retention_status_val",
                on_change=on_retention_change
            )

            auto_clear = needs_auto_clear(st.session_state.retention_status_val)

            st.number_input(
                "Months Working",
                min_value=0,
                step=1,
                key="months_working_val"
            )

            st.text_input(
                "Company Name",
                key="current_company_val",
                disabled=auto_clear
            )

            st.text_input(
                "Salary",
                key="current_salary_val",
                disabled=auto_clear
            )

            st.text_input(
                "DEG",
                key="current_designation_val",
                disabled=auto_clear
            )

            st.text_input(
                f"DOJ ({DATE_FORMAT_HINT})",
                key="doj_val",
                disabled=auto_clear,
                help="Leave blank if not available."
            )

            if auto_clear:
                warning_box("For this Retention Status, Company Name, Salary, DEG, DOJ, Reason, Need Job and NPS are auto-cleared.")
            else:
                st.markdown('<div class="small-muted">DOJ can be blank or in YYYY-MM-DD format.</div>', unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)

        # --------------------------------------------------------
        # COL 3: FEEDBACK DETAILS
        # --------------------------------------------------------
        with col3:
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">📋 Verification Feedback</div>', unsafe_allow_html=True)

            auto_clear = needs_auto_clear(st.session_state.retention_status_val)

            st.selectbox(
                "Reason",
                options=REASON_OPTIONS,
                index=safe_index(REASON_OPTIONS, st.session_state.reason_leaving_val, 0),
                key="reason_leaving_val",
                disabled=auto_clear
            )

            st.selectbox(
                "Need Job",
                options=NEED_JOB_OPTIONS,
                index=safe_index(NEED_JOB_OPTIONS, st.session_state.need_job_val, 0),
                key="need_job_val",
                disabled=auto_clear
            )

            st.selectbox(
                "NPS",
                options=NPS_OPTIONS,
                index=safe_index(NPS_OPTIONS, st.session_state.nps_val, 0),
                key="nps_val",
                disabled=auto_clear
            )

            st.date_input(
                "Verification Date",
                key="verification_date_val"
            )

            st.selectbox(
                "Remarks",
                options=REMARKS_OPTIONS,
                index=safe_index(REMARKS_OPTIONS, st.session_state.remarks_val, 0),
                key="remarks_val"
            )

            st.markdown("</div>", unsafe_allow_html=True)

        # --------------------------------------------------------
        # ACTION BUTTONS
        # --------------------------------------------------------
        action_col1, action_col2, action_col3 = st.columns(3)

        with action_col1:
            submitted = st.form_submit_button("Submit Data ✅")

        with action_col2:
            clear_clicked = st.form_submit_button("Clear Form 🧹")

        with action_col3:
            create_another_clicked = st.form_submit_button("Create Another ➕")

    st.markdown("</div>", unsafe_allow_html=True)

    # ------------------------------------------------------------
    # POST-FORM ACTION LOGIC
    # ------------------------------------------------------------
    if clear_clicked:
        clear_all_form_fields()
        st.success("🧹 All form data cleared.")
        st.rerun()

    if create_another_clicked:
        clear_all_form_fields()
        st.success("➕ Ready for a new entry.")
        st.rerun()

    if submitted:
        persist_current_form_to_session()
        errors = validate_form()

        if errors:
            for err in errors:
                st.error(f"❌ {err}")
            return

        row = build_submission_row()

        try:
            main_sheet.append_row(row)
            st.session_state.last_submit_success = True
            st.session_state.last_submit_message = "✅ Data submitted successfully. You can now create another fresh entry."
            st.session_state.show_post_submit_actions = True
            st.success("✅ Data submitted!")
            st.rerun()
        except Exception as e:
            st.error("❌ Failed to submit data")
            st.exception(e)


# ============================================================
# 🔐 AUTH PAGES
# ============================================================
def show_register(login_sheet):
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">🆕 SPOC Registration</div>', unsafe_allow_html=True)

    info_box("Create a new SPOC account for accessing the Student Verification Form.")

    new_user = st.text_input("Enter SPOC Name", key="register_user")
    new_password = st.text_input("Enter Password", type="password", key="register_pass")

    if st.button("Register"):
        if new_user and new_password:
            try:
                records = load_login_records(login_sheet)
                existing_users = [safe_str(r.get("spoc_name", "")) for r in records]

                if new_user in existing_users:
                    st.error("❌ SPOC name already exists!")
                else:
                    hashed = hash_password(new_password)
                    created_at = now_str()
                    login_sheet.append_row([new_user, hashed, created_at])
                    st.success("✅ Registration successful!")
            except Exception as e:
                st.error("❌ Registration failed")
                st.exception(e)
        else:
            st.warning("⚠️ Enter both fields!")

    st.markdown("</div>", unsafe_allow_html=True)


def show_login(login_sheet):
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">🔐 SPOC Login Portal</div>', unsafe_allow_html=True)

    info_box("Use your registered SPOC credentials to access the verification panel.")

    username = st.text_input("Enter SPOC Name", key="login_user")
    password = st.text_input("Enter Password", type="password", key="login_pass")

    if st.button("Login"):
        try:
            records = load_login_records(login_sheet)
            user_data = next(
                (r for r in records if safe_str(r.get("spoc_name", "")) == safe_str(username)),
                None
            )

            if user_data and verify_password(password, safe_str(user_data.get("password", ""))):
                st.session_state.logged_in = True
                st.session_state.spoc_name = username
                st.success(f"✅ Welcome {username}!")
                st.rerun()
            else:
                st.error("❌ Invalid Username or Password")
        except Exception as e:
            st.error("❌ Login failed")
            st.exception(e)

    st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# 🏠 MAIN APP FLOW
# ============================================================
def show_main_screen(main_sheet, fetch_sheet, mode: str):
    render_top_banner()
    render_environment_info(mode)
    render_post_submit_actions()

    test2_records = load_test2_records(fetch_sheet)
    render_fetch_section(test2_records)
    render_form_summary()
    render_main_form(main_sheet)


# ============================================================
# 🚀 APP START
# ============================================================
def main():
    init_app_state()

    try:
        main_sheet, login_sheet, fetch_sheet, mode = get_sheets()
    except Exception as e:
        st.error("❌ Google Sheet connection failed. Check sheet names, permissions, and credentials.")
        st.exception(e)
        st.stop()

    choice = render_sidebar()

    if not st.session_state.logged_in:
        if choice == "Login":
            show_login(login_sheet)
        else:
            show_register(login_sheet)
    else:
        show_main_screen(main_sheet, fetch_sheet, mode)

    st.markdown("""
        <div class="footer">
            © 2025 Nibedan Foundation | Student Verification System
        </div>
    """, unsafe_allow_html=True)


# ============================================================
# ENTRYPOINT
# ============================================================
if __name__ == "__main__":
    main()