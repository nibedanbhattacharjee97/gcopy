import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date, datetime
import hashlib
import pandas as pd

# ============================================
# ⚙️ PAGE CONFIG
# ============================================
st.set_page_config(page_title="Student Verification Entry Form", page_icon="✅", layout="wide")

# ============================================
# 🌈 PAGE STYLE
# ============================================
st.markdown("""
    <style>
        .main { background-color: #f0f2f6; }
        .login-card {
            background-color: white;
            border-radius: 16px;
            padding: 2rem;
            box-shadow: 0px 4px 12px rgba(0,0,0,0.1);
            max-width: 420px;
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
            width: 100%;
        }
    </style>
""", unsafe_allow_html=True)

# ============================================
# 🔐 SPEED OPTIMIZED CONNECTION (CACHED)
# ============================================
@st.cache_resource
def get_gspread_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    # Ensure your service_account.json is in the same directory or secret management
    credentials = Credentials.from_service_account_file("service_account.json", scopes=scope)
    return gspread.authorize(credentials)

# Initialize Sheets globally
try:
    client = get_gspread_client()
    SHEET_NAME = "Test"
    LOGIN_SHEET_NAME = "Test_Spoc_PassWord"
    TEST2_SHEET_NAME = "Test2"
    
    main_sheet = client.open(SHEET_NAME).sheet1
    login_sheet = client.open(LOGIN_SHEET_NAME).sheet1
    test2_sheet = client.open(TEST2_SHEET_NAME).sheet1
except Exception as e:
    st.error(f"Failed to connect to Google Sheets: {e}")
    st.stop() # Stop execution if we can't connect

@st.cache_data(ttl=600)
def get_login_records():
    return login_sheet.get_all_records()

@st.cache_data(ttl=300)
def get_test2_data():
    return test2_sheet.get_all_records()

# ============================================
# 🔐 UTILITIES & AUTH
# ============================================
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def verify_password(password, hashed):
    return hash_password(password) == hashed

# ============================================
# 🔑 SESSION STATE
# ============================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "spoc_name" not in st.session_state:
    st.session_state.spoc_name = ""

