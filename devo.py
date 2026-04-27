import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date, datetime
import hashlib
import os
import time

# ============================================
# ⚙️ PAGE CONFIG & PERFORMANCE SETUP
# ============================================
st.set_page_config(
    page_title="Fast Student Verification v4.0",
    page_icon="⚡",
    layout="wide"
)

# ============================================
# 🌈 FAST UI STYLING
# ============================================
st.markdown("""
    <style>
        .main { background: #f4f7f6; }
        .stButton > button { 
            border-radius: 8px; font-weight: 600; height: 3em;
            transition: all 0.2s ease-in-out;
        }
        .stButton > button:hover { transform: scale(1.02); }
        .section-card {
            background: white; padding: 1.5rem; border-radius: 15px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 1rem;
        }
        .form-title { color: #1a73e8; font-weight: 700; font-size: 1.2rem; margin-bottom: 1rem; }
        .footer { text-align: center; color: #888; font-size: 0.8rem; margin-top: 3rem; }
    </style>
""", unsafe_allow_html=True)

# ============================================
# 🔐 SECURITY & CACHED CONNECTION
# ============================================
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

@st.cache_resource
def get_sheets_connection():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    else:
        creds = Credentials.from_service_account_file("service_account.json", scopes=scope)
    gc = gspread.authorize(creds)
    return {
        "master": gc.open("Test").sheet1,
        "auth": gc.open("Test_Spoc_PassWord").sheet1,
        "lookup": gc.open("Test2").sheet1
    }

sheets = get_sheets_connection()

@st.cache_data(ttl=600)
def fetch_all_lookup_data():
    return sheets["lookup"].get_all_records()

@st.cache_data(ttl=300)
def fetch_auth_data():
    return sheets["auth"].get_all_records()

# ============================================
# 📊 LOGIC MAPPING
# ============================================
RETENTION_MAP = {
    "Yes": ["Working in same job", "Working in different job", "Disconnected,Did'nt Share All Info.", "Not_Joined_Yet", "Confirmed Name - No Info.", "Not_working_at_all", "Left The Job", "Language Issue", "Not a student"],
    "No": ["Unable_to_track"],
    "--": ["--"]
}

REMARKS_MAP = {
    "Unable_to_track": ["Did not respond", "Network issue", "Not a student", "Language issue", "Switched off", "Incoming Not Available", "Wrong Number"],
    "Working in same job": ["--", "Highly Satisfied", "Promoted"],
    "Not_working_at_all": ["Personal issue", "Profile issue", "Employer info missing", "Not selected", "No interview", "No reason-call"],
    "Left The Job": ["Distance Issue", "Pursuing Higher Studies.", "Job Profile Did Not Match", "Family Issue", "Medical & Health Issue", "Salary Issue", "Heavy Workload", "Timing Issue", "Office Timing", "Night Shift", "Internship/Project Completed", "Company Closed", "Others...", "Terminated"],
    "--": ["--"]
}

# ============================================
# 🔑 SESSION STATES & UTILITIES
# ============================================
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "user" not in st.session_state: st.session_state.user = ""

def reset_form_fields(preserve_student=False):
    """Clears placement data. If preserve_student is True, keeps Name, CMIS, Phone."""
    if not preserve_student:
        st.session_state.form_vals = {"name": "", "cmis": "", "comp": "", "sal": "", "deg": "", "phone": ""}
    else:
        # Keep the student identity but clear the job details
        st.session_state.form_vals["comp"] = ""
        st.session_state.form_vals["sal"] = ""
        st.session_state.form_vals["deg"] = ""
        # DOJ is handled by the widget default

if "form_vals" not in st.session_state: 
    reset_form_fields(preserve_student=False)

# ============================================
# 🚪 AUTHENTICATION UI
# ============================================
if not st.session_state.logged_in:
    st.markdown("<br><br>", unsafe_allow_html=True)
    cols = st.columns([1, 2, 1])
    with cols[1]:
        tab_log, tab_reg = st.tabs(["🔐 Login", "🆕 Register"])
        with tab_log:
            u = st.text_input("SPOC Name")
            p = st.text_input("Password", type="password")
            if st.button("Access System", use_container_width=True):
                auth_recs = fetch_auth_data()
                match = next((r for r in auth_recs if str(r.get("spoc_name")) == u), None)
                if match and match.get("password") == hash_password(p):
                    st.session_state.logged_in = True
                    st.session_state.user = u
                    st.rerun()
                else: st.error("Invalid Username/Password")
        with tab_reg:
            nu = st.text_input("New SPOC Name")
            np = st.text_input("New Password", type="password")
            if st.button("Create Account", use_container_width=True):
                if nu and np:
                    sheets["auth"].append_row([nu, hash_password(np), datetime.now().strftime("%Y-%m-%d")])
                    st.cache_data.clear() 
                    st.success("Registered! Go to Login tab.")
                else: st.warning("Fill all fields")

