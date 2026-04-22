import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date, datetime
import hashlib
import os

# ============================================
# ⚙️ PAGE CONFIG
# ============================================
st.set_page_config(
    page_title="Student Verification Entry Form",
    page_icon="✅",
    layout="wide"
)

# ============================================
# 🌈 PAGE STYLE (UNCHANGED + FULL UI)
# ============================================
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

        .logout-button > button {
            background-color: #dc3545 !important;
            color: white !important;
            width: 100%;
        }

        .section-card {
            background-color: rgba(255,255,255,0.90);
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
    </style>
""", unsafe_allow_html=True)

# ============================================
# 🔐 PASSWORD UTILITIES (UNCHANGED)
# ============================================
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def verify_password(password, hashed):
    return hash_password(password) == hashed

# ============================================
# 🔧 HELPER FUNCTIONS
# ============================================
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
    if value.startswith("+91"):
        value = value[3:]
    return value

def parse_doj(raw_value):
    """
    Convert raw DOJ value from sheet to date safely
    """
    raw_value = safe_str(raw_value)

    if not raw_value:
        return date.today()

    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y/%m/%d"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(raw_value, fmt).date()
        except:
            pass

    try:
        return datetime.fromisoformat(raw_value).date()
    except:
        return date.today()

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
        "doj_val": date.today(),
        "match_found": False,
        "matched_source_note": ""
    }

    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

def clear_form_session():
    """
    Optional reset after submit
    """
    st.session_state.student_name_val = ""
    st.session_state.cmisid_val = ""
    st.session_state.contact_number_val = ""
    st.session_state.current_company_val = ""
    st.session_state.current_salary_val = ""
    st.session_state.current_designation_val = ""
    st.session_state.doj_val = date.today()
    st.session_state.match_found = False
    st.session_state.matched_source_note = ""

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
        st.session_state.doj_val = parse_doj(matched_row.get("DOJ", ""))
        st.session_state.match_found = True
        st.session_state.matched_source_note = "✅ Test2 sheet match found. Fields auto-filled and still editable."
        return True
    else:
        st.session_state.match_found = False
        st.session_state.matched_source_note = "⚠️ No matching contact number found in Test2."
        return False

# ============================================
# 🔐 GOOGLE AUTHENTICATION (KEEPING YOUR LOGIC)
# ============================================
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

# ============================================
# 📡 CONNECT GSPREAD
# ============================================
client = gspread.authorize(credentials)

# ============================================
# 📄 GOOGLE SHEETS CONNECTIONS
# ============================================
try:
    sheet = client.open("Test").sheet1
    login_sheet = client.open("Test_Spoc_PassWord").sheet1
    test2_sheet = client.open("Test2").sheet1
except Exception as e:
    st.error("❌ Google Sheet connection failed. Check sheet names and sharing permissions.")
    st.exception(e)
    st.stop()

# ============================================
# 🔑 SESSION STATE INIT
# ============================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "spoc_name" not in st.session_state:
    st.session_state.spoc_name = ""

init_form_session()

# ============================================
# SIDEBAR (LOGIN / REGISTER / LOGOUT FULL)
# ============================================
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

# ============================================
# REGISTER PAGE
# ============================================
def show_register():
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">🆕 SPOC Registration</div>', unsafe_allow_html=True)

    st.markdown('<div class="info-box">Create a new SPOC account for accessing the Student Verification Form.</div>', unsafe_allow_html=True)

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
                    created_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    login_sheet.append_row([new_user, hashed_pass, created_date])
                    st.success("✅ Registration successful!")
            except Exception as e:
                st.error("❌ Registration failed")
                st.exception(e)
        else:
            st.warning("⚠️ Enter both fields!")

    st.markdown("</div>", unsafe_allow_html=True)

# ============================================
# LOGIN PAGE
# ============================================
def show_login():
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">🔐 SPOC Login Portal</div>', unsafe_allow_html=True)

    st.markdown('<div class="info-box">Use your registered SPOC credentials to access the verification panel.</div>', unsafe_allow_html=True)

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

# ============================================
# MAIN VERIFICATION FORM UI
# ============================================
def show_main_form():

    # Load latest Test2 data
    try:
        test2_data = test2_sheet.get_all_records()
    except Exception as e:
        test2_data = []
        st.error("❌ Unable to read Test2 sheet")
        st.exception(e)

    # Top helper section
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

    # Main form
    with st.form("entry_form"):
        col1, col2, col3 = st.columns(3)

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
                ["Call", "WhatsApp", "SMS", "Email", "Other"]
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
                ["Yes", "No"]
            )

            st.markdown("</div>", unsafe_allow_html=True)

        with col2:
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown('<div class="form-title">🏢 Employment Details</div>', unsafe_allow_html=True)

            retention_status = st.selectbox(
                "Retention Status",
                ["Working", "Not Working", "Unknown"]
            )

            months_working = st.number_input(
                "Months Working",
                min_value=0,
                step=1
            )

            current_company = st.text_input(
                "Company",
                value=st.session_state.current_company_val
            )

            current_salary = st.text_input(
                "Salary",
                value=st.session_state.current_salary_val
            )

            current_designation = st.text_input(
                "Designation",
                value=st.session_state.current_designation_val
            )

            doj = st.date_input(
                "DOJ",
                value=st.session_state.doj_val
            )

            st.markdown("</div>", unsafe_allow_html=True)

        with col3:
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown('<div class="form-title">📝 Verification Feedback</div>', unsafe_allow_html=True)

            reason_leaving = st.text_area("Reason")
            need_job = st.selectbox("Need Job", ["Yes", "No"])
            nps = st.slider("NPS", 0, 10, 5)
            verification_date = st.date_input("Verification Date", value=date.today())
            remarks = st.text_area("Remarks")

            st.markdown("</div>", unsafe_allow_html=True)

        submit_col1, = st.columns(1)

        with submit_col1:
            submitted = st.form_submit_button("Submit Data ✅")


    # Submit logic
    if submitted:
        try:
            data = [
                st.session_state.spoc_name,
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
                str(doj),
                reason_leaving,
                need_job,
                nps,
                str(verification_date),
                remarks
            ]

            sheet.append_row(data)
            st.success("✅ Data submitted!")

            # Keep last typed values if needed, or clear selected fields
            st.session_state.student_name_val = student_name
            st.session_state.cmisid_val = cmisid
            st.session_state.contact_number_val = contact_number
            st.session_state.current_company_val = current_company
            st.session_state.current_salary_val = current_salary
            st.session_state.current_designation_val = current_designation
            st.session_state.doj_val = doj

        except Exception as e:
            st.error("❌ Failed to submit data")
            st.exception(e)

# ============================================
# ROUTING
# ============================================
if not st.session_state.logged_in:
    if choice == "Login":
        show_login()
    else:
        show_register()
else:
    show_main_form()

# ============================================
# FOOTER
# ============================================
st.markdown("""
    <div class="footer">
        © 2025 Nibedan Foundation | Student Verification System
    </div>
""", unsafe_allow_html=True)