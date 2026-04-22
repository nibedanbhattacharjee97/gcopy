import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date, datetime
import hashlib
import os
import re

# ============================================================
# ⚙️ PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="Student Verification Entry Form",
    page_icon="✅",
    layout="wide"
)

# ============================================================
# 🌈 PAGE STYLE
# ============================================================
st.markdown("""
    <style>
        .main {
            background: linear-gradient(135deg, #00aaff, #00ffaa);
        }

        .login-card {
            background-color: white;
            border-radius: 16px;
            padding: 2rem;
            box-shadow: 0px 4px 12px rgba(0,0,0,0.2);
            width: 420px;
            margin: auto;
            text-align: center;
        }

        .login-title {
            color: #007bff;
            font-size: 1.5rem;
            font-weight: 700;
            margin-bottom: 1rem;
        }

        .footer {
            text-align: center;
            font-size: 0.9rem;
            color: #666;
            margin-top: 2rem;
        }

        .stButton > button {
            background-color: #007bff;
            color: white;
            font-weight: bold;
            border-radius: 8px;
            height: 2.7em;
            width: 100%;
            border: none;
        }

        .stButton > button:hover {
            background-color: #0056b3;
            color: white;
        }

        .section-card {
            background-color: rgba(255,255,255,0.92);
            padding: 1rem;
            border-radius: 12px;
            margin-bottom: 1rem;
            box-shadow: 0px 2px 10px rgba(0,0,0,0.08);
        }

        .form-title {
            font-size: 1.15rem;
            font-weight: 700;
            color: #0056b3;
            margin-bottom: 0.5rem;
        }

        .success-box {
            background: #eafaf1;
            border-left: 5px solid #28a745;
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 10px;
        }

        .info-box {
            background: #eef6ff;
            border-left: 5px solid #007bff;
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 10px;
        }

        .warning-box {
            background: #fff8e5;
            border-left: 5px solid #ff9800;
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 10px;
        }

        .danger-box {
            background: #ffeaea;
            border-left: 5px solid #dc3545;
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 10px;
        }

        .neutral-box {
            background: #f7f7f7;
            border-left: 5px solid #6c757d;
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 10px;
        }

        .small-note {
            font-size: 0.85rem;
            color: #555;
        }

        .stTextInput input:disabled,
        .stSelectbox div[data-baseweb="select"] > div[aria-disabled="true"] {
            background-color: #f8f9fa !important;
            opacity: 1 !important;
        }
    </style>
""", unsafe_allow_html=True)

# ============================================================
# 🔐 PASSWORD UTILITIES
# ============================================================
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()


def verify_password(password, hashed):
    return hash_password(password) == hashed


# ============================================================
# 🔧 CONSTANTS
# ============================================================
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

CLEAR_RETENTION_STATUSES = [
    "Unable_to_track",
    "Not_working_at_all",
    "Rejected",
    "Hold",
    "Confirmed Name But Didn't Share Any Information.",
    "Confirmed Name & Disconnected"
]

STUDENT_TOUCH_OPTIONS = [
    "Tikona_Call",
    "SPOC_call"
]

