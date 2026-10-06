import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date, datetime
import hashlib
import os
import re
import time

# ==============================================================================
# ⚙️ PAGE CONFIG & ULTRA-FAST PERFORMANCE SETUP
# ==============================================================================
st.set_page_config(
    page_title="High Speed Verification System v4.0",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================================================================
# 🌈 ENHANCED HIGH-SPEED TELECALLING UI STYLING
# ==============================================================================
st.markdown("""
    <style>
        .main { background: #f7f9fa; }
        .stButton > button { 
            border-radius: 8px; font-weight: 700; height: 3.1em;
            transition: all 0.15s ease-in-out;
        }
        .stButton > button:hover { transform: translateY(-1px); box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
        .section-card {
            background: #ffffff; padding: 1.4rem; border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06); margin-bottom: 1.2rem;
            border: 1px solid #e2e8f0;
        }
        .form-title {
            color: #0f4c81; font-weight: 800; font-size: 1.25rem;
            margin-bottom: 0.8rem; display: flex; align-items: center; gap: 8px;
        }
        .footer { text-align: center; color: #718096; font-size: 0.85rem; margin-top: 3rem; padding: 1rem 0; }
        .queue-box {
            background: linear-gradient(135deg, #e8f0fe 0%, #f0f7ff 100%);
            padding: 0.85rem 1.2rem; border-radius: 8px;
            border-left: 6px solid #1a73e8; font-weight: 700;
            color: #1a365d; margin-bottom: 1rem; font-size: 1.05rem;
        }
        .routing-badge {
            display: inline-block; padding: 0.35rem 0.75rem; border-radius: 6px;
            font-size: 0.88rem; font-weight: 700; margin-bottom: 0.8rem;
        }
        .badge-self-employed { background: #e6fffa; color: #234e52; border: 1px solid #81e6d9; }
        .badge-job { background: #ebf8ff; color: #2a4365; border: 1px solid #bee3f8; }
        .badge-non-earning { background: #fffaf0; color: #744210; border: 1px solid #fbd38d; }
        .badge-inactive { background: #edf2f7; color: #4a5568; border: 1px solid #cbd5e0; }
        .profile-label { font-size: 0.82rem; color: #718096; text-transform: uppercase; font-weight: 600; }
        .profile-val { font-size: 1.02rem; font-weight: 700; color: #1a202c; }
        div[data-testid="stRadio"] > div {
            gap: 8px;
        }
        div[data-testid="stRadio"] label {
            background: #f8fafc; border: 1px solid #e2e8f0; padding: 8px 14px;
            border-radius: 8px; width: 100%; cursor: pointer; transition: all 0.15s ease;
        }
        div[data-testid="stRadio"] label:hover {
            background: #edf2f7; border-color: #cbd5e0;
        }
        div[data-testid="stCheckbox"] {
            background: #f8fafc; border: 1px solid #e2e8f0; padding: 6px 12px;
            border-radius: 8px; margin-bottom: 6px; transition: all 0.15s ease;
        }
        div[data-testid="stCheckbox"]:hover {
            background: #edf2f7; border-color: #cbd5e0;
        }
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 🔐 GOOGLE SHEETS CONNECTION & AUTHENTICATION UTILS
# ==============================================================================
def hash_password(password: str) -> str:
    return hashlib.sha256(str.encode(password)).hexdigest()

def clean_phone(phone_val) -> str:
    """Extracts only digits and returns the last 10 digits for clean lookup"""
    if not phone_val:
        return ""
    digits = re.sub(r"\D", "", str(phone_val).strip())
    return digits[-10:] if len(digits) >= 10 else digits

@st.cache_resource
def get_sheets_connection():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    else:
        # Check current folder or relative gcopy folder
        local_path = "service_account.json"
        script_dir_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "service_account.json")
        gcopy_path = os.path.join("gcopy", "service_account.json")
        
        if os.path.exists(local_path):
            creds = Credentials.from_service_account_file(local_path, scopes=scope)
        elif os.path.exists(script_dir_path):
            creds = Credentials.from_service_account_file(script_dir_path, scopes=scope)
        elif os.path.exists(gcopy_path):
            creds = Credentials.from_service_account_file(gcopy_path, scopes=scope)
        else:
            raise FileNotFoundError("service_account.json could not be found.")

    gc = gspread.authorize(creds)
    
    # Open required sheets
    master_ws = gc.open("Test").sheet1
    auth_ws = gc.open("Test_Spoc_PassWord").sheet1
    lookup_ws = gc.open("Test2").sheet1
    alloc_ws = gc.open("Test3").sheet1
    
    # Synchronize Test headers if needed
    EXPECTED_HEADERS = [
        'SPOC Name', 'Students Touch Method', 'STUDENT NAME', 'CMISID', 'CONTACT NUMBER',
        'Programme completed', 'Course or training name', 'Month and year of completion',
        'State of residence', 'District or city', 'Gender', 'Age group',
        'Highest educational qualification', 'Location type of training centre',
        'Contactable', 'Call Remarks',
        'Q1. What are you doing these days?',
        'Q2. How much do you earn every month from this work?',
        'Q2a. What kind of work are you doing?',
        'Q2a. Others (Please specify)',
        'Q2b. Where or how do you find your work or customers?',
        'Q2b. Others (Please specify)',
        'Q3. Did the Anudip training help you start your own work or earn on your own?',
        'Q4. What would help you most to earn better or start your own work?',
        'Verification Date', 'SPOC Remarks'
    ]
    try:
        current_headers = master_ws.row_values(1)
        if not current_headers or current_headers[:5] != EXPECTED_HEADERS[:5] or len(current_headers) < 20 or "Retention Status" in current_headers:
            master_ws.update(values=[EXPECTED_HEADERS], range_name=f"A1:Z1")
    except Exception:
        pass

    return {
        "master": master_ws,
        "auth": auth_ws,
        "lookup": lookup_ws,
        "allocation": alloc_ws
    }

sheets = get_sheets_connection()

@st.cache_data(ttl=600)
def fetch_all_lookup_data():
    """Fetches and indexes all 7,400+ student records from Test2 for instant O(1) lookup"""
    records = sheets["lookup"].get_all_records()
    phone_map = {}
    for r in records:
        raw_phone = str(r.get("Contact Number", "")).strip()
        cleaned = clean_phone(raw_phone)
        if cleaned and cleaned not in phone_map:
            phone_map[cleaned] = r
    return records, phone_map

@st.cache_data(ttl=300)
def fetch_auth_data():
    return sheets["auth"].get_all_records()

@st.cache_data(ttl=300)
def fetch_allocation_data():
    return sheets["allocation"].get_all_records()

# ==============================================================================
# 📋 QUESTIONNAIRE SPECIFICATIONS (Page 3 of Survey Protocol)
# ==============================================================================
Q1_OPTIONS = [
    "I run my own small business or work for myself",
    "I do freelance or gig work (like delivery, tutoring, stitching, or online work)",
    "I have a regular job (full-time or part-time)",
    "I am studying or doing another course",
    "I am preparing for a government exam",
    "I am looking for a job",
    "I look after my home and family",
    "I am not working and not looking for work right now"
]

Q2_EARNING_OPTIONS = [
    "Less than Rs 5,000",
    "Rs 5,000 to Rs 10,000",
    "Rs 10,001 to Rs 15,000",
    "Rs 15,001 to Rs 25,000",
    "More than Rs 25,000"
]

Q2A_WORK_TYPES = [
    "Digital work like data entry, writing, design, social media, or video editing",
    "Tech work like coding, web development, or IT support",
    "Gig platform work like Urban Company, Swiggy, Zomato, or delivery",
    "Services like stitching, beauty, repair, tutoring, cooking, or events",
    "Selling or reselling goods online or offline (like Meesho, Amazon, or WhatsApp)",
    "Farming or farm-related work",
    "Others (Please specify)"
]

Q2B_CHANNELS = [
    "Freelance websites like Upwork, Fiverr, or Freelancer.com",
    "Gig apps like Urban Company, Swiggy, Zomato, or Blinkit",
    "Selling apps like Meesho, Amazon, or Flipkart",
    "Instagram, Facebook, or WhatsApp groups",
    "People I know or referrals",
    "Customers who come to me directly or walk in",
    "Others (Please specify)"
]

Q3_TRAINING_RELEVANCE = [
    "Yes, the training helped me start working on my own",
    "A little, it helped with skills but not with finding customers or running a business",
    "No, the training was only about jobs and did not cover independent work",
    "I have not tried to use it for self-employment"
]

Q4_SUPPORT_OPTIONS = [
    "Learning a new skill",
    "Help finding customers or joining platforms like Fiverr or Urban Company",
    "A small loan or money to start or grow my work",
    "Help registering or setting up my business",
    "Guidance or a mentor",
    "Help finding a regular job",
    "I do not need any help right now"
]

CALL_STATUS_OPTIONS = [
    "Did not respond",
    "Switched off",
    "Network issue",
    "Incoming Not Available",
    "Wrong Number",
    "Not a student",
    "Language issue",
    "Call Disconnected",
    "Others"
]

# ==============================================================================
# 🔑 SESSION STATES & LOOKUP LOGIC
# ==============================================================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    st.session_state.user = ""
if "allocated_numbers" not in st.session_state:
    st.session_state.allocated_numbers = []
if "queue_index" not in st.session_state:
    st.session_state.queue_index = 0
if "form_version" not in st.session_state:
    st.session_state.form_version = 0

DEFAULT_FORM = {
    "cmis": "",
    "phone": "",
    "name": "",
    "programme": "",
    "course": "",
    "completion": "",
    "state": "",
    "district": "",
    "gender": "",
    "age_group": "",
    "qualification": "",
    "location_type": ""
}

if "form_initials" not in st.session_state or "programme" not in st.session_state.form_initials:
    st.session_state.form_initials = DEFAULT_FORM.copy()

def load_student_by_phone(phone_target):
    """Searches lookup data from Test2 and stores them cleanly in session state"""
    _, phone_map = fetch_all_lookup_data()
    cleaned = clean_phone(phone_target)
    
    if not cleaned:
        st.session_state.form_initials = DEFAULT_FORM.copy()
        st.session_state.form_version += 1
        return False
        
    match = phone_map.get(cleaned)
    if not match:
        # Fallback partial search
        records, _ = fetch_all_lookup_data()
        for r in records:
            p = str(r.get("Contact Number", "")).strip()
            if cleaned in p or p.endswith(cleaned):
                match = r
                break
                
    if match:
        st.session_state.form_initials = {
            "cmis": str(match.get("CMIS ID", "")).strip(),
            "phone": str(match.get("Contact Number", "")).strip(),
            "name": str(match.get("student_name", "")).strip(),
            "programme": str(match.get("Programme completed", "")).strip(),
            "course": str(match.get("Course or training name", "")).strip(),
            "completion": str(match.get("Month and year of completion", "")).strip(),
            "state": str(match.get("State of residence", "")).strip(),
            "district": str(match.get("District or city", "")).strip(),
            "gender": str(match.get("Gender", "")).strip(),
            "age_group": str(match.get("Age group", "")).strip(),
            "qualification": str(match.get("Highest educational qualification", "")).strip(),
            "location_type": str(match.get("Location type of training centre", "")).strip()
        }
        st.session_state.form_version += 1
        return True
    else:
        st.session_state.form_initials = DEFAULT_FORM.copy()
        st.session_state.form_initials["phone"] = str(phone_target).strip()
        st.session_state.form_version += 1
        return False

# ==============================================================================
# 🚪 AUTHENTICATION UI
# ==============================================================================
if not st.session_state.logged_in:
    st.markdown("<br><br>", unsafe_allow_html=True)
    cols = st.columns([1, 2, 1])
    with cols[1]:
        st.markdown("""
            <div style="text-align: center; margin-bottom: 1.5rem;">
                <h2 style="color: #0f4c81; margin-bottom: 0.2rem;">⚡ High Speed Verification System v4.0</h2>
                <p style="color: #64748b; font-size: 0.95rem;">Non-Placed Graduates Livelihood Study | Anudip Foundation</p>
            </div>
        """, unsafe_allow_html=True)
        tab_log, tab_reg = st.tabs(["🔐 Login", "🆕 Register"])
        with tab_log:
            u = st.text_input("SPOC Name", key="login_user")
            p = st.text_input("Password", type="password", key="login_pass")
            if st.button("Access System", use_container_width=True, type="primary"):
                auth_recs = fetch_auth_data()
                match = next((r for r in auth_recs if str(r.get("spoc_name")).strip().lower() == u.strip().lower()), None)
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
                else:
                    st.error("Invalid Username or Password.")
        with tab_reg:
            nu = st.text_input("New SPOC Name", key="reg_user")
            np = st.text_input("New Password", type="password", key="reg_pass")
            if st.button("Create Account", use_container_width=True):
                if nu and np:
                    sheets["auth"].append_row([nu.strip(), hash_password(np), datetime.now().strftime("%Y-%m-%d")])
                    st.cache_data.clear() 
                    st.success("Registered successfully! Please switch to Login tab.")
                else:
                    st.warning("Please fill all fields.")

# ==============================================================================
# 🏠 MAIN OPERATIONAL DASHBOARD
# ==============================================================================
else:
    # Sidebar
    st.sidebar.markdown(f"### 👤 Logged In: **{st.session_state.user}**")
    total_assigned = len(st.session_state.allocated_numbers)
    current_idx = st.session_state.queue_index
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📋 Verification Queue")
    st.sidebar.metric(label="Assigned in Test3", value=total_assigned)
    if total_assigned > 0:
        progress_val = min(current_idx / total_assigned, 1.0)
        st.sidebar.progress(progress_val)
        st.sidebar.write(f"Calling record **{min(current_idx + 1, total_assigned)}** of **{total_assigned}**")
    else:
        st.sidebar.info("💡 Free Mode: No specific numbers assigned to you in Test3. You can paste and verify any student number directly.")

    if st.sidebar.button("🔴 Logout", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.allocated_numbers = []
        st.session_state.queue_index = 0
        st.session_state.form_initials = DEFAULT_FORM.copy()
        st.session_state.form_version += 1
        st.rerun()

    # SECTION 1: QUEUE & FAST PHONE SEARCH NAVIGATOR
    st.markdown('<div class="section-card"><div class="form-title">⚡ High Speed Queue & Contact Search</div>', unsafe_allow_html=True)
    
    if total_assigned > 0 and current_idx < total_assigned:
        current_target_phone = st.session_state.allocated_numbers[current_idx]
        st.markdown(f'<div class="queue-box">🎯 Active Queue Target #{current_idx + 1}: <b>{current_target_phone}</b> (Progress: {current_idx + 1}/{total_assigned})</div>', unsafe_allow_html=True)
    elif total_assigned > 0 and current_idx >= total_assigned:
        st.markdown('<div class="queue-box" style="background: #e6f4ea; border-left-color: #34a853; color: #137333;">🎉 Verification Queue Completed! Great job!</div>', unsafe_allow_html=True)

    c_search, c_fetch, c_prev, c_next, c_clear, c_refresh = st.columns([3, 1.2, 0.9, 0.9, 1.1, 1.1])
    search_q = c_search.text_input(
        "Search or Paste Contact Number",
        placeholder="Paste student phone number here...",
        label_visibility="collapsed"
    )
    
    # ⚡ Fetch Details
    if c_fetch.button("⚡ Fetch Details", use_container_width=True, type="primary"):
        target = search_q.strip()
        if target:
            # Check if this exists in allocation
            if total_assigned > 0:
                for idx, num in enumerate(st.session_state.allocated_numbers):
                    if clean_phone(target) == clean_phone(num):
                        st.session_state.queue_index = idx
                        break
            found = load_student_by_phone(target)
            if found:
                st.toast("Student record loaded from database!", icon="✅")
            else:
                st.warning("Number not found in Test2 master data. Enter details manually.")
            st.rerun()
        else:
            if total_assigned > 0 and current_idx < total_assigned:
                load_student_by_phone(st.session_state.allocated_numbers[current_idx])
                st.rerun()

    # ⬅️ Prev Button
    if c_prev.button("⬅️ Prev", use_container_width=True, disabled=(total_assigned == 0 or current_idx <= 0)):
        if current_idx > 0:
            st.session_state.queue_index -= 1
            load_student_by_phone(st.session_state.allocated_numbers[st.session_state.queue_index])
            st.rerun()

    # ➡️ Next Button
    if c_next.button("Next ➡️", use_container_width=True, disabled=(total_assigned == 0 or current_idx >= total_assigned - 1)):
        if current_idx < total_assigned - 1:
            st.session_state.queue_index += 1
            load_student_by_phone(st.session_state.allocated_numbers[st.session_state.queue_index])
            st.rerun()

    # 🧹 Clear Form
    if c_clear.button("🧹 Clear Form", use_container_width=True):
        st.session_state.form_initials = DEFAULT_FORM.copy()
        st.session_state.form_version += 1
        st.rerun()

    # 🔄 Refresh DB
    if c_refresh.button("🔄 Refresh DB", use_container_width=True):
        st.cache_data.clear()
        alloc_data = fetch_allocation_data()
        st.session_state.allocated_numbers = [
            str(r.get("phone_number")).strip() for r in alloc_data 
            if str(r.get("SPOC_Name")).strip().lower() == st.session_state.user.strip().lower() and r.get("phone_number")
        ]
        if st.session_state.allocated_numbers and st.session_state.queue_index < len(st.session_state.allocated_numbers):
            load_student_by_phone(st.session_state.allocated_numbers[st.session_state.queue_index])
        st.toast("Database cache refreshed!", icon="🔄")
        st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

    # ==========================================================================
    # SECTION A: RESPONDENT PROFILE (Pre-filled from Test2)
    # ==========================================================================
    st.markdown('<div class="section-card"><div class="form-title">📋 Section A: Respondent Profile</div>', unsafe_allow_html=True)
    
    ver = st.session_state.form_version
    init = st.session_state.form_initials

    pa1, pa2, pa3, pa4 = st.columns(4)
    with pa1:
        f_name = st.text_input("A1. Student / Respondent Name", value=init.get("name", ""), key=f"inp_name_{ver}")
        f_cmis = st.text_input("CMIS ID", value=init.get("cmis", ""), key=f"inp_cmis_{ver}")
        f_phone = st.text_input("A. Contact Number", value=init.get("phone", ""), key=f"inp_phone_{ver}")
    with pa2:
        f_programme = st.text_input("A2. Programme Completed", value=init.get("programme", ""), key=f"inp_prog_{ver}")
        f_course = st.text_input("A3. Course / Training Name", value=init.get("course", ""), key=f"inp_course_{ver}")
        f_completion = st.text_input("A4. Completion Month & Year", value=init.get("completion", ""), key=f"inp_comp_{ver}")
    with pa3:
        f_state = st.text_input("A5. State of Residence", value=init.get("state", ""), key=f"inp_state_{ver}")
        f_district = st.text_input("A6. District / City", value=init.get("district", ""), key=f"inp_dist_{ver}")
        f_location_type = st.text_input("A10. Centre Location Type", value=init.get("location_type", ""), key=f"inp_loc_{ver}")
    with pa4:
        f_gender = st.text_input("A7. Gender", value=init.get("gender", ""), key=f"inp_gen_{ver}")
        f_age_group = st.text_input("A8. Age Group", value=init.get("age_group", ""), key=f"inp_age_{ver}")
        f_qualification = st.text_input("A9. Highest Qualification", value=init.get("qualification", ""), key=f"inp_qual_{ver}")

    st.markdown('</div>', unsafe_allow_html=True)

    # ==========================================================================
    # CALL VERIFICATION DISPOSITION
    # ==========================================================================
  #  st.markdown('<div class="section-card"><div class="form-title">📞 Telecall Status & Contactability</div>', unsafe_allow_html=True)
    
    col_t1, col_t2, col_t3 = st.columns([1.5, 1.5, 3])
    with col_t1:
        f_touch = st.selectbox("Touch Method", ["Tikona_Call", "SPOC_call"], key=f"sel_touch_{ver}")
    with col_t2:
        f_contactable = st.selectbox("Contactable", ["Yes", "No"], key=f"sel_cont_{ver}")
    with col_t3:
        if f_contactable == "No":
            f_call_remarks = st.selectbox("Call Outcome / Reason", CALL_STATUS_OPTIONS, key=f"sel_unreach_{ver}")
        else:
            f_call_remarks = "Connected"
        #    st.info("Student connected successfully. Please proceed to the questionnaire below.")

    st.markdown('</div>', unsafe_allow_html=True)

    # Variables for questionnaire responses
    q1_val = ""
    q2_val = ""
    q2a_val = ""
    q2a_other_val = ""
    q2b_selected = []
    q2b_other_val = ""
    q3_val = ""
    q4_selected = []

    # ==========================================================================
    # SECTIONS B & C: SURVEY QUESTIONNAIRE (Visible if Contactable == Yes)
    # ==========================================================================
    if f_contactable == "Yes":
        # ----------------------------------------------------------------------
        # SECTION B: Current Status and Earnings [Q1 to Q2b]
        # ----------------------------------------------------------------------
        st.markdown('<div class="section-card"><div class="form-title">💼 Section B: Current Status and Earnings</div>', unsafe_allow_html=True)
        st.markdown('<p style="color: #64748b; font-size: 0.88rem; margin-top: -0.5rem;">Estimated completion time: 4 to 5 minutes. All responses are confidential.</p>', unsafe_allow_html=True)
        
        st.markdown("#### **Q1. What are you doing these days?**")
        st.caption("*(Read all options. Ask the respondent to choose one.)*")
        
        q1_selection = st.radio(
            label="Q1 Options",
            options=Q1_OPTIONS,
            index=None,
            key=f"rad_q1_{ver}",
            label_visibility="collapsed"
        )
        q1_val = q1_selection if q1_selection else ""

        # ROUTING LOGIC
        # 1 or 2: Self-employment / freelance / gig -> Q2, Q2a, Q2b, Q3, Q4
        # 3: Regular job -> Q2, then Q3, Q4
        # 4 to 8: Direct to Q3, Q4
        is_path_1_2 = q1_val in [
            "I run my own small business or work for myself",
            "I do freelance or gig work (like delivery, tutoring, stitching, or online work)"
        ]
        is_path_3 = q1_val == "I have a regular job (full-time or part-time)"
        is_path_non_earning = q1_val in Q1_OPTIONS[3:]

        if is_path_1_2:
            st.markdown('<div class="routing-badge badge-self-employed">🌟 Active Pathway: Self-Employed / Freelance / Gig Worker (Complete Q2, Q2a, Q2b, Q3, Q4)</div>', unsafe_allow_html=True)
        elif is_path_3:
            st.markdown('<div class="routing-badge badge-job">💼 Active Pathway: Regular Job (Complete Q2, then jump to Q3 and Q4)</div>', unsafe_allow_html=True)
        elif is_path_non_earning:
            st.markdown('<div class="routing-badge badge-non-earning">📚 Active Pathway: Non-Earning / Studies / Other (Skip Q2, Q2a, Q2b ➔ Proceed directly to Section C)</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="routing-badge badge-inactive">⏳ Please select a response for Q1 above to activate routing</div>', unsafe_allow_html=True)

        # Q2: Monthly Earnings (Asked if Q1 is 1, 2, or 3)
        if is_path_1_2 or is_path_3:
            st.markdown("---")
            st.markdown("#### **Q2. How much do you earn every month from this work?**")
            st.caption("*(Ask only if Q1 response is 1, 2, or 3. Read all options. Ask the respondent to choose one.)*")
            
            q2_selection = st.radio(
                label="Q2 Options",
                options=Q2_EARNING_OPTIONS,
                index=None,
                key=f"rad_q2_{ver}",
                label_visibility="collapsed"
            )
            q2_val = q2_selection if q2_selection else ""

        # Q2a & Q2b: Work Details (Asked ONLY if Q1 is 1 or 2)
        if is_path_1_2:
            st.markdown("---")
            st.markdown("#### **Q2a. What kind of work are you doing?**")
            st.caption("*(Ask only if Q1 response is 1 or 2. Read all options. Ask the respondent to choose one.)*")
            
            q2a_selection = st.radio(
                label="Q2a Options",
                options=Q2A_WORK_TYPES,
                index=None,
                key=f"rad_q2a_{ver}",
                label_visibility="collapsed"
            )
            q2a_val = q2a_selection if q2a_selection else ""
            if q2a_val == "Others (Please specify)":
                q2a_other_val = st.text_input("Please specify kind of work:", key=f"txt_q2a_other_{ver}")

            st.markdown("---")
            st.markdown("#### **Q2b. Where or how do you find your work or customers?**")
            st.caption("*(Ask only if Q1 response is 1 or 2. Read all options. Ask the respondent to choose all that apply - Checkboxes.)*")
            
            # CHECKBOXES for Q2b (NOT A DROPDOWN)
            for idx, ch in enumerate(Q2B_CHANNELS):
                cb_val = st.checkbox(ch, key=f"chk_q2b_{idx}_{ver}")
                if cb_val:
                    q2b_selected.append(ch)
                    if ch == "Others (Please specify)":
                        q2b_other_val = st.text_input("Please specify customer/work source:", key=f"txt_q2b_other_{ver}")

        st.markdown('</div>', unsafe_allow_html=True)

        # ----------------------------------------------------------------------
        # SECTION C: Training and Support [Q3 to Q4]
        # ----------------------------------------------------------------------
        st.markdown('<div class="section-card"><div class="form-title">🎓 Section C: Training and Support</div>', unsafe_allow_html=True)
        
        # Q3: Training Relevance
        st.markdown("#### **Q3. Did the Anudip training help you start your own work or earn on your own?**")
        st.caption("*(Read all options. Ask the respondent to choose one.)*")
        
        q3_selection = st.radio(
            label="Q3 Options",
            options=Q3_TRAINING_RELEVANCE,
            index=None,
            key=f"rad_q3_{ver}",
            label_visibility="collapsed"
        )
        q3_val = q3_selection if q3_selection else ""

        # Q4: Needed Support
        st.markdown("---")
        st.markdown("#### **Q4. What would help you most to earn better or start your own work?**")
        st.caption("*(Read all options. Ask the respondent to choose all that apply. If the respondent does not need any help, record only that option - Checkboxes.)*")
        
        # CHECKBOXES for Q4 (NOT A DROPDOWN)
        q4_no_help_key = f"chk_q4_6_{ver}"
        no_help_checked = st.session_state.get(q4_no_help_key, False)
        
        for idx, sup in enumerate(Q4_SUPPORT_OPTIONS):
            is_none_opt = (sup == "I do not need any help right now")
            # If "no help" is checked, disable other options
            disabled_flag = (not is_none_opt) and no_help_checked
            cb_sup = st.checkbox(sup, key=f"chk_q4_{idx}_{ver}", disabled=disabled_flag)
            if cb_sup and not disabled_flag:
                q4_selected.append(sup)

        st.markdown('</div>', unsafe_allow_html=True)

    # ==========================================================================
    # FINAL DETAILS & SUBMIT
    # ==========================================================================
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    f_sub1, f_sub2 = st.columns([1.5, 3.5])
    with f_sub1:
        f_vdate = st.date_input("Verification Date", value=date.today(), key=f"inp_vdate_{ver}")
    with f_sub2:
        f_spoc_notes = st.text_input("SPOC Notes / Calling Remarks", placeholder="Any additional notes or observations...", key=f"inp_notes_{ver}")

    st.markdown("<br>", unsafe_allow_html=True)
    
    # 🚀 SUBMIT BUTTON
    submit_btn = st.button("🚀 SUBMIT VERIFICATION TO TEST SHEET", use_container_width=True, type="primary")
    if submit_btn:
        # VALIDATION RULES
        can_save = True
        err_msg = ""
        
        if not f_name or not f_cmis:
            can_save = False
            err_msg = "Student Name and CMIS ID are required."
        elif f_contactable == "Yes":
            if not q1_val:
                can_save = False
                err_msg = "Please answer Q1 (What are you doing these days?)."
            elif (is_path_1_2 or is_path_3) and not q2_val:
                can_save = False
                err_msg = "Please answer Q2 (Monthly earnings)."
            elif is_path_1_2 and not q2a_val:
                can_save = False
                err_msg = "Please answer Q2a (Kind of work)."
            elif not q3_val:
                can_save = False
                err_msg = "Please answer Q3 (Did Anudip training help)."
            elif not q4_selected:
                can_save = False
                err_msg = "Please select at least one option for Q4 (Support needed)."
                
        if not can_save:
            st.error(f"⚠️ Validation Failed: {err_msg}")
        else:
            with st.spinner("Saving verification payload to Google Sheet 'Test'..."):
                try:
                    payload = [
                        st.session_state.user,                               # 1: SPOC Name
                        f_touch,                                             # 2: Students Touch Method
                        f_name,                                              # 3: STUDENT NAME
                        f_cmis,                                              # 4: CMISID
                        f_phone,                                             # 5: CONTACT NUMBER
                        f_programme,                                         # 6: Programme completed
                        f_course,                                            # 7: Course or training name
                        f_completion,                                        # 8: Month and year of completion
                        f_state,                                             # 9: State of residence
                        f_district,                                          # 10: District or city
                        f_gender,                                            # 11: Gender
                        f_age_group,                                         # 12: Age group
                        f_qualification,                                     # 13: Highest educational qualification
                        f_location_type,                                     # 14: Location type of training centre
                        f_contactable,                                       # 15: Contactable
                        f_call_remarks,                                      # 16: Call Remarks
                        q1_val if f_contactable == "Yes" else "N/A",         # 17: Q1. Current Status
                        q2_val if f_contactable == "Yes" else "N/A",         # 18: Q2. Monthly Earnings
                        q2a_val if f_contactable == "Yes" else "N/A",        # 19: Q2a. Kind of Work
                        q2a_other_val if f_contactable == "Yes" else "",     # 20: Q2a. Others Specify
                        "; ".join(q2b_selected) if f_contactable == "Yes" else "N/A", # 21: Q2b. Channels
                        q2b_other_val if f_contactable == "Yes" else "",     # 22: Q2b. Others Specify
                        q3_val if f_contactable == "Yes" else "N/A",         # 23: Q3. Training Helpfulness
                        "; ".join(q4_selected) if f_contactable == "Yes" else "N/A",  # 24: Q4. Support Needed
                        str(f_vdate),                                        # 25: Verification Date
                        f_spoc_notes                                         # 26: SPOC Remarks
                    ]
                    
                    sheets["master"].append_row(payload)
                    st.success(f"✅ Record for {f_name} ({f_phone}) saved successfully to Google Sheets!")
                    
                    # Queue progression
                    st.session_state.queue_index += 1
                    if st.session_state.queue_index < len(st.session_state.allocated_numbers):
                        next_phone = st.session_state.allocated_numbers[st.session_state.queue_index]
                        load_student_by_phone(next_phone)
                    else:
                        st.session_state.form_initials = DEFAULT_FORM.copy()
                        st.session_state.form_version += 1
                        if len(st.session_state.allocated_numbers) > 0:
                            st.balloons()
                            
                    time.sleep(0.4)
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error appending row to Google Sheets: {ex}")

    st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="footer">© 2026 Anudip Foundation for Social Welfare | High Speed Verification System v4.0</div>', unsafe_allow_html=True)