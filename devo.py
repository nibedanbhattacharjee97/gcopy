import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date, datetime
import hashlib
import os

# ============================================
# ⚙️ PAGE CONFIG
# ============================================
st.set_page_config(page_title="Student Verification Entry Form", page_icon="✅", layout="wide")

# ============================================
# 🌈 PAGE STYLE (UNCHANGED)
# ============================================
st.markdown("""
    <style>
        .main { background: linear-gradient(135deg, #00aaff, #00ffaa); }
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
        .stButton>button {
            background-color: #007bff;
            color: white;
            font-weight: bold;
            border-radius: 8px;
            height: 2.5em;
            width: 100%;
        }
        .stButton>button:hover { background-color: #0056b3; }
        .logout-button>button {
            background-color: #dc3545 !important;
            color: white !important;
            width: 100%;
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
# 🔐 GOOGLE AUTHENTICATION (FIXED)
# ============================================
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

credentials = None

# 🔥 FIXED LOGIC (Clear detection)
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

# Connect
client = gspread.authorize(credentials)

# ============================================
# 📄 GOOGLE SHEETS CONNECTIONS (UNCHANGED)
# ============================================
sheet = client.open("Test").sheet1
login_sheet = client.open("Test_Spoc_PassWord").sheet1

# ============================================
# 🔑 SESSION STATE INIT (UNCHANGED)
# ============================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "spoc_name" not in st.session_state:
    st.session_state.spoc_name = ""

# ============================================
# SIDEBAR (UNCHANGED)
# ============================================
if not st.session_state.logged_in:
    menu = ["Login", "Register"]
    choice = st.sidebar.selectbox("Select Option", menu)

if st.session_state.logged_in:
    st.sidebar.markdown("---")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.spoc_name = ""
        st.success("👋 Logged out successfully.")
        st.rerun()

# ============================================
# REGISTER (UNCHANGED)
# ============================================
def show_register():
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">🆕 SPOC Registration</div>', unsafe_allow_html=True)

    new_user = st.text_input("Enter SPOC Name")
    new_password = st.text_input("Enter Password", type="password")

    if st.button("Register"):
        if new_user and new_password:
            all_records = login_sheet.get_all_records()
            existing_users = [r.get("spoc_name", "") for r in all_records]

            if new_user in existing_users:
                st.error("❌ SPOC name already exists!")
            else:
                hashed_pass = hash_password(new_password)
                created_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                login_sheet.append_row([new_user, hashed_pass, created_date])
                st.success("✅ Registration successful!")
        else:
            st.warning("⚠️ Enter both fields!")

    st.markdown("</div>", unsafe_allow_html=True)

# ============================================
# LOGIN (UNCHANGED)
# ============================================
def show_login():
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">🔐 SPOC Login Portal</div>', unsafe_allow_html=True)

    username = st.text_input("Enter SPOC Name")
    password = st.text_input("Enter Password", type="password")

    if st.button("Login"):
        all_records = login_sheet.get_all_records()
        user_data = next((r for r in all_records if r.get("spoc_name", "") == username), None)

        if user_data and verify_password(password, user_data.get("password", "")):
            st.session_state.logged_in = True
            st.session_state.spoc_name = username
            st.success(f"✅ Welcome {username}!")
            st.rerun()
        else:
            st.error("❌ Invalid Username or Password")

    st.markdown("</div>", unsafe_allow_html=True)

# ============================================
# MAIN FORM (UNCHANGED)
# ============================================
def show_main_form():
    st.title("📋 Student Verification Entry Form")
    st.markdown("---")

    with st.form("entry_form"):
        col1, col2, col3 = st.columns(3)

        with col1:
            st.text_input("SPOC Name", st.session_state.spoc_name, disabled=True)
            student_touch = st.selectbox("Students Touch Method", ["Call", "WhatsApp", "SMS", "Email", "Other"])
            student_name = st.text_input("Student Name")
            cmisid = st.text_input("CMIS ID")
            contact_number = st.text_input("Contact Number")
            contactable = st.selectbox("Contactable", ["Yes", "No"])

        with col2:
            retention_status = st.selectbox("Retention Status", ["Working", "Not Working", "Unknown"])
            months_working = st.number_input("Months Working", min_value=0)
            current_company = st.text_input("Company")
            current_salary = st.text_input("Salary")
            current_designation = st.text_input("Designation")
            doj = st.date_input("DOJ")

        with col3:
            reason_leaving = st.text_area("Reason")
            need_job = st.selectbox("Need Job", ["Yes", "No"])
            nps = st.slider("NPS", 0, 10, 5)
            verification_date = st.date_input("Verification Date", value=date.today())
            remarks = st.text_area("Remarks")

        submitted = st.form_submit_button("Submit Data ✅")

    if submitted:
        data = [
            st.session_state.spoc_name, student_touch, student_name, cmisid,
            contact_number, contactable, retention_status, months_working,
            current_company, current_salary, current_designation, str(doj),
            reason_leaving, need_job, nps, str(verification_date), remarks
        ]
        sheet.append_row(data)
        st.success("✅ Data submitted!")

# ============================================
# ROUTING (UNCHANGED)
# ============================================
if not st.session_state.logged_in:
    if choice == "Login":
        show_login()
    else:
        show_register()
else:
    show_main_form()

# ============================================
# FOOTER (UNCHANGED)
# ============================================
st.markdown("""
    <div class="footer">
        © 2025 Nibedan Foundation | Student Verification System
    </div>
""", unsafe_allow_html=True)