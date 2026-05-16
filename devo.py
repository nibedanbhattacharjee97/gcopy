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
        .queue-box { background: #e8f0fe; padding: 0.75rem; border-radius: 8px; border-left: 5px solid #1a73e8; font-weight: 600; margin-bottom: 1rem; }
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
        "lookup": gc.open("Test2").sheet1,
        "allocation": gc.open("Test3").sheet1 
    }

sheets = get_sheets_connection()

@st.cache_data(ttl=600)
def fetch_all_lookup_data():
    return sheets["lookup"].get_all_records()

@st.cache_data(ttl=300)
def fetch_auth_data():
    return sheets["auth"].get_all_records()

@st.cache_data(ttl=300)
def fetch_allocation_data():
    return sheets["allocation"].get_all_records()

# ============================================
# 📊 LOGIC MAPPING
# ============================================
RETENTION_MAP = {
    "Yes": ["Working in same job", "Working in different job", "Disconnected,Did'nt Share All Info.", "Not_Joined_Yet", "Confirmed Name - No Info.", "Not_working_at_all", "Left The Job", "Language Issue", "Not a student","Hold","Rejected"],
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
if "allocated_numbers" not in st.session_state: st.session_state.allocated_numbers = []
if "queue_index" not in st.session_state: st.session_state.queue_index = 0

if "form_initials" not in st.session_state:
    st.session_state.form_initials = {
        "name": "", "cmis": "", "comp": "", "sal": "", "deg": "", "phone": "", "doj": date.today()
    }

def load_student_by_phone(phone_target):
    """Searches lookup data from Test2 and stores them cleanly without widget key conflicts"""
    data = fetch_all_lookup_data()
    target_clean = str(phone_target).strip()
    if not target_clean:
        return False
        
    match = None
    for r in data:
        sheet_phone = str(r.get("Contact Number", "")).strip()
        if target_clean in sheet_phone or sheet_phone.endswith(target_clean[-10:]):
            match = r
            break
            
    if match:
        raw_doj = match.get("DOJ", "")
        try:
            parsed_doj = datetime.strptime(str(raw_doj).strip(), "%Y-%m-%d").date() if raw_doj else date.today()
        except:
            parsed_doj = date.today()

        st.session_state.form_initials = {
            "name": str(match.get("student_name", "")).strip(),
            "cmis": str(match.get("CMIS ID", "")).strip(),
            "comp": str(match.get("Company Name", "")).strip(),
            "sal": str(match.get("salary", "")).strip(),
            "deg": str(match.get("Deg", "")).strip(),
            "phone": str(match.get("Contact Number", "")).strip(),
            "doj": parsed_doj
        }
        return True
    else:
        st.session_state.form_initials = {
            "name": "", "cmis": "", "comp": "", "sal": "", "deg": "", "phone": target_clean, "doj": date.today()
        }
        return False

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
                match = next((r for r in auth_recs if str(r.get("spoc_name")).strip() == u.strip()), None)
                if match and match.get("password") == hash_password(p):
                    st.session_state.logged_in = True
                    st.session_state.user = u.strip()
                    
                    alloc_data = fetch_allocation_data()
                    spoc_numbers = [
                        str(r.get("phone_number")).strip() for r in alloc_data 
                        if str(r.get("SPOC_Name")).strip().lower() == u.strip().lower() and r.get("phone_number")
                    ]
                    st.session_state.allocated_numbers = spoc_numbers
                    st.session_state.queue_index = 0
                    
                    if spoc_numbers:
                        load_student_by_phone(spoc_numbers[0])
                        
                    st.rerun()
                else: st.error("Invalid Username/Password")
        with tab_reg:
            nu = st.text_input("New SPOC Name")
            np = st.text_input("New Password", type="password")
            if st.button("Create Account", use_container_width=True):
                if nu and np:
                    sheets["auth"].append_row([nu.strip(), hash_password(np), datetime.now().strftime("%Y-%m-%d")])
                    st.cache_data.clear() 
                    st.success("Registered! Go to Login tab.")
                else: st.warning("Fill all fields")

# ============================================
# 🏠 MAIN DASHBOARD
# ============================================
else:
    st.sidebar.subheader(f"👤 {st.session_state.user}")
    
    total_assigned = len(st.session_state.allocated_numbers)
    current_idx = st.session_state.queue_index
    
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"### 📋 Allocation Status")
    st.sidebar.metric(label="Total Assigned Numbers", value=total_assigned)
    if total_assigned > 0:
        progress_val = min(current_idx / total_assigned, 1.0)
        st.sidebar.progress(progress_val)
        st.sidebar.write(f"Processing item **{min(current_idx + 1, total_assigned)}** of **{total_assigned}**")
    else:
        st.sidebar.warning("No numbers allocated to you in Test3.")

    if st.sidebar.button("🔴 Logout", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.allocated_numbers = []
        st.session_state.queue_index = 0
        st.rerun()

    # SECTION 1: QUEUE CONTROLS
    st.markdown('<div class="section-card"><div class="form-title">🔍 Allocated Student Queue Navigator</div>', unsafe_allow_html=True)
    
    if total_assigned > 0 and current_idx < total_assigned:
        current_allocated_phone = st.session_state.allocated_numbers[current_idx]
        st.markdown(f'<div class="queue-box">🎯 Active Queue Target: {current_allocated_phone} ({current_idx + 1}/{total_assigned})</div>', unsafe_allow_html=True)
    elif total_assigned > 0 and current_idx >= total_assigned:
        st.markdown('<div class="queue-box" style="background: #e6f4ea; border-left-color: #34a853;">✅ Verification Queue Fully Completed!</div>', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
    search_q = c1.text_input("Jump directly to specific number (Optional)", placeholder="Leave blank to use sequential automation queue")
    
    if c2.button("⚡ Fetch Details", use_container_width=True):
        query = search_q.strip()
        if query:
            match_found = False
            for idx, num in enumerate(st.session_state.allocated_numbers):
                if query in num or num.endswith(query[-10:]):
                    st.session_state.queue_index = idx
                    load_student_by_phone(num)
                    match_found = True
                    break
            
            if match_found:
                st.toast("Allocated Record Loaded!", icon="✅")
                st.rerun()
            else:
                st.error("Access Denied: This number is not allocated to your profile.")
        else:
            # ⚡ NO COPY PASTE REQUIRED HERE anymore! 
            # If search bar is blank, hitting Fetch Details automatically grabs the active queue number
            if total_assigned > 0 and current_idx < total_assigned:
                load_student_by_phone(st.session_state.allocated_numbers[current_idx])
                st.toast("Current Allocated Target Details Fetched!", icon="⚡")
                st.rerun()

    if c3.button("🧹 Clear Placement Data", use_container_width=True):
        st.session_state.form_initials["comp"] = ""
        st.session_state.form_initials["sal"] = ""
        st.session_state.form_initials["deg"] = ""
        st.session_state.form_initials["doj"] = date.today()
        st.rerun()

    if c4.button("🔄 Refresh DB", use_container_width=True):
        st.cache_data.clear()
        alloc_data = fetch_allocation_data()
        st.session_state.allocated_numbers = [
            str(r.get("phone_number")).strip() for r in alloc_data 
            if str(r.get("SPOC_Name")).strip().lower() == st.session_state.user.strip().lower() and r.get("phone_number")
        ]
        if st.session_state.allocated_numbers and st.session_state.queue_index < len(st.session_state.allocated_numbers):
            load_student_by_phone(st.session_state.allocated_numbers[st.session_state.queue_index])
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # SECTION 2: THE FORM
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="form-title">📝 Student Verification Form</div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        f_touch = st.selectbox("Touch Method", ["Tikona_Call", "SPOC_call"])
        f_name = st.text_input("Name", value=st.session_state.form_initials["name"])
        f_cmis = st.text_input("CMIS ID", value=st.session_state.form_initials["cmis"])
        f_phone = st.text_input("Contact", value=st.session_state.form_initials["phone"])
        f_contactable = st.selectbox("Contactable", ["Yes", "No"])

    with col2:
        ret_opts = RETENTION_MAP.get(f_contactable, ["--"])
        f_retention = st.selectbox("Retention Status", ret_opts)
        
        if f_retention in ["Working in different job", "Not_working_at_all", "Unable_to_track", "Left The Job"]:
             disp_comp = ""
             disp_sal = ""
             disp_deg = ""
             disp_doj = date.today()
        else:
             disp_comp = st.session_state.form_initials["comp"]
             disp_sal = st.session_state.form_initials["sal"]
             disp_deg = st.session_state.form_initials["deg"]
             disp_doj = st.session_state.form_initials["doj"]

        f_months = st.number_input("Months Working", min_value=0)
        f_comp = st.text_input("Company", value=disp_comp)
        f_sal = st.text_input("Salary", value=disp_sal)
        f_deg = st.text_input("DEG", value=disp_deg)

    with col3:
        rem_opts = REMARKS_MAP.get(f_retention, ["--"])
        f_remarks = st.selectbox("Remarks", rem_opts)
        f_doj = st.date_input("DOJ", value=disp_doj)
        f_reason = st.text_input("Remarks_Own", value="")
        f_nps = st.selectbox("NPS Score", ["--"] + list(range(11)))
        f_vdate = st.date_input("Verification Date", value=date.today())

    st.markdown('</div>', unsafe_allow_html=True)

    # SUBMIT
    if st.button("🚀 SUBMIT VERIFICATION", use_container_width=True):
        if f_name and f_cmis:
            with st.spinner("Saving current record and shifting queue..."):
                try:
                    payload = [
                        st.session_state.user, f_touch, f_name, f_cmis, f_phone,
                        f_contactable, f_retention, f_months, f_comp, f_sal,
                        f_deg, str(f_doj), f_reason, "No", str(f_nps), str(f_vdate), f_remarks
                    ]
                    sheets["master"].append_row(payload)
                    st.success("Record Saved!")
                    
                    # Core automation: move index forward immediately
                    st.session_state.queue_index += 1
                    
                    if st.session_state.queue_index < len(st.session_state.allocated_numbers):
                        next_phone = st.session_state.allocated_numbers[st.session_state.queue_index]
                        # Dynamically fetch Test2 details for the next entry down without intermediate steps
                        load_student_by_phone(next_phone)
                    else:
                        st.session_state.form_initials = {
                            "name": "", "cmis": "", "comp": "", "sal": "", "deg": "", "phone": "", "doj": date.today()
                        }
                        st.balloons()
                    
                    time.sleep(0.5)
                    st.rerun()
                except Exception as e: st.error(f"Error handling save operations: {e}")
        else: st.warning("Name and CMIS ID are mandatory fields!")

st.markdown('<div class="footer">© 2026 Anudip Foundation | High Speed Verification System v4.0</div>', unsafe_allow_html=True)