# ============================================
# 🏠 MAIN DASHBOARD
# ============================================
else:
    st.sidebar.subheader(f"👤 {st.session_state.user}")
    if st.sidebar.button("🔴 Logout", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()

    # SECTION 1: SEARCH
    st.markdown('<div class="section-card"><div class="form-title">🔍 Quick Student Lookup</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
    search_q = c1.text_input("Enter Contact Number", placeholder="E.g. 9876543210")
    
    if c2.button("⚡ Fetch Details", use_container_width=True):
        data = fetch_all_lookup_data()
        match = next((r for r in data if str(r.get("Contact Number")) == search_q or str(r.get("Contact Number")).endswith(search_q[-10:])), None)
        if match:
            st.session_state.form_vals = {
                "name": str(match.get("Student Name", "")),
                "cmis": str(match.get("CMIS ID", "")),
                "comp": str(match.get("Company Name", "")),
                "sal": str(match.get("salary", "")),
                "deg": str(match.get("Deg", "")),
                "phone": search_q
            }
            st.toast("Record Found!", icon="✅")
            st.rerun()
        else: st.toast("Not Found", icon="⚠️")

    if c3.button("🧹 Clear Placement Data", use_container_width=True):
        # Keeps Student Info, removes Job Info
        reset_form_fields(preserve_student=True)
        st.rerun()

    if c4.button("🔄 Refresh DB", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # SECTION 2: THE FORM
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="form-title">📝 Student Verification Form</div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        f_touch = st.selectbox("Touch Method", ["Tikona_Call", "SPOC_call"])
        f_name = st.text_input("Name", value=st.session_state.form_vals["name"])
        f_cmis = st.text_input("CMIS ID", value=st.session_state.form_vals["cmis"])
        f_phone = st.text_input("Contact", value=st.session_state.form_vals["phone"])
        f_contactable = st.selectbox("Contactable", ["Yes", "No"])

    with col2:
        ret_opts = RETENTION_MAP.get(f_contactable, ["--"])
        f_retention = st.selectbox("Retention Status", ret_opts)
        
        # ⚡ SELECTIVE CLEARING BASED ON STATUS
        # If student is NOT working or untraceable, clear the job fields automatically
        if f_retention in ["Working in different job", "Not_working_at_all", "Unable_to_track", "Left The Job"]:
             disp_comp = ""
             disp_sal = ""
             disp_deg = ""
        else:
             disp_comp = st.session_state.form_vals["comp"]
             disp_sal = st.session_state.form_vals["sal"]
             disp_deg = st.session_state.form_vals["deg"]

        f_months = st.number_input("Months Working", min_value=0)
        f_comp = st.text_input("Company", value=disp_comp)
        f_sal = st.text_input("Salary", value=disp_sal)
        f_deg = st.text_input("DEG", value=disp_deg)

    with col3:
        rem_opts = REMARKS_MAP.get(f_retention, ["--"])
        f_remarks = st.selectbox("Remarks", rem_opts)
        
        # If DOJ needs to be cleared (reset to today) on certain statuses:
        default_doj = date.today()
        f_doj = st.date_input("DOJ", value=default_doj)
        
        f_reason = st.text_input("Remarks_Own", value="")
        f_nps = st.selectbox("NPS Score", ["--"] + list(range(11)))
        f_vdate = st.date_input("Verification Date", value=date.today())

    st.markdown('</div>', unsafe_allow_html=True)

    # SUBMIT
    if st.button("🚀 SUBMIT VERIFICATION", use_container_width=True):
        if f_name and f_cmis:
            with st.spinner("Saving..."):
                try:
                    payload = [
                        st.session_state.user, f_touch, f_name, f_cmis, f_phone,
                        f_contactable, f_retention, f_months, f_comp, f_sal,
                        f_deg, str(f_doj), f_reason, "No", str(f_nps), str(f_vdate), f_remarks
                    ]
                    sheets["master"].append_row(payload)
                    st.success("Record Saved!")
                    # Full clear after successful submission to prepare for next student
                    reset_form_fields(preserve_student=False)
                    time.sleep(1)
                    st.rerun()
                except Exception as e: st.error(f"Error: {e}")
        else: st.warning("Name and CMIS ID are mandatory!")

st.markdown('<div class="footer">© 2026 Anudip Foundation | High Speed Verification System v4.0</div>', unsafe_allow_html=True)