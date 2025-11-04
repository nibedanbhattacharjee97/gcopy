import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date, datetime
import hashlib

# ============================================
# ⚙️ PAGE CONFIG
# ============================================
st.set_page_config(page_title="Student Verification Entry Form", page_icon="✅", layout="wide")

# ============================================
# 🌈 PAGE STYLE
# ============================================
st.markdown("""
    <style>
        body { background: linear-gradient(135deg, #00aaff, #00ffaa); }
        .main { background: transparent; }
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
# 🔐 PASSWORD UTILITIES
# ============================================
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def verify_password(password, hashed):
    return hash_password(password) == hashed

# ============================================
# 🔐 GOOGLE AUTHENTICATION
# ============================================
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
credentials = Credentials.from_service_account_file("service_account.json", scopes=scope)
client = gspread.authorize(credentials)

# ============================================
# 📄 GOOGLE SHEETS CONNECTIONS
# ============================================
SHEET_NAME = "Test"
LOGIN_SHEET_NAME = "Test_Spoc_PassWord"

sheet = client.open(SHEET_NAME).sheet1
login_sheet = client.open(LOGIN_SHEET_NAME).sheet1

# ============================================
# 🔑 SESSION STATE INIT
# ============================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "spoc_name" not in st.session_state:
    st.session_state.spoc_name = ""

# ============================================
# 🧭 SIDEBAR MENU
# ============================================
menu = ["Login", "Register"]
choice = st.sidebar.selectbox("Select Option", menu)

# ============================================
# 🚪 LOGOUT
# ============================================
if st.session_state.logged_in:
    st.sidebar.markdown("---")
    with st.sidebar:
        st.markdown('<div class="logout-button">', unsafe_allow_html=True)
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.spoc_name = ""
            st.success("👋 Logged out successfully.")
            st.rerun()  # 🔁 Immediately reloads page after logout
        st.markdown("</div>", unsafe_allow_html=True)

# ============================================
# 🧾 REGISTER PAGE
# ============================================
def show_register():
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">🆕 SPOC Registration</div>', unsafe_allow_html=True)
    st.markdown("Create your SPOC login credentials below 👇")

    new_user = st.text_input("Enter SPOC Name")
    new_password = st.text_input("Enter Password", type="password")

    if st.button("Register"):
        if new_user and new_password:
            all_records = login_sheet.get_all_records()
            existing_users = [r["spoc_name"] for r in all_records if "spoc_name" in r]

            if new_user in existing_users:
                st.error("❌ SPOC name already exists. Please choose another.")
            else:
                hashed_pass = hash_password(new_password)
                created_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                login_sheet.append_row([new_user, hashed_pass, created_date])
                st.success("✅ Registration successful! Please login now.")
        else:
            st.warning("⚠️ Please enter both SPOC name and password.")
    st.markdown("</div>", unsafe_allow_html=True)

# ============================================
# 🔐 LOGIN PAGE
# ============================================
def show_login():

    st.markdown('<div class="login-title">SPOC Login Portal</div>', unsafe_allow_html=True)

    username = st.text_input("Enter SPOC Name")
    password = st.text_input("Enter Password", type="password")

    if st.button("Login"):
        try:
            all_records = login_sheet.get_all_records()
            user_data = next((r for r in all_records if r["spoc_name"] == username), None)

            if user_data and verify_password(password, user_data["password"]):
                st.session_state.logged_in = True
                st.session_state.spoc_name = username
                st.success(f"✅ Welcome {username}!")
                st.rerun()  # 🔁 Immediately reload page to show main form
            else:
                st.error("❌ Invalid credentials. Please try again.")
        except Exception as e:
            st.error(f"⚠️ Error reading login sheet: {e}")
    st.markdown("</div>", unsafe_allow_html=True)

# ============================================
# 📋 MAIN FORM (AFTER LOGIN)
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
            months_working = st.number_input("How many months working", min_value=0, step=1)
            current_company = st.text_input("Current Company Name")
            current_salary = st.text_input("Current Salary")
            current_designation = st.text_input("Current Designation")
            doj = st.date_input("DOJ", value=date.today())

        with col3:
            reason_leaving = st.text_area("Reason Behind leaving the Job")
            need_job = st.selectbox("Need any further job", ["Yes", "No"])
            nps = st.slider("Net Promoting Score (0-10)", 0, 10, 5)
            verification_date = st.date_input("Verification Date", value=date.today())
            remarks = st.text_area("Remarks")
            remarks_1 = st.text_area("Remarks_1")
            remarks_3 = st.text_area("Remarks_3")

        submitted = st.form_submit_button("Submit Data ✅")

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
                remarks,
                remarks_1,
                remarks_3
            ]
            sheet.append_row(data)
            st.success("✅ Data successfully submitted to Google Sheet!")
        except Exception as e:
            st.error(f"❌ Error submitting data: {e}")

# ============================================
# 🌐 ROUTER-LIKE FLOW
# ============================================
if not st.session_state.logged_in:
    if choice == "Login":
        show_login()
    elif choice == "Register":
        show_register()
else:
    show_main_form()

# ============================================
# 👣 FOOTER
# ============================================
st.markdown("""
    <div class="footer">
        © 2025 Nibedan Foundation | Student Verification System
    </div>
""", unsafe_allow_html=True)
