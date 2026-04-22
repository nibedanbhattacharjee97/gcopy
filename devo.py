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
# 🌈 PAGE STYLE
# ============================================
st.markdown("""
    <style>
        .main { background: linear-gradient(135deg, #00aaff, #00ffaa); }
        .login-card { background-color: white; border-radius: 16px; padding: 2rem; box-shadow: 0px 4px 12px rgba(0,0,0,0.2); width: 420px; margin: auto; text-align: center; }
        .login-title { color: #007bff; font-size: 1.5rem; font-weight: 700; margin-bottom: 1rem; }
        .footer { text-align: center; font-size: 0.9rem; color: #666; margin-top: 2rem; }
        .stButton > button { background-color: #007bff; color: white; font-weight: bold; border-radius: 8px; width: 100%; border: none; }
        .section-card { background-color: rgba(255,255,255,0.95); padding: 1.5rem; border-radius: 12px; margin-bottom: 1rem; box-shadow: 0px 4px 15px rgba(0,0,0,0.1); }
        .form-title { font-size: 1.2rem; font-weight: 700; color: #0056b3; margin-bottom: 1rem; border-bottom: 2px solid #eef; padding-bottom: 5px; }
        .success-box { background: #eafaf1; border-left: 5px solid #28a745; padding: 10px; border-radius: 8px; margin-bottom: 10px; }
        .warning-box { background: #fff8e5; border-left: 5px solid #ff9800; padding: 10px; border-radius: 8px; margin-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

# ============================================
# 🗺️ LOGIC MAPPING (FROM IMAGE)
# ============================================
LOGIC_MAP = {
    "Yes": {
        "Yes -(Retention Status)": ["Working in same job", "Working in different job", "Confirmed Name But Didn't Share Information", "Left_The_Job", "Will joined after some days", "Not a student of Anudip", "Language issue"],
        "Not_working_at_all": ["Did_not_joined_job_due_to_personal_issue", "Did_not_joined_job_due_to_profile_issue", "Did not get any information from the employer", "Did not get selected", "Did Not Attend Any Interview"],
        "Unable_to_track": ["Did not respond to our call", "Network issue", "Switched off", "Incoming Call Is Not Available", "Wrong Number"],
        "Left_The_Job": ["Distance Issue", "Pursuing Higher Studies.", "Job Profile Did Not Match", "Family Issue", "Medical & Health Issue", "Don't Want To Share", "Salary Issue", "Heavy Workload", "Office Timing", "Internship/Project Completed", "Company Closed", "Others..."]
    },
    "No": {
        "No -(Retention Status)": ["Unable_to_track"],
        "Not_working_at_all": ["Not_working_at_all"]
    }
}

# ============================================
# 🔐 UTILITIES
# ============================================
def hash_password(password): return hashlib.sha256(str.encode(password)).hexdigest()
def verify_password(password, hashed): return hash_password(password) == hashed
def safe_str(val): return str(val).strip() if val else ""

def normalize_contact(number):
    v = safe_str(number).replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    return v[3:] if v.startswith("+91") else v

def parse_doj(raw):
    if not raw: return date.today()
    for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"]:
        try: return datetime.strptime(safe_str(raw), fmt).date()
        except: pass
    return date.today()

# ============================================
# 📡 GOOGLE SHEETS AUTH
# ============================================
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
try:
    if "gcp_service_account" in st.secrets:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    else:
        creds = Credentials.from_service_account_file("service_account.json", scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open("Test").sheet1
    login_sheet = client.open("Test_Spoc_PassWord").sheet1
    test2_sheet = client.open("Test2").sheet1
except Exception as e:
    st.error("Google Sheets Connection Failed"); st.stop()

# ============================================
# 🔑 SESSION MANAGEMENT
# ============================================
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "spoc_name" not in st.session_state: st.session_state.spoc_name = ""

# Form state management
for key, val in {"s_name": "", "s_cmis": "", "s_phone": "", "s_comp": "", "s_sal": "", "s_deg": "", "s_doj": date.today(), "note": ""}.items():
    if key not in st.session_state: st.session_state[key] = val

# ============================================
# 🚪 AUTH UI (LOGIN/REGISTER)
# ============================================
if not st.session_state.logged_in:
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        st.markdown('<div class="login-card"><div class="login-title">🔐 SPOC Login</div>', unsafe_allow_html=True)
        u = st.text_input("SPOC Name", key="login_u")
        p = st.text_input("Password", type="password", key="login_p")
        if st.button("Login"):
            recs = login_sheet.get_all_records()
            user_data = next((r for r in recs if safe_str(r.get("spoc_name")) == u), None)
            if user_data and verify_password(p, safe_str(user_data.get("password"))):
                st.session_state.logged_in = True
                st.session_state.spoc_name = u
                st.rerun()
            else: st.error("Invalid Credentials")
        st.markdown('</div>', unsafe_allow_html=True)

    with tab2:
        st.markdown('<div class="login-card"><div class="login-title">🆕 Register</div>', unsafe_allow_html=True)
        nu = st.text_input("New SPOC Name")
        np = st.text_input("New Password", type="password")
        if st.button("Create Account"):
            if nu and np:
                login_sheet.append_row([nu, hash_password(np), datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                st.success("Registration Successful! Please Login.")
        st.markdown('</div>', unsafe_allow_html=True)

# ============================================
# 📝 MAIN FORM UI (LOGGED IN)
# ============================================
else:
    # Sidebar Logout
    st.sidebar.title("Navigation")
    st.sidebar.success(f"User: {st.session_state.spoc_name}")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    # --- Section 1: Auto-Fetch ---
    st.markdown('<div class="section-card"><div class="form-title">🔎 Data Retrieval</div>', unsafe_allow_html=True)
    c_fetch1, c_fetch2 = st.columns([4, 1])
    with c_fetch1:
        search_phone = st.text_input("Search Contact Number", value=st.session_state.s_phone)
    with c_fetch2:
        st.write("<br>", unsafe_allow_html=True)
        if st.button("Fetch Data"):
            try:
                data = test2_sheet.get_all_records()
                match = next((r for r in data if normalize_contact(r.get("Contact Number")) == normalize_contact(search_phone)), None)
                if match:
                    st.session_state.s_name = safe_str(match.get("Student Name", ""))
                    st.session_state.s_cmis = safe_str(match.get("CMIS ID", ""))
                    st.session_state.s_phone = search_phone
                    st.session_state.s_comp = safe_str(match.get("Company Name", ""))
                    st.session_state.s_sal = safe_str(match.get("salary", ""))
                    st.session_state.s_deg = safe_str(match.get("Deg", ""))
                    st.session_state.s_doj = parse_doj(match.get("DOJ", ""))
                    st.session_state.note = "✅ Found in Database"
                else: st.session_state.note = "⚠️ No records found"
                st.rerun()
            except: st.error("Fetch Failed")
    
    if st.session_state.note:
        st.info(st.session_state.note)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- Section 2: Entry Form ---
    with st.form("student_entry"):
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown('<div class="section-card"><div class="form-title">👤 Student Info</div>', unsafe_allow_html=True)
            method = st.selectbox("Touch Method", ["Call", "WhatsApp", "SMS", "Email"])
            name = st.text_input("Name", value=st.session_state.s_name)
            cmis = st.text_input("CMIS ID", value=st.session_state.s_cmis)
            phone = st.text_input("Mobile", value=st.session_state.s_phone)
            # LOGIC START: Contactable
            contactable = st.selectbox("Contactable", list(LOGIC_MAP.keys()))
            st.markdown('</div>', unsafe_allow_html=True)

        with col2:
            st.markdown('<div class="section-card"><div class="form-title">🏢 Career Details</div>', unsafe_allow_html=True)
            # LOGIC: Retention Status depends on Contactable
            ret_options = list(LOGIC_MAP[contactable].keys())
            ret_status = st.selectbox("Retention Status", ret_options)
            
            comp = st.text_input("Current Company", value=st.session_state.s_comp)
            sal = st.text_input("Salary", value=st.session_state.s_sal)
            deg = st.text_input("Designation", value=st.session_state.s_deg)
            doj = st.date_input("DOJ", value=st.session_state.s_doj)
            months = st.number_input("Months Worked", min_value=0, step=1)
            st.markdown('</div>', unsafe_allow_html=True)

        with col3:
            st.markdown('<div class="section-card"><div class="form-title">📝 Feedback</div>', unsafe_allow_html=True)
            # LOGIC: Reasons depends on Retention Status selected in Col 2
            reason_options = LOGIC_MAP[contactable][ret_status]
            final_reason = st.selectbox("Reason (From Logic Table)", reason_options)
            
            need_job = st.selectbox("Needs Job?", ["No", "Yes"])
            nps = st.slider("NPS Score", 0, 10, 8)
            v_date = st.date_input("Verification Date", value=date.today())
            remarks = st.text_area("Remarks")
            st.markdown('</div>', unsafe_allow_html=True)

        if st.form_submit_button("Submit Data to Sheet"):
            final_row = [
                st.session_state.spoc_name, method, name, cmis, phone, contactable,
                ret_status, comp, sal, deg, str(doj), months, final_reason,
                need_job, nps, str(v_date), remarks
            ]
            sheet.append_row(final_row)
            st.success("✅ Entry Recorded!")

st.markdown('<div class="footer">© 2026 Anudip Foundation | M&E Verification Portal</div>', unsafe_allow_html=True)