# ============================================
# 🧾 REGISTRATION & LOGIN FUNCTIONS
# ============================================
def show_register():
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">🆕 SPOC Registration</div>', unsafe_allow_html=True)
    new_user = st.text_input("Enter SPOC Name", key="reg_user")
    new_password = st.text_input("Enter Password", type="password", key="reg_pass")
    if st.button("Register"):
        if new_user and new_password:
            all_records = get_login_records()
            if any(r.get("spoc_name") == new_user for r in all_records):
                st.error("❌ SPOC name already exists.")
            else:
                login_sheet.append_row([new_user, hash_password(new_password), datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                st.cache_data.clear()
                st.success("✅ Registered! Please login.")
    st.markdown('</div>', unsafe_allow_html=True)

def show_login():
    st.markdown('<div class="login-card">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">SPOC Login Portal</div>', unsafe_allow_html=True)
    username = st.text_input("Enter SPOC Name", key="log_user")
    password = st.text_input("Enter Password", type="password", key="log_pass")
    if st.button("Login"):
        records = get_login_records()
        user_data = next((r for r in records if r["spoc_name"] == username), None)
        if user_data and verify_password(password, user_data["password"]):
            st.session_state.logged_in = True
            st.session_state.spoc_name = username
            st.rerun()
        else:
            st.error("❌ Invalid credentials.")
    st.markdown('</div>', unsafe_allow_html=True)

# ============================================
# 📋 MAIN FORM (WITH LOOKUP LOGIC)
# ============================================
def show_main_form():
    st.title("📋 Student Verification Entry Form")
    
    # --- LEVEL 1 & 2: SELECTION LOGIC ---
    col_a, col_b, col_c = st.columns(3)
    
    with col_a:
        contactable = st.selectbox("1. Contactable", ["Yes", "No"])
    
    with col_b:
        if contactable == "No":
            retention_options = ["Unable_to_track"]
        else:
            retention_options = [
                "Working in same job", "Not_working_at_all", 
                "Working in different job", "Confirmed name and didn't share information",
                "Rejected", "on hold", "Will join after few days", "Left the job"
            ]
        retention_status = st.selectbox("2. Retention Status", retention_options)

    with col_c:
        remarks_options = ["Other"]
        if retention_status == "Unable_to_track":
            remarks_options = ["Did not respond", "Network issue", "Switched off", "Wrong Number"]
        elif retention_status == "Left the job":
            remarks_options = ["Salary Issue", "Distance Issue", "Family Issue", "Higher Studies"]
        
        selected_remark = st.selectbox("3. Specific Reason (Remarks)", remarks_options)

    is_disabled = (contactable == "No")

    # --- LOOKUP LOGIC FOR "WORKING IN SAME JOB" ---
    lookup_data = {}
    search_contact = st.text_input("🔍 Search Contact Number to Autofill", help="Enter number and press Enter")

    if retention_status == "Working in same job" and search_contact:
        data_test2 = get_test2_data()
        match = next((item for item in data_test2 if str(item.get("Contact Number")) == search_contact), None)
        
        if match:
            lookup_data = {
                "cmis": match.get("CMIS ID", ""),
                "company": match.get("Company Name", ""),
                "deg": match.get("Deg", ""),
                "salary": match.get("salary", ""),
                "doj": match.get("DOJ", "")
            }
            st.success("✅ Student details found and loaded!")
        else:
            st.warning("⚠️ No record found for this number in Test2.")

    # --- MAIN DATA FORM ---
    with st.form("entry_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)

        with col1:
            student_touch = st.selectbox("Students Touch Method", ["Call", "G-Meet", "SPOC_Mobile"])
            student_name = st.text_input("Student Name")
            cmisid = st.text_input("CMIS ID", value=lookup_data.get("cmis", ""))
            contact_number = st.text_input("Contact Number", value=search_contact)

        with col2:
            months_working = st.number_input("Months Working", min_value=0, step=1, disabled=is_disabled)
            current_company = st.text_input("Current Company", value=lookup_data.get("company", ""), disabled=is_disabled)
            current_salary = st.text_input("Current Salary", value=lookup_data.get("salary", ""), disabled=is_disabled)
            current_designation = st.text_input("Current Designation", value=lookup_data.get("deg", ""), disabled=is_disabled)

        with col3:
            default_doj = date.today()
            if lookup_data.get("doj"):
                try:
                    # Adjust format if your sheet uses different date format
                    default_doj = datetime.strptime(str(lookup_data.get("doj")), "%Y-%m-%d").date()
                except: pass
                
            doj = st.date_input("DOJ", value=default_doj, disabled=is_disabled)
            nps = st.slider("NPS Score", min_value=0, max_value=10, value=5, disabled=is_disabled)
            need_job = st.selectbox("Need Job Assistance?", ["Yes", "No"], disabled=is_disabled)
            verification_date = st.date_input("Verification Date", value=date.today())
            
        additional_notes = st.text_area("Additional Remarks/Notes")

        submitted = st.form_submit_button("Submit Data ✅")

        if submitted:
            try:
                final_data = [
                    st.session_state.spoc_name, student_touch, student_name, cmisid, 
                    contact_number, contactable, retention_status,
                    months_working if not is_disabled else 0,
                    current_company if not is_disabled else "N/A",
                    current_salary if not is_disabled else "N/A",
                    current_designation if not is_disabled else "N/A",
                    str(doj) if not is_disabled else "N/A",
                    selected_remark,
                    need_job if not is_disabled else "N/A",
                    nps if not is_disabled else 0,
                    str(verification_date), additional_notes
                ]
                main_sheet.append_row(final_data)
                st.success(f"✅ Data for {student_name} saved successfully!")
                st.cache_data.clear()
            except Exception as e:
                st.error(f"❌ Error: {e}")

# ============================================
# 🚪 SIDEBAR & NAVIGATION
# ============================================
if not st.session_state.logged_in:
    choice = st.sidebar.selectbox("Select Option", ["Login", "Register"])
    if choice == "Login": 
        show_login()
    else: 
        show_register()
else:
    st.sidebar.title(f"Welcome, {st.session_state.spoc_name}")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.spoc_name = ""
        st.rerun()
    show_main_form()

st.markdown('<div class="footer">© 2025 Nibedan Foundation | Student Verification System</div>', unsafe_allow_html=True)