CONTACTABLE_OPTIONS = [
    "Yes",
    "No"
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

DEFAULT_REASON = ""
DEFAULT_NEED_JOB = ""
DEFAULT_NPS = "--"

# ============================================================
# 🔧 HELPER FUNCTIONS
# ============================================================
def safe_str(value):
    if value is None:
        return ""
    return str(value).strip()


def normalize_contact(number):
    """
    Normalize contact number for matching:
    remove spaces, +91, dashes etc.
    """
    value = safe_str(number)
    value = value.replace(" ", "")
    value = value.replace("-", "")
    value = value.replace("(", "")
    value = value.replace(")", "")
    value = value.replace(".", "")
    if value.startswith("+91"):
        value = value[3:]
    return value


def parse_any_date_to_string(raw_value):
    """
    Convert many possible sheet date formats into YYYY-MM-DD string.
    Return blank if invalid or empty.
    """
    raw_value = safe_str(raw_value)

    if not raw_value:
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
            return datetime.strptime(raw_value, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass

    try:
        return datetime.fromisoformat(raw_value).strftime("%Y-%m-%d")
    except Exception:
        return ""


def is_valid_yyyy_mm_dd(value):
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


def is_clear_status(retention_status):
    return retention_status in CLEAR_RETENTION_STATUSES


def normalize_reason(value):
    value = safe_str(value)
    return value if value in REASON_OPTIONS else DEFAULT_REASON


def normalize_need_job(value):
    value = safe_str(value)
    return value if value in NEED_JOB_OPTIONS else DEFAULT_NEED_JOB


def normalize_nps(value):
    value = safe_str(value)
    return value if value in NPS_OPTIONS else DEFAULT_NPS


def safe_index(options, value, fallback=0):
    try:
        return options.index(value)
    except ValueError:
        return fallback


def get_now_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def blank_employment_fields():
    st.session_state.current_company_val = ""
    st.session_state.current_salary_val = ""
    st.session_state.current_designation_val = ""
    st.session_state.doj_val = ""
    st.session_state.reason_leaving_val = DEFAULT_REASON
    st.session_state.need_job_val = DEFAULT_NEED_JOB
    st.session_state.nps_val = DEFAULT_NPS


def init_form_session():
    """
    Initialize editable form field session states
    """
    defaults = {
        "student_name_val": "",
        "cmisid_val": "",
        "contact_number_val": "",
        "current_company_val": "",
        "current_salary_val": "",
        "current_designation_val": "",
        "doj_val": "",
        "match_found": False,
        "matched_source_note": "",
        "student_touch_val": STUDENT_TOUCH_OPTIONS[0],
        "contactable_val": CONTACTABLE_OPTIONS[0],
        "retention_status_val": RETENTION_STATUS_OPTIONS[0],
        "months_working_val": 0,
        "reason_leaving_val": DEFAULT_REASON,
        "need_job_val": DEFAULT_NEED_JOB,
        "nps_val": DEFAULT_NPS,
        "verification_date_val": date.today(),
        "remarks_val": REMARKS_OPTIONS[0],
        "last_submit_success": False,
        "last_submit_message": "",
        "show_create_another": False
    }

    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def clear_form_session():
    """
    Reset all form-related session states for fresh entry
    """
    st.session_state.student_name_val = ""
    st.session_state.cmisid_val = ""
    st.session_state.contact_number_val = ""
    st.session_state.student_touch_val = STUDENT_TOUCH_OPTIONS[0]
    st.session_state.contactable_val = CONTACTABLE_OPTIONS[0]
    st.session_state.retention_status_val = RETENTION_STATUS_OPTIONS[0]
    st.session_state.months_working_val = 0

    blank_employment_fields()

    st.session_state.verification_date_val = date.today()
    st.session_state.remarks_val = REMARKS_OPTIONS[0]
    st.session_state.match_found = False
    st.session_state.matched_source_note = ""
    st.session_state.last_submit_success = False
    st.session_state.last_submit_message = ""
    st.session_state.show_create_another = False


def clear_after_submit_for_new_entry():
    """
    Clear everything needed after clicking Create Another
    """
    clear_form_session()


def fetch_test2_match(test2_records, contact_number):
    """
    Find matching row in Test2 by Contact Number
    """
    target = normalize_contact(contact_number)

    if not target:
        return None

    for row in test2_records:
        sheet_contact = normalize_contact(row.get("Contact Number", ""))
        if sheet_contact == target:
            return row

    return None


def load_from_test2_to_session(test2_records, contact_number):
    """
    Load matched Test2 row into editable session fields
    """
    matched_row = fetch_test2_match(test2_records, contact_number)

    if matched_row:
        st.session_state.cmisid_val = safe_str(matched_row.get("CMIS ID", ""))
        st.session_state.current_company_val = safe_str(matched_row.get("Company Name", ""))
        st.session_state.current_salary_val = safe_str(matched_row.get("Salary", ""))
        st.session_state.current_designation_val = safe_str(matched_row.get("Deg", ""))
        st.session_state.doj_val = parse_any_date_to_string(matched_row.get("DOJ", ""))
        st.session_state.match_found = True
        st.session_state.matched_source_note = "✅ Test2 sheet match found. Fields auto-filled and still editable."
        return True
    else:
        st.session_state.match_found = False
        st.session_state.matched_source_note = "⚠️ No matching contact number found in Test2."
        return False


def apply_retention_rules_to_session(retention_status):
    """
    Auto-clear dependent fields for selected retention status
    """
    st.session_state.retention_status_val = retention_status

    if is_clear_status(retention_status):
        blank_employment_fields()


def prepare_submission_values(
    spoc_name,
    student_touch,
    student_name,
    cmisid,
    contact_number,
    contactable,
    retention_status,
    months_working,
    current_company,
    current_salary,
    current_designation,
    doj,
    reason_leaving,
    need_job,
    nps,
    verification_date,
    remarks
):
    """
    Final normalization before appending to sheet
    """
    student_touch = safe_str(student_touch)
    student_name = safe_str(student_name)
    cmisid = safe_str(cmisid)
    contact_number = safe_str(contact_number)
    contactable = safe_str(contactable)
    retention_status = safe_str(retention_status)
    current_company = safe_str(current_company)
    current_salary = safe_str(current_salary)
    current_designation = safe_str(current_designation)
    doj = safe_str(doj)
    reason_leaving = safe_str(reason_leaving)
    need_job = safe_str(need_job)
    nps = safe_str(nps)
    remarks = safe_str(remarks)

    if retention_status in CLEAR_RETENTION_STATUSES:
        current_company = ""
        current_salary = ""
        current_designation = ""
        doj = ""
        reason_leaving = DEFAULT_REASON
        need_job = DEFAULT_NEED_JOB
        nps = DEFAULT_NPS

    if not is_valid_yyyy_mm_dd(doj):
        doj = ""

    try:
        verification_date_str = str(verification_date)
    except Exception:
        verification_date_str = str(date.today())

    return [
        safe_str(spoc_name),
        student_touch,
        student_name,
        cmisid,
        contact_number,
        contactable,
        retention_status,
        months_working,
        current_company,
        current_salary,
        current_designation,
        doj,
        reason_leaving,
        need_job,
        nps,
        verification_date_str,
        remarks
    ]


def persist_last_entered_non_cleared_values(
    student_touch,
    student_name,
    cmisid,
    contact_number,
    contactable,
    retention_status,
    months_working,
    current_company,
    current_salary,
    current_designation,
    doj,
    reason_leaving,
    need_job,
    nps,
    verification_date,
    remarks
):
    """
    Keep latest visible values in session.
    For clear statuses, force employment-related fields blank.
    """
    st.session_state.student_touch_val = student_touch
    st.session_state.student_name_val = student_name
    st.session_state.cmisid_val = cmisid
    st.session_state.contact_number_val = contact_number
    st.session_state.contactable_val = contactable
    st.session_state.retention_status_val = retention_status
    st.session_state.months_working_val = months_working
    st.session_state.verification_date_val = verification_date
    st.session_state.remarks_val = remarks

    if is_clear_status(retention_status):
        blank_employment_fields()
    else:
        st.session_state.current_company_val = current_company
        st.session_state.current_salary_val = current_salary
        st.session_state.current_designation_val = current_designation
        st.session_state.doj_val = doj
        st.session_state.reason_leaving_val = normalize_reason(reason_leaving)
        st.session_state.need_job_val = normalize_need_job(need_job)
        st.session_state.nps_val = normalize_nps(nps)


def validate_form_before_submit(student_name, contact_number, doj):
    errors = []

    if not safe_str(student_name):
        errors.append("Student Name is required.")

    if not safe_str(contact_number):
        errors.append("Contact Number is required.")

    if safe_str(doj) and not is_valid_yyyy_mm_dd(doj):
        errors.append("DOJ must be in YYYY-MM-DD format.")

    return errors


# ============================================================
# 🔐 GOOGLE AUTHENTICATION
# ============================================================
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

credentials = None

if "gcp_service_account" in st.secrets:
    try:
        credentials = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=scope
        )
        st.info("☁️ Running on Streamlit Cloud (Secrets Loaded)")
    except Exception as e:
        st.error("❌ Invalid Streamlit Secrets format")
        st.exception(e)
        st.stop()

elif os.path.exists("service_account.json"):
    try:
        credentials = Credentials.from_service_account_file(
            "service_account.json",
            scopes=scope
        )
        st.info("💻 Running Locally (JSON Loaded)")
    except Exception as e:
        st.error("❌ Error loading local service_account.json")
        st.exception(e)
        st.stop()

else:
    st.error("❌ No credentials found:\n\n➡️ Add service_account.json locally\nOR\n➡️ Add gcp_service_account in Streamlit Secrets")
    st.stop()

# ============================================================
# 📡 CONNECT GSPREAD
# ============================================================
client = gspread.authorize(credentials)

# ============================================================
# 📄 GOOGLE SHEETS CONNECTIONS
# ============================================================
try:
    sheet = client.open("Test").sheet1
    login_sheet = client.open("Test_Spoc_PassWord").sheet1
    test2_sheet = client.open("Test2").sheet1
except Exception as e:
    st.error("❌ Google Sheet connection failed. Check sheet names and sharing permissions.")
    st.exception(e)
    st.stop()

# ============================================================
# 🔑 SESSION STATE INIT
# ============================================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "spoc_name" not in st.session_state:
    st.session_state.spoc_name = ""

init_form_session()

# ============================================================
# SIDEBAR (LOGIN / REGISTER / LOGOUT FULL)
# ============================================================
if not st.session_state.logged_in:
    menu = ["Login", "Register"]
    choice = st.sidebar.selectbox("Select Option", menu)

if st.session_state.logged_in:
    st.sidebar.markdown("---")
    st.sidebar.success(f"👤 Logged in as: {st.session_state.spoc_name}")
    st.sidebar.markdown("---")

    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.spoc_name = ""
        clear_form_session()
        st.success("👋 Logged out successfully.")
        st.rerun()

# ============================================================
# REGISTER PAGE
# ============================================================
def show_register():
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">🆕 SPOC Registration</div>', unsafe_allow_html=True)

    st.markdown(
        '<div class="info-box">Create a new SPOC account for accessing the Student Verification Form.</div>',
        unsafe_allow_html=True
    )

    new_user = st.text_input("Enter SPOC Name")
    new_password = st.text_input("Enter Password", type="password")

    if st.button("Register"):
        if new_user and new_password:
            try:
                all_records = login_sheet.get_all_records()
                existing_users = [safe_str(r.get("spoc_name", "")) for r in all_records]

                if new_user in existing_users:
                    st.error("❌ SPOC name already exists!")
                else:
                    hashed_pass = hash_password(new_password)
                    created_date = get_now_timestamp()
                    login_sheet.append_row([new_user, hashed_pass, created_date])
                    st.success("✅ Registration successful!")
            except Exception as e:
                st.error("❌ Registration failed")
                st.exception(e)
        else:
            st.warning("⚠️ Enter both fields!")

    st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# LOGIN PAGE
# ============================================================
def show_login():
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">🔐 SPOC Login Portal</div>', unsafe_allow_html=True)

    st.markdown(
        '<div class="info-box">Use your registered SPOC credentials to access the verification panel.</div>',
        unsafe_allow_html=True
    )

    username = st.text_input("Enter SPOC Name")
    password = st.text_input("Enter Password", type="password")

    if st.button("Login"):
        try:
            all_records = login_sheet.get_all_records()
            user_data = next(
                (r for r in all_records if safe_str(r.get("spoc_name", "")) == safe_str(username)),
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
# MAIN VERIFICATION FORM UI
# ============================================================
def show_main_form():

    # --------------------------------------------------------
    # 1. Load latest Test2 data
    # --------------------------------------------------------
    try:
        test2_data = test2_sheet.get_all_records()
    except Exception as e:
        test2_data = []
        st.error("❌ Unable to read Test2 sheet")
        st.exception(e)

    # --------------------------------------------------------
    # 2. Submission Success + Create Another
    # --------------------------------------------------------
    if st.session_state.last_submit_success:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="form-title">✅ Last Submission Status</div>', unsafe_allow_html=True)

        st.markdown(
            f'<div class="success-box">{safe_str(st.session_state.last_submit_message) or "✅ Data submitted successfully!"}</div>',
            unsafe_allow_html=True
        )

        create_col1, create_col2 = st.columns([1, 1])

        with create_col1:
            if st.button("➕ Create Another"):
                clear_after_submit_for_new_entry()
                st.rerun()

        with create_col2:
            if st.button("🔄 Stay With Current Values"):
                st.session_state.last_submit_success = False
                st.session_state.last_submit_message = ""
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    # --------------------------------------------------------
    # 3. Top helper section
    # --------------------------------------------------------
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="form-title">🔎 Fetch Existing Data From Test2</div>', unsafe_allow_html=True)

    fetch_col1, fetch_col2 = st.columns([4, 1])

    with fetch_col1:
        entered_contact = st.text_input(
            "Enter Contact Number to Auto Fetch",
            value=st.session_state.contact_number_val,
            key="fetch_contact_number_top"
        )

    with fetch_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Fetch Data"):
            st.session_state.contact_number_val = entered_contact
            load_from_test2_to_session(test2_data, entered_contact)
            st.rerun()

    if st.session_state.matched_source_note:
        if st.session_state.match_found:
            st.markdown(
                f'<div class="success-box">{st.session_state.matched_source_note}</div>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f'<div class="warning-box">{st.session_state.matched_source_note}</div>',
                unsafe_allow_html=True
            )

    st.markdown("</div>", unsafe_allow_html=True)

    # --------------------------------------------------------
    # 4. Main form
    # --------------------------------------------------------
    with st.form("entry_form"):

        col1, col2, col3 = st.columns(3)

        # ----------------------------------------------------
        # COL 1 - BASIC DETAILS
        # ----------------------------------------------------
        with col1:
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown('<div class="form-title">👤 Basic Details</div>', unsafe_allow_html=True)

            st.text_input(
                "SPOC Name",
                st.session_state.spoc_name,
                disabled=True
            )

            student_touch = st.selectbox(
                "Students Touch Method",
                STUDENT_TOUCH_OPTIONS,
                index=safe_index(STUDENT_TOUCH_OPTIONS, st.session_state.student_touch_val, 0)
            )

            student_name = st.text_input(
                "Student Name",
                value=st.session_state.student_name_val
            )

            cmisid = st.text_input(
                "CMIS ID",
                value=st.session_state.cmisid_val
            )

            contact_number = st.text_input(
                "Contact Number",
                value=st.session_state.contact_number_val
            )

            contactable = st.selectbox(
                "Contactable",
                CONTACTABLE_OPTIONS,
                index=safe_index(CONTACTABLE_OPTIONS, st.session_state.contactable_val, 0)
            )

            st.markdown("</div>", unsafe_allow_html=True)

        # ----------------------------------------------------
        # COL 2 - EMPLOYMENT DETAILS
        # ----------------------------------------------------
        with col2:
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown('<div class="form-title">🏢 Employment Details</div>', unsafe_allow_html=True)

            retention_status = st.selectbox(
                "Retention Status",
                RETENTION_STATUS_OPTIONS,
                index=safe_index(RETENTION_STATUS_OPTIONS, st.session_state.retention_status_val, 0)
            )

            if is_clear_status(retention_status):
                company_default = ""
                salary_default = ""
                designation_default = ""
                doj_default = ""
            else:
                company_default = st.session_state.current_company_val
                salary_default = st.session_state.current_salary_val
                designation_default = st.session_state.current_designation_val
                doj_default = st.session_state.doj_val

            months_working = st.number_input(
                "Months Working",
                min_value=0,
                step=1,
                value=int(st.session_state.months_working_val)
            )

            current_company = st.text_input(
                "Company Name",
                value=company_default,
                disabled=is_clear_status(retention_status)
            )

            current_salary = st.text_input(
                "Salary",
                value=salary_default,
                disabled=is_clear_status(retention_status)
            )

            current_designation = st.text_input(
                "DEG",
                value=designation_default,
                disabled=is_clear_status(retention_status)
            )

            doj = st.text_input(
                "DOJ (YYYY-MM-DD)",
                value=doj_default,
                disabled=is_clear_status(retention_status),
                help="Leave blank if DOJ is not available."
            )

            if not is_clear_status(retention_status):
                if doj and not is_valid_yyyy_mm_dd(doj):
                    st.markdown(
                        '<div class="warning-box">⚠️ DOJ format should be YYYY-MM-DD</div>',
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(
                        '<div class="small-note">Use YYYY-MM-DD format. Example: 2025-01-31</div>',
                        unsafe_allow_html=True
                    )
            else:
                st.markdown(
                    '<div class="neutral-box">For this Retention Status, Company, Salary, DEG and DOJ will stay blank.</div>',
                    unsafe_allow_html=True
                )

            st.markdown("</div>", unsafe_allow_html=True)

        # ----------------------------------------------------
        # COL 3 - VERIFICATION FEEDBACK
        # ----------------------------------------------------
        with col3:
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown('<div class="form-title">📝 Verification Feedback</div>', unsafe_allow_html=True)

            if is_clear_status(retention_status):
                reason_default = DEFAULT_REASON
                need_job_default = DEFAULT_NEED_JOB
                nps_default = DEFAULT_NPS
            else:
                reason_default = normalize_reason(st.session_state.reason_leaving_val)
                need_job_default = normalize_need_job(st.session_state.need_job_val)
                nps_default = normalize_nps(st.session_state.nps_val)

            reason_leaving = st.selectbox(
                "Reason",
                REASON_OPTIONS,
                index=safe_index(REASON_OPTIONS, reason_default, 0),
                disabled=is_clear_status(retention_status)
            )

            need_job = st.selectbox(
                "Need Job",
                NEED_JOB_OPTIONS,
                index=safe_index(NEED_JOB_OPTIONS, need_job_default, 0),
                disabled=is_clear_status(retention_status)
            )

            nps = st.selectbox(
                "NPS",
                NPS_OPTIONS,
                index=safe_index(NPS_OPTIONS, nps_default, 0),
                disabled=is_clear_status(retention_status)
            )

            verification_date = st.date_input(
                "Verification Date",
                value=st.session_state.verification_date_val
            )

            remarks = st.selectbox(
                "Remarks",
                REMARKS_OPTIONS,
                index=safe_index(REMARKS_OPTIONS, st.session_state.remarks_val, 0)
            )

            if is_clear_status(retention_status):
                st.markdown(
                    '<div class="neutral-box">For this Retention Status, Reason, Need Job and NPS will stay blank / --.</div>',
                    unsafe_allow_html=True
                )

            st.markdown("</div>", unsafe_allow_html=True)

        # ----------------------------------------------------
        # SUBMIT BUTTON
        # ----------------------------------------------------
        submit_col1, = st.columns(1)

        with submit_col1:
            submitted = st.form_submit_button("Submit Data ✅")

    # --------------------------------------------------------
    # 5. Submit logic
    # --------------------------------------------------------
    if submitted:
        try:
            validation_errors = validate_form_before_submit(
                student_name=student_name,
                contact_number=contact_number,
                doj=doj
            )

            if validation_errors:
                for err in validation_errors:
                    st.error(f"❌ {err}")
                return

            submission_data = prepare_submission_values(
                spoc_name=st.session_state.spoc_name,
                student_touch=student_touch,
                student_name=student_name,
                cmisid=cmisid,
                contact_number=contact_number,
                contactable=contactable,
                retention_status=retention_status,
                months_working=months_working,
                current_company=current_company,
                current_salary=current_salary,
                current_designation=current_designation,
                doj=doj,
                reason_leaving=reason_leaving,
                need_job=need_job,
                nps=nps,
                verification_date=verification_date,
                remarks=remarks
            )

            sheet.append_row(submission_data)

            persist_last_entered_non_cleared_values(
                student_touch=student_touch,
                student_name=student_name,
                cmisid=cmisid,
                contact_number=contact_number,
                contactable=contactable,
                retention_status=retention_status,
                months_working=months_working,
                current_company=current_company,
                current_salary=current_salary,
                current_designation=current_designation,
                doj=doj,
                reason_leaving=reason_leaving,
                need_job=need_job,
                nps=nps,
                verification_date=verification_date,
                remarks=remarks
            )

            st.session_state.last_submit_success = True
            st.session_state.last_submit_message = "✅ Data submitted successfully. Click 'Create Another' to clear all fields for a new entry."
            st.success("✅ Data submitted!")
            st.rerun()

        except Exception as e:
            st.error("❌ Failed to submit data")
            st.exception(e)

# ============================================================
# ROUTING
# ============================================================
if not st.session_state.logged_in:
    if choice == "Login":
        show_login()
    else:
        show_register()
else:
    show_main_form()

# ============================================================
# FOOTER
# ============================================================
st.markdown("""
    <div class="footer">
        © 2025 Nibedan Foundation | Student Verification System
    </div>
""", unsafe_allow_html=True)