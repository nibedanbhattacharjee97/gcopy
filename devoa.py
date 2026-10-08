import streamlit as st
import streamlit.components.v1 as components
import gspread
from google.oauth2.service_account import Credentials
from datetime import date, datetime
import csv
import hashlib
import io
import json
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

def parse_date_safe(d_val):
    """Parses various date string formats into datetime.date, or None if invalid"""
    if not d_val:
        return None
    d_str = str(d_val).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(d_str[:10], fmt).date()
        except Exception:
            pass
    return None

def load_credentials(scopes):
    secrets_dict = None
    
    # 1. Check Streamlit Secrets under common keys (including [connections.gsheets])
    try:
        if hasattr(st, "secrets"):
            if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
                secrets_dict = dict(st.secrets["connections"]["gsheets"])
            elif "connections.gsheets" in st.secrets:
                secrets_dict = dict(st.secrets["connections.gsheets"])
            elif "gcp_service_account" in st.secrets:
                secrets_dict = dict(st.secrets["gcp_service_account"])
            elif "project_id" in st.secrets and "private_key" in st.secrets:
                secrets_dict = dict(st.secrets)
            else:
                for k in st.secrets.keys():
                    val = st.secrets[k]
                    if isinstance(val, dict) or hasattr(val, "get"):
                        if val.get("project_id") and val.get("private_key"):
                            secrets_dict = dict(val)
                            break
                        for sub_k in val.keys():
                            sub_val = val[sub_k]
                            if isinstance(sub_val, dict) or hasattr(sub_val, "get"):
                                if sub_val.get("project_id") and sub_val.get("private_key"):
                                    secrets_dict = dict(sub_val)
                                    break
                    if secrets_dict:
                        break
    except Exception:
        pass

    if secrets_dict:
        # Normalize private key newlines
        if "private_key" in secrets_dict and isinstance(secrets_dict["private_key"], str):
            secrets_dict["private_key"] = secrets_dict["private_key"].replace("\\n", "\n")
        return Credentials.from_service_account_info(secrets_dict, scopes=scopes)

    # 2. Check local file paths
    candidate_paths = [
        "service_account.json",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "service_account.json"),
        os.path.join("gcopy", "service_account.json"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "service_account.json"),
        "d:/testgsheetup/gcopy/service_account.json"
    ]
    for p in candidate_paths:
        if os.path.exists(p):
            return Credentials.from_service_account_file(p, scopes=scopes)

    raise FileNotFoundError("service_account.json could not be found.")

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

@st.cache_resource
def get_sheets_connection():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = load_credentials(scope)
    gc = gspread.authorize(creds)
    
    # Open required sheets
    master_ws = gc.open("Test").sheet1
    auth_ws = gc.open("Test_Spoc_PassWord").sheet1
    lookup_ws = gc.open("Test2").sheet1
    alloc_ws = gc.open("Test3").sheet1
    
    # Synchronize Test headers if needed
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

@st.cache_data(ttl=20)
def fetch_master_data():
    """Fetches all rows from Test verification sheet to check for existing submissions"""
    try:
        return sheets["master"].get_all_values()
    except Exception:
        return []

def find_master_record_by_phone(phone_target):
    """Finds existing record in Test sheet by phone number. Returns (row_data, 1_indexed_row_number) or (None, None)"""
    cleaned = clean_phone(phone_target)
    if not cleaned:
        return None, None
    rows = fetch_master_data()
    # Scan from bottom to top so latest entry is found
    for i in range(len(rows) - 1, 0, -1):
        r = rows[i]
        if len(r) > 4:
            p = clean_phone(r[4])
            if p == cleaned:
                return r, i + 1
    return None, None

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

CALL_STATUS_YES_OPTIONS = [
    "Connected",
    "Not a student",
    "Language issue",
    "Call Disconnected",
    "Others"
]

CALL_STATUS_NO_OPTIONS = [
    "Did not respond",
    "Switched off",
    "Network issue",
    "Incoming Not Available",
    "Wrong Number",
    "Others"
]

CALL_STATUS_OPTIONS = CALL_STATUS_NO_OPTIONS

SURVEY_STATUS_OPTIONS = [
    "Full Information Shared",
    "Dont Want Share Full Information",
    "Call Disconnected / Cut Down Midway"
]

# ==============================================================================
# 🔑 SESSION STATES, QUEUE PROGRESS PERSISTENCE & LOOKUP LOGIC
# ==============================================================================
PROGRESS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spoc_progress.json")

def load_all_spoc_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_spoc_progress(spoc_name, queue_index, phone="", active_call_index=None):
    if not spoc_name:
        return
    try:
        data = load_all_spoc_progress()
        spoc_key = spoc_name.strip().lower()
        prev = data.get(spoc_key, {})
        prev_active = prev.get("active_call_index", prev.get("queue_index", queue_index))
        if active_call_index is None:
            active_call_index = max(int(queue_index), int(prev_active))
        else:
            active_call_index = int(active_call_index)

        data[spoc_key] = {
            "queue_index": int(queue_index),
            "active_call_index": active_call_index,
            "phone": str(phone).strip(),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def get_spoc_saved_index(spoc_name, allocated_numbers):
    if not spoc_name or not allocated_numbers:
        return 0, 0
    data = load_all_spoc_progress()
    saved = data.get(spoc_name.strip().lower())
    if not saved:
        return 0, 0
    
    saved_active = saved.get("active_call_index", saved.get("queue_index", 0))
    if not isinstance(saved_active, int) or saved_active < 0 or saved_active >= len(allocated_numbers):
        saved_active = 0

    saved_phone = clean_phone(saved.get("phone", ""))
    if saved_phone:
        for idx, num in enumerate(allocated_numbers):
            if clean_phone(num) == saved_phone:
                return idx, max(idx, saved_active)
    
    saved_idx = saved.get("queue_index", 0)
    if isinstance(saved_idx, int) and 0 <= saved_idx < len(allocated_numbers):
        return saved_idx, max(saved_idx, saved_active)
    return 0, saved_active

def get_spoc_highest_verified_index(spoc_name, allocated_numbers):
    """Finds the maximum queue index verified in Test sheet so progress is never lost"""
    if not spoc_name or not allocated_numbers:
        return -1
    try:
        rows = fetch_master_data()
        spoc_clean = spoc_name.strip().lower()
        alloc_map = {clean_phone(num): idx for idx, num in enumerate(allocated_numbers) if num}
        highest_idx = -1
        for r in rows[1:]:
            if len(r) > 4 and str(r[0]).strip().lower() == spoc_clean:
                cp = clean_phone(r[4])
                if cp in alloc_map:
                    if alloc_map[cp] > highest_idx:
                        highest_idx = alloc_map[cp]
        return highest_idx
    except Exception:
        return -1

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    st.session_state.user = ""
if "allocated_numbers" not in st.session_state:
    st.session_state.allocated_numbers = []
if "queue_index" not in st.session_state:
    st.session_state.queue_index = 0
if "active_call_index" not in st.session_state:
    st.session_state.active_call_index = 0
if "show_resume_banner" not in st.session_state:
    st.session_state.show_resume_banner = False
if "form_version" not in st.session_state:
    st.session_state.form_version = 0
if "existing_master_row" not in st.session_state:
    st.session_state.existing_master_row = None

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
    "location_type": "",
    "touch_method": "Tikona_Call",
    "contactable": "Yes",
    "call_remarks": "Connected",
    "q1": "",
    "q2": "",
    "q2a": "",
    "q2a_other": "",
    "q2b_selected": [],
    "q2b_other": "",
    "secb_status": "Full Information Shared",
    "q3": "",
    "q4_selected": [],
    "secc_status": "Full Information Shared",
    "vdate": date.today(),
    "spoc_notes": ""
}

if "form_initials" not in st.session_state or "programme" not in st.session_state.form_initials:
    st.session_state.form_initials = DEFAULT_FORM.copy()

def load_student_by_phone(phone_target):
    """
    Searches:
    1. First in Google Sheet 'Test' (submitted records). If found, loads submitted call details in UPDATE mode.
    2. If not found in 'Test', searches 'Test2' (student profile lookup) in NEW SUBMISSION mode.
    """
    cleaned = clean_phone(phone_target)
    if not cleaned:
        st.session_state.existing_master_row = None
        st.session_state.form_initials = DEFAULT_FORM.copy()
        st.session_state.form_version += 1
        return False, "none"

    # Step 1: Check if already submitted in Test
    master_rec, master_row_num = find_master_record_by_phone(cleaned)
    if master_rec and master_row_num:
        row = list(master_rec) + [""] * max(0, 26 - len(master_rec))
        
        contactable_val = row[14].strip() if row[14].strip() in ["Yes", "No"] else "Yes"
        raw_call_remarks = row[15].strip()
        secb_stat = "Full Information Shared"
        secc_stat = "Full Information Shared"
        call_rem_val = "Connected"

        if contactable_val == "Yes":
            if raw_call_remarks == "Connected":
                call_rem_val = "Connected"
            elif raw_call_remarks.startswith("Connected - "):
                call_rem_val = "Connected"
                sub_status = raw_call_remarks.replace("Connected - ", "").strip()
                if sub_status in SURVEY_STATUS_OPTIONS:
                    secb_stat = sub_status
                    secc_stat = sub_status
            elif raw_call_remarks in CALL_STATUS_YES_OPTIONS:
                call_rem_val = raw_call_remarks
            else:
                call_rem_val = "Others"
        else:
            if raw_call_remarks in CALL_STATUS_NO_OPTIONS:
                call_rem_val = raw_call_remarks
            else:
                call_rem_val = "Others"

        q2b_raw = row[20].strip()
        q2b_list = [c.strip() for c in q2b_raw.split(";") if c.strip() and c.strip() != "N/A"] if q2b_raw and q2b_raw != "N/A" else []

        q4_raw = row[23].strip()
        q4_list = [s.strip() for s in q4_raw.split(";") if s.strip() and s.strip() != "N/A"] if q4_raw and q4_raw != "N/A" else []

        st.session_state.existing_master_row = master_row_num
        st.session_state.form_initials = {
            "spoc_name": row[0].strip(),
            "touch_method": row[1].strip() if row[1].strip() in ["Tikona_Call", "SPOC_call"] else "Tikona_Call",
            "name": row[2].strip(),
            "cmis": row[3].strip(),
            "phone": row[4].strip() or str(phone_target).strip(),
            "programme": row[5].strip(),
            "course": row[6].strip(),
            "completion": row[7].strip(),
            "state": row[8].strip(),
            "district": row[9].strip(),
            "gender": row[10].strip(),
            "age_group": row[11].strip(),
            "qualification": row[12].strip(),
            "location_type": row[13].strip(),
            "contactable": contactable_val,
            "call_remarks": call_rem_val,
            "q1": row[16].strip() if row[16].strip() != "N/A" else "",
            "q2": row[17].strip() if row[17].strip() != "N/A" else "",
            "q2a": row[18].strip() if row[18].strip() != "N/A" else "",
            "q2a_other": row[19].strip(),
            "q2b_selected": q2b_list,
            "q2b_other": row[21].strip(),
            "secb_status": secb_stat,
            "q3": row[22].strip() if row[22].strip() != "N/A" else "",
            "q4_selected": q4_list,
            "secc_status": secc_stat,
            "vdate": row[24].strip() if row[24].strip() else str(date.today()),
            "spoc_notes": row[25].strip()
        }
        st.session_state.form_version += 1
        return True, "master"

    # Step 2: Check Test2
    _, phone_map = fetch_all_lookup_data()
    match = phone_map.get(cleaned)
    if not match:
        records, _ = fetch_all_lookup_data()
        for r in records:
            p = str(r.get("Contact Number", "")).strip()
            if cleaned in p or p.endswith(cleaned):
                match = r
                break

    st.session_state.existing_master_row = None
    if match:
        st.session_state.form_initials = DEFAULT_FORM.copy()
        st.session_state.form_initials.update({
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
        })
        st.session_state.form_version += 1
        return True, "lookup"
    else:
        st.session_state.form_initials = DEFAULT_FORM.copy()
        st.session_state.form_initials["phone"] = str(phone_target).strip()
        st.session_state.form_version += 1
        return False, "none"

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
                    
                    saved_idx, saved_active = get_spoc_saved_index(u, spoc_numbers)
                    highest_verified = get_spoc_highest_verified_index(u, spoc_numbers)
                    if highest_verified >= 0 and (highest_verified + 1) < len(spoc_numbers):
                        effective_active = max(saved_active, highest_verified + 1)
                    else:
                        effective_active = saved_active

                    st.session_state.active_call_index = effective_active
                    target_idx = saved_idx if (saved_idx > 0 or effective_active == 0) else effective_active
                    st.session_state.queue_index = target_idx
                    if target_idx > 0 and target_idx < len(spoc_numbers):
                        st.session_state.show_resume_banner = True
                    else:
                        st.session_state.show_resume_banner = False
                    
                    if spoc_numbers:
                        resume_idx = target_idx if target_idx < len(spoc_numbers) else 0
                        load_student_by_phone(spoc_numbers[resume_idx])
                        
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
        st.session_state.active_call_index = 0
        st.session_state.show_resume_banner = False
        st.session_state.existing_master_row = None
        st.session_state.form_initials = DEFAULT_FORM.copy()
        st.session_state.form_version += 1
        st.rerun()

    # ==========================================================================
    # 📥 SPOC VERIFIED DATA EXPORT & FILTERS (Sidebar)
    # ==========================================================================
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📥 Download Verified Data")

    # 1. Verification Date Filter
    vdate_filter_mode = st.sidebar.selectbox(
        "Verification Date",
        ["Total data", "Specific Date", "From - To date"],
        key="side_vdate_mode"
    )

    spec_vdate = None
    from_vdate = None
    to_vdate = None

    if vdate_filter_mode == "Specific Date":
        spec_vdate = st.sidebar.date_input("Select Date", value=date.today(), key="side_spec_vdate")
    elif vdate_filter_mode == "From - To date":
        col_vd1, col_vd2 = st.sidebar.columns(2)
        from_vdate = col_vd1.date_input("From Date", value=date.today(), key="side_from_vdate")
        to_vdate = col_vd2.date_input("To Date", value=date.today(), key="side_to_vdate")

    # 2. Contactable Filter
    cont_filter_mode = st.sidebar.selectbox(
        "Contactable",
        ["Total data", "Yes", "No"],
        key="side_cont_mode"
    )

    # 3. Filter Master Records for this SPOC
    all_master_rows = fetch_master_data()
    master_headers = all_master_rows[0] if (all_master_rows and len(all_master_rows) > 0) else EXPECTED_HEADERS
    
    current_spoc_clean = st.session_state.user.strip().lower()
    raw_spoc_rows = []
    if len(all_master_rows) > 1:
        raw_spoc_rows = [
            r for r in all_master_rows[1:] 
            if len(r) > 0 and str(r[0]).strip().lower() == current_spoc_clean
        ]

    filtered_export_rows = []
    for r in raw_spoc_rows:
        # Date Filter Check (Col Y: index 24)
        row_date_str = str(r[24]).strip() if len(r) > 24 else ""
        row_date = parse_date_safe(row_date_str)
        date_matches = True
        
        if vdate_filter_mode == "Specific Date":
            date_matches = (row_date == spec_vdate) if row_date else (row_date_str == str(spec_vdate))
        elif vdate_filter_mode == "From - To date":
            if row_date and from_vdate and to_vdate:
                date_matches = (from_vdate <= row_date <= to_vdate)
            else:
                date_matches = False

        if not date_matches:
            continue

        # Contactable Filter Check (Col O: index 14)
        row_cont = str(r[14]).strip().lower() if len(r) > 14 else ""
        if cont_filter_mode == "Yes" and row_cont != "yes":
            continue
        elif cont_filter_mode == "No" and row_cont != "no":
            continue

        filtered_export_rows.append(r)

    # CSV Generation
    csv_buf = io.StringIO()
    csv_writer = csv.writer(csv_buf)
    csv_writer.writerow(master_headers)
    for r in filtered_export_rows:
        padded = list(r) + [""] * max(0, len(master_headers) - len(r))
        csv_writer.writerow(padded[:len(master_headers)])
    csv_bytes = csv_buf.getvalue().encode("utf-8")

    st.sidebar.caption(f"📊 Verified records: **{len(filtered_export_rows)}**")

    # Download Button
    st.sidebar.download_button(
        label=f"📥 Download Respective CSVs ({st.session_state.user})",
        data=csv_bytes,
        file_name=f"verified_{st.session_state.user.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        use_container_width=True
    )

    # Resume Banner (If SPOC returned after closing tab/shift)
    if st.session_state.get("show_resume_banner") and total_assigned > 0 and current_idx > 0:
        res_cols = st.columns([3.2, 1.2, 1.2])
        res_cols[0].info(f"📍 **Welcome back!** Resumed at Target **#{current_idx + 1}** of {total_assigned} (where you previously stopped).")
        if res_cols[1].button("▶️ Continue Here", use_container_width=True, type="primary"):
            st.session_state.show_resume_banner = False
            save_spoc_progress(st.session_state.user, current_idx, st.session_state.allocated_numbers[current_idx], active_call_index=st.session_state.active_call_index)
            st.rerun()
        if res_cols[2].button("⏮️ Start from #1", use_container_width=True):
            st.session_state.queue_index = 0
            st.session_state.show_resume_banner = False
            save_spoc_progress(st.session_state.user, 0, st.session_state.allocated_numbers[0], active_call_index=st.session_state.active_call_index)
            load_student_by_phone(st.session_state.allocated_numbers[0])
            st.rerun()

    # SECTION 1: QUEUE & FAST PHONE SEARCH NAVIGATOR
 #   st.markdown('<div class="section-card"><div class="form-title">⚡ High Speed Queue & Contact Search</div>', unsafe_allow_html=True)
    
    if total_assigned > 0 and current_idx < total_assigned:
        current_target_phone = st.session_state.allocated_numbers[current_idx]
        components.html(f"""
        <!DOCTYPE html>
        <html>
        <head>
        <style>
            * {{ box-sizing: border-box; }}
            body {{
                margin: 0;
                padding: 0;
                background: transparent;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            }}
            .queue-banner {{
                background: linear-gradient(135deg, #e8f0fe 0%, #f0f7ff 100%);
                padding: 10px 16px;
                border-radius: 8px;
                border-left: 6px solid #1a73e8;
                font-weight: 700;
                color: #1a365d;
                font-size: 1.05rem;
                display: flex;
                align-items: center;
                gap: 12px;
                flex-wrap: wrap;
            }}
            .phone-number {{
                color: #0d47a1;
                font-weight: 800;
                font-size: 1.15rem;
                letter-spacing: 0.5px;
            }}
            .copy-btn {{
                background: #1a73e8;
                color: #ffffff;
                border: none;
                padding: 5px 14px;
                border-radius: 6px;
                cursor: pointer;
                font-size: 0.85rem;
                font-weight: 700;
                display: inline-flex;
                align-items: center;
                gap: 5px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.12);
                transition: all 0.15s ease-in-out;
            }}
            .copy-btn:hover {{
                background: #1557b0;
                transform: translateY(-1px);
                box-shadow: 0 2px 6px rgba(0,0,0,0.18);
            }}
            .copy-btn.copied {{
                background: #10b981;
            }}
            .progress-info {{
                color: #64748b;
                font-weight: 600;
                font-size: 0.95rem;
            }}
        </style>
        </head>
        <body>
        <div class="queue-banner">
            <span>🎯 Active Queue Target #{current_idx + 1}: <span class="phone-number">{current_target_phone}</span></span>
            <button id="copyBtn" class="copy-btn" onclick="copyNumber()">📋 Copy Phone Number</button>
            <span class="progress-info">(Progress: {current_idx + 1}/{total_assigned})</span>
        </div>
        <script>
        function copyNumber() {{
            const num = "{current_target_phone}";
            if (navigator.clipboard && window.isSecureContext) {{
                navigator.clipboard.writeText(num).then(showSuccess, fallbackCopy);
            }} else {{
                fallbackCopy();
            }}
            function showSuccess() {{
                const btn = document.getElementById("copyBtn");
                btn.innerHTML = "✅ Copied!";
                btn.className = "copy-btn copied";
                setTimeout(() => {{
                    btn.innerHTML = "📋 Copy Phone Number";
                    btn.className = "copy-btn";
                }}, 2000);
            }}
            function fallbackCopy() {{
                const ta = document.createElement("textarea");
                ta.value = num;
                ta.style.position = "fixed";
                ta.style.top = "0";
                ta.style.left = "0";
                ta.style.opacity = "0";
                document.body.appendChild(ta);
                ta.focus();
                ta.select();
                try {{
                    document.execCommand("copy");
                    showSuccess();
                }} catch (e) {{
                    console.error("Copy failed", e);
                }}
                document.body.removeChild(ta);
            }}
        }}
        </script>
        </body>
        </html>
        """, height=52)
    elif total_assigned > 0 and current_idx >= total_assigned:
        st.markdown('<div class="queue-box" style="background: #e6f4ea; border-left-color: #34a853; color: #137333;">🎉 Verification Queue Completed! Great job!</div>', unsafe_allow_html=True)

    c_search, c_fetch, c_start, c_prev, c_next, c_clear, c_refresh = st.columns([2.7, 1.2, 0.9, 0.8, 0.8, 1.1, 1.1])
    search_q = c_search.text_input(
        "Search or Paste Contact Number",
        placeholder="Search phone or enter Target # (e.g. 71, 302)...",
        label_visibility="collapsed"
    )
    
    # ⚡ Fetch Details / Jump to Target
    if c_fetch.button("⚡ Fetch Details", use_container_width=True, type="primary"):
        target = search_q.strip()
        if target:
            clean_target_num = target.lstrip("#").strip()
            # If input is a queue number (e.g. 71, #71, 302, 20, 21...)
            if clean_target_num.isdigit() and total_assigned > 0 and (1 <= int(clean_target_num) <= total_assigned):
                target_idx = int(clean_target_num) - 1
                st.session_state.queue_index = target_idx
                st.session_state.show_resume_banner = False
                if target_idx > st.session_state.active_call_index:
                    st.session_state.active_call_index = target_idx
                phone_num = st.session_state.allocated_numbers[target_idx]
                save_spoc_progress(st.session_state.user, target_idx, phone_num, active_call_index=st.session_state.active_call_index)
                load_student_by_phone(phone_num)
                st.toast(f"Jumped to Target #{target_idx + 1} ({phone_num})!", icon="🎯")
                st.rerun()
            else:
                # Phone lookup
                if total_assigned > 0:
                    for idx, num in enumerate(st.session_state.allocated_numbers):
                        if clean_phone(target) == clean_phone(num):
                            st.session_state.queue_index = idx
                            st.session_state.show_resume_banner = False
                            # Preserve active_call_index so calling position is not lost!
                            save_spoc_progress(st.session_state.user, idx, num, active_call_index=st.session_state.active_call_index)
                            break
                found, src = load_student_by_phone(target)
                if found:
                    if src == "master":
                        row_num = st.session_state.get("existing_master_row")
                        st.toast(f"Found existing record in Test (Row #{row_num})! Loaded for update.", icon="📝")
                    else:
                        st.toast("Student record loaded from database!", icon="✅")
                else:
                    st.warning("Number not found in Test or Test2 database. Enter details manually.")
                st.rerun()
        else:
            if total_assigned > 0 and current_idx < total_assigned:
                phone_num = st.session_state.allocated_numbers[current_idx]
                save_spoc_progress(st.session_state.user, current_idx, phone_num, active_call_index=st.session_state.active_call_index)
                load_student_by_phone(phone_num)
                st.rerun()

    # ⏮️ #1 Button (Start from Beginning)
    if c_start.button("⏮️ #1", use_container_width=True, help="Jump to Target #1 (Queue beginning)", disabled=(total_assigned == 0 or current_idx == 0)):
        st.session_state.queue_index = 0
        st.session_state.show_resume_banner = False
        save_spoc_progress(st.session_state.user, 0, st.session_state.allocated_numbers[0], active_call_index=st.session_state.active_call_index)
        load_student_by_phone(st.session_state.allocated_numbers[0])
        st.toast("Jumped to Target #1!", icon="⏮️")
        st.rerun()

    # ⬅️ Prev Button
    if c_prev.button("⬅️ Prev", use_container_width=True, disabled=(total_assigned == 0 or current_idx <= 0)):
        if current_idx > 0:
            st.session_state.queue_index -= 1
            st.session_state.show_resume_banner = False
            phone_num = st.session_state.allocated_numbers[st.session_state.queue_index]
            save_spoc_progress(st.session_state.user, st.session_state.queue_index, phone_num, active_call_index=st.session_state.active_call_index)
            load_student_by_phone(phone_num)
            st.rerun()

    # ➡️ Next Button
    if c_next.button("Next ➡️", use_container_width=True, disabled=(total_assigned == 0 or current_idx >= total_assigned - 1)):
        if current_idx < total_assigned - 1:
            st.session_state.queue_index += 1
            st.session_state.show_resume_banner = False
            if st.session_state.queue_index > st.session_state.active_call_index:
                st.session_state.active_call_index = st.session_state.queue_index
            phone_num = st.session_state.allocated_numbers[st.session_state.queue_index]
            save_spoc_progress(st.session_state.user, st.session_state.queue_index, phone_num, active_call_index=st.session_state.active_call_index)
            load_student_by_phone(phone_num)
            st.rerun()

    # 🎯 Direct Queue Jump & Resume Latest Call Toolbar (Image 2)
    if total_assigned > 0:
        st.markdown("<div style='margin-top: 4px; margin-bottom: 8px;'></div>", unsafe_allow_html=True)
        cj_lbl, cj_inp, cj_btn, cj_latest = st.columns([1.6, 1.6, 1.4, 3.4])
        with cj_lbl:
            st.markdown("<div style='padding-top: 8px; font-weight: 700; color: #1e3a8a; font-size: 0.95rem;'>🎯 Jump to Queue #:</div>", unsafe_allow_html=True)
        with cj_inp:
            jump_input_val = st.number_input(
                "Queue Target Number",
                min_value=1,
                max_value=total_assigned,
                value=min(current_idx + 1, total_assigned),
                step=1,
                label_visibility="collapsed",
                key="num_jump_target_input"
            )
        with cj_btn:
            if st.button("🚀 Jump", use_container_width=True, help="Jump directly to chosen target number (e.g. 20, 21, 71, 302...)"):
                chosen_idx = int(jump_input_val) - 1
                st.session_state.queue_index = chosen_idx
                st.session_state.show_resume_banner = False
                if chosen_idx > st.session_state.active_call_index:
                    st.session_state.active_call_index = chosen_idx
                p_num = st.session_state.allocated_numbers[chosen_idx]
                save_spoc_progress(st.session_state.user, chosen_idx, p_num, active_call_index=st.session_state.active_call_index)
                load_student_by_phone(p_num)
                st.toast(f"Jumped to Target #{chosen_idx + 1}!", icon="🎯")
                st.rerun()
        with cj_latest:
            active_target_display = min(st.session_state.active_call_index + 1, total_assigned)
            is_at_latest = (current_idx == st.session_state.active_call_index)
            latest_label = f"📍 At Latest Call: Target #{active_target_display}" if is_at_latest else f"⚡ Resume Latest Call: Target #{active_target_display}"
            if st.button(latest_label, use_container_width=True, type="secondary" if is_at_latest else "primary", help=f"Jump directly to your active calling target (#{active_target_display})"):
                st.session_state.queue_index = st.session_state.active_call_index
                st.session_state.show_resume_banner = False
                p_num = st.session_state.allocated_numbers[st.session_state.queue_index]
                save_spoc_progress(st.session_state.user, st.session_state.queue_index, p_num, active_call_index=st.session_state.active_call_index)
                load_student_by_phone(p_num)
                st.toast(f"Jumped to Latest Call Target #{active_target_display}!", icon="⚡")
                st.rerun()

    # 🧹 Clear Form
    if c_clear.button("🧹 Clear Form", use_container_width=True):
        st.session_state.existing_master_row = None
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

    ver = st.session_state.form_version
    init = st.session_state.form_initials

    # UPDATE MODE NOTIFICATION (If editing a previously submitted record)
    if st.session_state.get("existing_master_row"):
        r_num = st.session_state.existing_master_row
        st.markdown(f"""
        <div style="background: #fffbeb; border: 2px solid #f59e0b; border-radius: 10px; padding: 14px 18px; margin-bottom: 1.2rem; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; box-shadow: 0 2px 8px rgba(245,158,11,0.12);">
            <div>
                <span style="font-size: 1.25rem; margin-right: 6px;">📝</span>
                <strong style="color: #92400e; font-size: 1.05rem;">PREVIOUSLY SUBMITTED RECORD FOUND (Row #{r_num} in Test Sheet) — UPDATE MODE ACTIVE</strong>
                <p style="margin: 4px 0 0 0; color: #78350f; font-size: 0.88rem; line-height: 1.4;">
                    All previously submitted call details for this student ({init.get('phone', '')}) have been loaded into the form below. 
                    <br>You can update any field (Call Outcome, Answers, Remarks) and submit — <strong>it will update Row #{r_num} directly without creating a duplicate record</strong>.
                </p>
            </div>
            <span style="background: #f59e0b; color: #ffffff; padding: 6px 14px; border-radius: 6px; font-weight: 700; font-size: 0.85rem; letter-spacing: 0.5px;">
                ✏️ UPDATE IN-PLACE
            </span>
        </div>
        """, unsafe_allow_html=True)

    # ==========================================================================
    # SECTION A: RESPONDENT PROFILE (Pre-filled from Test2)
    # ==========================================================================
    st.markdown('<div class="section-card"><div class="form-title">📋 Section A: Respondent Profile</div>', unsafe_allow_html=True)
    
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
        touch_opts = ["Tikona_Call", "SPOC_call"]
        saved_touch = init.get("touch_method", "Tikona_Call")
        touch_idx = touch_opts.index(saved_touch) if saved_touch in touch_opts else 0
        f_touch = st.selectbox("Touch Method", touch_opts, index=touch_idx, key=f"sel_touch_{ver}")
    with col_t2:
        cont_opts = ["Yes", "No"]
        saved_cont = init.get("contactable", "Yes")
        cont_idx = cont_opts.index(saved_cont) if saved_cont in cont_opts else 0
        f_contactable = st.selectbox("Contactable", cont_opts, index=cont_idx, key=f"sel_cont_{ver}")
    with col_t3:
        if f_contactable == "Yes":
            saved_rem = init.get("call_remarks", "Connected")
            rem_idx = CALL_STATUS_YES_OPTIONS.index(saved_rem) if saved_rem in CALL_STATUS_YES_OPTIONS else 0
            f_call_remarks = st.selectbox("Call Outcome / Reason", CALL_STATUS_YES_OPTIONS, index=rem_idx, key=f"sel_reach_{ver}")
        else:
            saved_rem = init.get("call_remarks", "RNR (Ring No Response)")
            rem_idx = CALL_STATUS_NO_OPTIONS.index(saved_rem) if saved_rem in CALL_STATUS_NO_OPTIONS else 0
            f_call_remarks = st.selectbox("Call Outcome / Reason", CALL_STATUS_NO_OPTIONS, index=rem_idx, key=f"sel_unreach_{ver}")

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
    b_survey_status = "Full Information Shared"
    c_survey_status = "Full Information Shared"

    # ==========================================================================
    # SECTIONS B & C: SURVEY QUESTIONNAIRE (Visible if Contactable == Yes and Connected)
    # ==========================================================================
    if f_contactable == "Yes" and f_call_remarks == "Connected":
        # ----------------------------------------------------------------------
        # SECTION B: Current Status and Earnings [Q1 to Q2b]
        # ----------------------------------------------------------------------
        st.markdown('<div class="section-card"><div class="form-title">💼 Section B: Current Status and Earnings</div>', unsafe_allow_html=True)
        st.markdown('<p style="color: #64748b; font-size: 0.88rem; margin-top: -0.5rem; margin-bottom: 1.2rem;">Estimated completion time: 4 to 5 minutes. All responses are confidential.</p>', unsafe_allow_html=True)

        col_q1, col_follow = st.columns([1, 1.15], gap="large")

        with col_q1:
            st.markdown("#### **Q1. What are you doing these days?**")
            st.caption("*(Read all options. Ask the respondent to choose one.)*")
            
            q1_saved = init.get("q1", "")
            q1_idx = Q1_OPTIONS.index(q1_saved) if q1_saved in Q1_OPTIONS else None
            q1_selection = st.radio(
                label="Q1 Options",
                options=Q1_OPTIONS,
                index=q1_idx,
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
                st.markdown('<div class="routing-badge badge-self-employed" style="display: block; text-align: center; margin-top: 0.8rem;">🌟 Active Pathway: Self-Employed / Freelance / Gig Worker<br><span style="font-weight: 500; font-size: 0.8rem;">(Complete Q2, Q2a, Q2b on the right)</span></div>', unsafe_allow_html=True)
            elif is_path_3:
                st.markdown('<div class="routing-badge badge-job" style="display: block; text-align: center; margin-top: 0.8rem;">💼 Active Pathway: Regular Job<br><span style="font-weight: 500; font-size: 0.8rem;">(Complete Q2 on the right ➔ Proceed to Section C)</span></div>', unsafe_allow_html=True)
            elif is_path_non_earning:
                st.markdown('<div class="routing-badge badge-non-earning" style="display: block; text-align: center; margin-top: 0.8rem;">📚 Active Pathway: Non-Earning / Studies / Other<br><span style="font-weight: 500; font-size: 0.8rem;">(Skip Q2, Q2a, Q2b ➔ Proceed directly to Section C)</span></div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="routing-badge badge-inactive" style="display: block; text-align: center; margin-top: 0.8rem;">⏳ Please select a response for Q1 above to activate routing</div>', unsafe_allow_html=True)

        with col_follow:
            if not q1_val:
                st.markdown("""
                    <div style="background: #f8fafc; border: 2px dashed #cbd5e1; border-radius: 12px; padding: 3rem 1.5rem; text-align: center; color: #64748b; margin-top: 0.5rem;">
                        <div style="font-size: 2.2rem; margin-bottom: 0.5rem;">👉</div>
                        <div style="font-weight: 700; color: #1e293b; font-size: 1.05rem;">Follow-up Questions</div>
                        <p style="font-size: 0.88rem; color: #64748b; margin-top: 0.5rem; line-height: 1.5; max-width: 380px; margin-left: auto; margin-right: auto;">
                            Select the respondent's current activity in <strong>Q1</strong> on the left to display the appropriate follow-up questions (<strong>Q2, Q2a, Q2b</strong>).
                        </p>
                    </div>
                """, unsafe_allow_html=True)

            elif is_path_non_earning:
                st.markdown("""
                    <div style="background: #fffaf0; border: 1px solid #fbd38d; border-radius: 12px; padding: 2.5rem 1.5rem; text-align: center; color: #744210; margin-top: 0.5rem;">
                        <div style="font-size: 2.2rem; margin-bottom: 0.5rem;">📚</div>
                        <div style="font-weight: 700; font-size: 1.05rem; color: #744210; margin-bottom: 0.4rem;">Non-Earning / Studies Pathway</div>
                        <p style="font-size: 0.88rem; color: #975a16; line-height: 1.5; margin-bottom: 1rem;">
                            Questions <strong>Q2, Q2a, and Q2b</strong> are not applicable for this status.
                        </p>
                        <div style="background: #ffffff; display: inline-block; padding: 0.45rem 1.1rem; border-radius: 20px; border: 1px solid #fbd38d; font-size: 0.85rem; font-weight: 600; color: #744210;">
                            ⬇️ Proceed directly to Section C (Training and Support) below
                        </div>
                    </div>
                """, unsafe_allow_html=True)

            elif is_path_3:
                # Q2: Monthly Earnings (Asked for Regular Job)
                st.markdown("#### **Q2. How much do you earn every month from this work?**")
                st.caption("*(Ask only if Q1 response is 1, 2, or 3. Read all options. Ask the respondent to choose one.)*")
                
                q2_saved = init.get("q2", "")
                q2_idx = Q2_EARNING_OPTIONS.index(q2_saved) if q2_saved in Q2_EARNING_OPTIONS else None
                q2_selection = st.radio(
                    label="Q2 Options",
                    options=Q2_EARNING_OPTIONS,
                    index=q2_idx,
                    key=f"rad_q2_{ver}",
                    label_visibility="collapsed"
                )
                q2_val = q2_selection if q2_selection else ""

                st.markdown("""
                    <div style="background: #ebf8ff; border: 1px solid #bee3f8; border-radius: 8px; padding: 0.85rem 1rem; color: #2a4365; font-size: 0.88rem; margin-top: 1rem;">
                        💼 <strong>Regular Job Pathway:</strong> Questions Q2a and Q2b are skipped. Please proceed directly to Section C below.
                    </div>
                """, unsafe_allow_html=True)

            elif is_path_1_2:
                # Q2: Monthly Earnings
                st.markdown("#### **Q2. How much do you earn every month from this work?**")
                st.caption("*(Ask only if Q1 response is 1, 2, or 3. Read all options. Ask the respondent to choose one.)*")
                
                q2_saved = init.get("q2", "")
                q2_idx = Q2_EARNING_OPTIONS.index(q2_saved) if q2_saved in Q2_EARNING_OPTIONS else None
                q2_selection = st.radio(
                    label="Q2 Options",
                    options=Q2_EARNING_OPTIONS,
                    index=q2_idx,
                    key=f"rad_q2_{ver}",
                    label_visibility="collapsed"
                )
                q2_val = q2_selection if q2_selection else ""

                st.markdown('<hr style="margin: 1.2rem 0; border: none; border-top: 1px solid #e2e8f0;">', unsafe_allow_html=True)

                # Q2a: Kind of Work
                st.markdown("#### **Q2a. What kind of work are you doing?**")
                st.caption("*(Ask only if Q1 response is 1 or 2. Read all options. Ask the respondent to choose one.)*")
                
                q2a_saved = init.get("q2a", "")
                q2a_idx = Q2A_WORK_TYPES.index(q2a_saved) if q2a_saved in Q2A_WORK_TYPES else None
                q2a_selection = st.radio(
                    label="Q2a Options",
                    options=Q2A_WORK_TYPES,
                    index=q2a_idx,
                    key=f"rad_q2a_{ver}",
                    label_visibility="collapsed"
                )
                q2a_val = q2a_selection if q2a_selection else ""
                if q2a_val == "Others (Please specify)":
                    q2a_other_val = st.text_input("Please specify kind of work:", value=init.get("q2a_other", ""), placeholder="Enter work description...", key=f"txt_q2a_other_{ver}")

                st.markdown('<hr style="margin: 1.2rem 0; border: none; border-top: 1px solid #e2e8f0;">', unsafe_allow_html=True)

                # Q2b: Sourcing Channels
                st.markdown("#### **Q2b. Where or how do you find your work or customers?**")
                st.caption("*(Ask only if Q1 response is 1 or 2. Read all options. Ask the respondent to choose all that apply - Checkboxes.)*")
                
                # CHECKBOXES for Q2b (NOT A DROPDOWN)
                saved_q2b = init.get("q2b_selected", [])
                for idx, ch in enumerate(Q2B_CHANNELS):
                    cb_val = st.checkbox(ch, value=(ch in saved_q2b), key=f"chk_q2b_{idx}_{ver}")
                    if cb_val:
                        q2b_selected.append(ch)
                        if ch == "Others (Please specify)":
                            q2b_other_val = st.text_input("Please specify customer/work source:", value=init.get("q2b_other", ""), placeholder="Enter customer/work source...", key=f"txt_q2b_other_{ver}")

        st.markdown('<hr style="margin: 1.4rem 0 1rem 0; border: none; border-top: 1px solid #e2e8f0;">', unsafe_allow_html=True)
        col_sb1, col_sb2 = st.columns([2.5, 2.5])
        with col_sb1:
            saved_secb = init.get("secb_status", "Full Information Shared")
            secb_idx = SURVEY_STATUS_OPTIONS.index(saved_secb) if saved_secb in SURVEY_STATUS_OPTIONS else 0
            b_survey_status = st.selectbox(
                "Section B: Information Sharing Status",
                SURVEY_STATUS_OPTIONS,
                index=secb_idx,
                key=f"sel_secb_status_{ver}",
                help="Select if respondent refused to share full details or call disconnected during Section B"
            )

        st.markdown('</div>', unsafe_allow_html=True)

        # ----------------------------------------------------------------------
        # SECTION C: Training and Support [Q3 to Q4]
        # ----------------------------------------------------------------------
        if b_survey_status == "Full Information Shared":
            st.markdown('<div class="section-card"><div class="form-title">🎓 Section C: Training and Support</div>', unsafe_allow_html=True)
            
            # Q3: Training Relevance
            st.markdown("#### **Q3. Did the Anudip training help you start your own work or earn on your own?**")
            st.caption("*(Read all options. Ask the respondent to choose one.)*")
            
            q3_saved = init.get("q3", "")
            q3_idx = Q3_TRAINING_RELEVANCE.index(q3_saved) if q3_saved in Q3_TRAINING_RELEVANCE else None
            q3_selection = st.radio(
                label="Q3 Options",
                options=Q3_TRAINING_RELEVANCE,
                index=q3_idx,
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
            saved_q4 = init.get("q4_selected", [])
            
            for idx, sup in enumerate(Q4_SUPPORT_OPTIONS):
                is_none_opt = (sup == "I do not need any help right now")
                # If "no help" is checked, disable other options
                disabled_flag = (not is_none_opt) and no_help_checked
                is_checked = (sup in saved_q4) if not disabled_flag else False
                cb_sup = st.checkbox(sup, value=is_checked, key=f"chk_q4_{idx}_{ver}", disabled=disabled_flag)
                if cb_sup and not disabled_flag:
                    q4_selected.append(sup)

            st.markdown('<hr style="margin: 1.4rem 0 1rem 0; border: none; border-top: 1px solid #e2e8f0;">', unsafe_allow_html=True)
            col_sc1, col_sc2 = st.columns([2.5, 2.5])
            with col_sc1:
                saved_secc = init.get("secc_status", "Full Information Shared")
                secc_idx = SURVEY_STATUS_OPTIONS.index(saved_secc) if saved_secc in SURVEY_STATUS_OPTIONS else 0
                c_survey_status = st.selectbox(
                    "Section C: Information Sharing Status",
                    SURVEY_STATUS_OPTIONS,
                    index=secc_idx,
                    key=f"sel_secc_status_{ver}",
                    help="Select if respondent refused to share full details or call disconnected during Section C"
                )

            st.markdown('</div>', unsafe_allow_html=True)
        else:
            c_survey_status = b_survey_status
            st.markdown(f'''
                <div class="section-card" style="border-left: 5px solid #f59e0b; background: #fffdfa;">
                    <div style="font-weight: 700; color: #92400e; font-size: 1rem; margin-bottom: 0.3rem;">
                        ⚠️ Section B Status: {b_survey_status}
                    </div>
                    <p style="color: #78350f; font-size: 0.88rem; margin: 0;">
                        Student did not provide full information for Section B (<strong>{b_survey_status}</strong>). Section C (Training and Support) is skipped.
                        <br>You can enter any additional notes in <strong>SPOC Notes</strong> below and click <strong>Submit</strong>.
                    </p>
                </div>
            ''', unsafe_allow_html=True)

    elif f_contactable == "Yes":
        st.markdown(f'''
            <div class="section-card" style="border-left: 5px solid #0f4c81; background: #f8fafc;">
                <div class="form-title" style="color: #0f4c81; font-size: 1.1rem; margin-bottom: 0.4rem;">
                    📞 Call Outcome: {f_call_remarks}
                </div>
                <p style="color: #475569; font-size: 0.9rem; margin-bottom: 0;">
                    Student was reached / tracked (<strong>Contactable: Yes</strong>) with outcome: <strong>{f_call_remarks}</strong>.<br>
                    Survey questionnaire (Sections B & C) is skipped. Please enter any additional details in <strong>SPOC Notes</strong> below and submit.
                </p>
            </div>
        ''', unsafe_allow_html=True)

    # ==========================================================================
    # FINAL DETAILS & SUBMIT
    # ==========================================================================
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    f_sub1, f_sub2 = st.columns([1.5, 3.5])
    init_vdate = init.get("vdate")
    if isinstance(init_vdate, str) and init_vdate:
        try:
            init_vdate = datetime.strptime(init_vdate, "%Y-%m-%d").date()
        except Exception:
            init_vdate = date.today()
    elif not isinstance(init_vdate, (date, datetime)):
        init_vdate = date.today()

    with f_sub1:
        f_vdate = st.date_input("Verification Date", value=init_vdate, key=f"inp_vdate_{ver}")
    with f_sub2:
        f_spoc_notes = st.text_input("SPOC Notes / Calling Remarks", value=init.get("spoc_notes", ""), placeholder="Any additional notes or observations...", key=f"inp_notes_{ver}")

    st.markdown("<br>", unsafe_allow_html=True)
    
    # 🚀 SUBMIT / UPDATE BUTTON
    is_update_mode = bool(st.session_state.get("existing_master_row"))
    if is_update_mode:
        row_num = st.session_state.existing_master_row
        submit_btn = st.button(
            f"🔄 UPDATE EXISTING RECORD IN TEST SHEET (Row #{row_num} - No Duplicate)", 
            use_container_width=True, 
            type="primary"
        )
    else:
        submit_btn = st.button(
            "🚀 SUBMIT VERIFICATION TO TEST SHEET", 
            use_container_width=True, 
            type="primary"
        )

    if submit_btn:
        # VALIDATION RULES
        can_save = True
        err_msg = ""
        
        if not f_name or not f_cmis:
            can_save = False
            err_msg = "Student Name and CMIS ID are required."
        elif f_contactable == "Yes" and f_call_remarks == "Connected":
            if b_survey_status == "Full Information Shared":
                if not q1_val:
                    can_save = False
                    err_msg = "Please answer Q1 (What are you doing these days?), or select 'Dont Want Share Full Information' if refused."
                elif (is_path_1_2 or is_path_3) and not q2_val:
                    can_save = False
                    err_msg = "Please answer Q2 (Monthly earnings), or select 'Dont Want Share Full Information' if refused."
                elif is_path_1_2 and not q2a_val:
                    can_save = False
                    err_msg = "Please answer Q2a (Kind of work), or select 'Dont Want Share Full Information' if refused."
                elif c_survey_status == "Full Information Shared":
                    if not q3_val:
                        can_save = False
                        err_msg = "Please answer Q3 (Did Anudip training help), or select 'Dont Want Share Full Information' if refused."
                    elif not q4_selected:
                        can_save = False
                        err_msg = "Please select at least one option for Q4 (Support needed), or select 'Dont Want Share Full Information' if refused."
                
        if not can_save:
            st.error(f"⚠️ Validation Failed: {err_msg}")
        else:
            with st.spinner("Saving verification payload to Google Sheet 'Test'..."):
                try:
                    is_survey_active = (f_contactable == "Yes" and f_call_remarks == "Connected")
                    
                    if is_survey_active:
                        if b_survey_status != "Full Information Shared":
                            final_call_remarks = f"Connected - {b_survey_status}"
                        elif c_survey_status != "Full Information Shared":
                            final_call_remarks = f"Connected - {c_survey_status}"
                        else:
                            final_call_remarks = "Connected"
                    else:
                        final_call_remarks = f_call_remarks

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
                        final_call_remarks,                                  # 16: Call Remarks
                        q1_val if (is_survey_active and q1_val) else "N/A",  # 17: Q1. Current Status
                        q2_val if (is_survey_active and q2_val) else "N/A",  # 18: Q2. Monthly Earnings
                        q2a_val if (is_survey_active and q2a_val) else "N/A", # 19: Q2a. Kind of Work
                        q2a_other_val if is_survey_active else "",           # 20: Q2a. Others Specify
                        "; ".join(q2b_selected) if (is_survey_active and q2b_selected) else "N/A", # 21: Q2b. Channels
                        q2b_other_val if is_survey_active else "",           # 22: Q2b. Others Specify
                        q3_val if (is_survey_active and q3_val) else "N/A",  # 23: Q3. Training Helpfulness
                        "; ".join(q4_selected) if (is_survey_active and q4_selected) else "N/A",  # 24: Q4. Support Needed
                        str(f_vdate),                                        # 25: Verification Date
                        f_spoc_notes                                         # 26: SPOC Remarks
                    ]
                    
                    # Determine whether this is an UPDATE or NEW APPEND
                    target_row = st.session_state.get("existing_master_row")
                    
                    # Extra safety: Check Test sheet one more time by clean phone
                    if not target_row:
                        cleaned_cur_phone = clean_phone(f_phone)
                        if cleaned_cur_phone:
                            m_rows = fetch_master_data()
                            for i in range(len(m_rows) - 1, 0, -1):
                                if len(m_rows[i]) > 4 and clean_phone(m_rows[i][4]) == cleaned_cur_phone:
                                    target_row = i + 1
                                    break

                    is_update_record = bool(target_row)

                    if target_row:
                        sheets["master"].update(values=[payload], range_name=f"A{target_row}:Z{target_row}")
                        st.cache_data.clear()
                        st.session_state.existing_master_row = None
                        st.success(f"✅ Record for {f_name} ({f_phone}) UPDATED successfully in Google Sheet 'Test' (Row #{target_row})! No duplicate created.")
                    else:
                        sheets["master"].append_row(payload)
                        st.cache_data.clear()
                        st.session_state.existing_master_row = None
                        st.success(f"✅ Record for {f_name} ({f_phone}) saved successfully to Google Sheet 'Test'!")
                    
                    # Queue progression
                    if is_update_record:
                        # 🎯 FIX FOR UPDATE QUEUE RESET ISSUE:
                        # Updating a student's details must NOT advance queue to edited_idx + 1 (e.g. Queue 2).
                        # Return SPOC back to their active calling target (e.g. Call #71)!
                        target_resume_idx = st.session_state.get("active_call_index", st.session_state.queue_index)
                        if total_assigned > 0 and target_resume_idx < total_assigned:
                            st.session_state.queue_index = target_resume_idx
                            next_phone = st.session_state.allocated_numbers[target_resume_idx]
                            save_spoc_progress(st.session_state.user, target_resume_idx, next_phone, active_call_index=target_resume_idx)
                            load_student_by_phone(next_phone)
                            st.toast(f"Update saved! Returned to active calling queue: Target #{target_resume_idx + 1}", icon="🎯")
                        else:
                            st.session_state.form_initials = DEFAULT_FORM.copy()
                            st.session_state.form_version += 1
                    else:
                        # Normal sequential verification call
                        st.session_state.queue_index += 1
                        if st.session_state.queue_index > st.session_state.active_call_index:
                            st.session_state.active_call_index = st.session_state.queue_index

                        if st.session_state.queue_index < len(st.session_state.allocated_numbers):
                            next_phone = st.session_state.allocated_numbers[st.session_state.queue_index]
                            save_spoc_progress(st.session_state.user, st.session_state.queue_index, next_phone, active_call_index=st.session_state.active_call_index)
                            load_student_by_phone(next_phone)
                        else:
                            save_spoc_progress(st.session_state.user, st.session_state.queue_index, "", active_call_index=st.session_state.active_call_index)
                            st.session_state.form_initials = DEFAULT_FORM.copy()
                            st.session_state.form_version += 1
                            if len(st.session_state.allocated_numbers) > 0:
                                st.balloons()
                            
                    time.sleep(0.4)
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error appending row to Google Sheets: {ex}")

    st.markdown('</div>', unsafe_allow_html=True)

    # ==========================================================================
    # 📋 SECTION: SPOC WISE LATEST 5 CALLS WITH QUEUE NUMBER (Z-A)
    # ==========================================================================
    st.markdown("""
        <div class="section-card" style="margin-top: 1.2rem; border-top: 4px solid #1a73e8;">
    """, unsafe_allow_html=True)

    all_master_rows = fetch_master_data()
    current_spoc_clean = st.session_state.user.strip().lower()

    # Filter rows for currently logged-in SPOC
    spoc_records = []
    if len(all_master_rows) > 1:
        for r_i, r_data in enumerate(all_master_rows[1:], start=2): # 1-based Google Sheet row index
            if len(r_data) > 0 and str(r_data[0]).strip().lower() == current_spoc_clean:
                spoc_records.append((r_i, r_data))

    # Z-A: Newest / latest call first (reverse order)
    latest_5_calls = list(reversed(spoc_records))[:5]

    col_h1, col_h2 = st.columns([3.5, 1.5])
    with col_h1:
        st.markdown(f'<div class="form-title">📋 SPOC Calling History: Latest 5 Calls (Z-A / Newest First) — {st.session_state.user}</div>', unsafe_allow_html=True)
    with col_h2:
        st.markdown(f"<div style='text-align: right; color: #64748b; font-size: 0.9rem; font-weight: 600; padding-top: 4px;'>Showing newest <b>{len(latest_5_calls)}</b> of <b>{len(spoc_records)}</b> verified</div>", unsafe_allow_html=True)

    if not latest_5_calls:
        st.info(f"💡 No verified calls submitted yet for {st.session_state.user}. When you submit verifications, your latest 5 calls with their Queue Numbers will appear here.")
    else:
        for idx_call, (sheet_row_num, row_data) in enumerate(latest_5_calls):
            c_student_name = row_data[2].strip() if len(row_data) > 2 else "N/A"
            c_cmis = row_data[3].strip() if len(row_data) > 3 else "N/A"
            c_phone = row_data[4].strip() if len(row_data) > 4 else "N/A"
            c_contactable = row_data[14].strip() if len(row_data) > 14 else "N/A"
            c_remarks = row_data[15].strip() if len(row_data) > 15 else "N/A"
            c_vdate = row_data[24].strip() if len(row_data) > 24 else ""
            c_notes = row_data[25].strip() if len(row_data) > 25 else ""
            
            # Determine Queue Number by matching phone with allocated_numbers
            c_clean_phone = clean_phone(c_phone)
            q_num_str = "N/A"
            if c_clean_phone and st.session_state.allocated_numbers:
                for q_idx, a_phone in enumerate(st.session_state.allocated_numbers):
                    if clean_phone(a_phone) == c_clean_phone:
                        q_num_str = f"#{q_idx + 1}"
                        break
            
            # Color badge for call outcome
            if "Connected" in c_remarks:
                rem_badge_style = "background: #e6f4ea; color: #137333; border: 1px solid #ceead6;"
            elif any(k in c_remarks for k in ["Ringing", "Call Back"]):
                rem_badge_style = "background: #fef7e0; color: #b06000; border: 1px solid #feefc3;"
            else:
                rem_badge_style = "background: #fce8e6; color: #c5221f; border: 1px solid #fad2cf;"
            
            c_col1, c_col2, c_col3, c_col4, c_col5 = st.columns([1.1, 2.3, 1.6, 2.3, 1.2])
            with c_col1:
                st.markdown(f"""
                <div style="background: #e8f0fe; border-left: 4px solid #1a73e8; padding: 6px 10px; border-radius: 6px;">
                    <span style="font-size: 0.72rem; color: #5f6368; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">Queue No</span><br>
                    <strong style="color: #1a73e8; font-size: 1.1rem;">{q_num_str}</strong>
                </div>
                """, unsafe_allow_html=True)
            with c_col2:
                st.markdown(f"**{c_student_name}**<br><span style='color: #64748b; font-size: 0.83rem;'>CMIS: {c_cmis}</span>", unsafe_allow_html=True)
            with c_col3:
                st.markdown(f"📞 `{c_phone}`<br><span style='color: #64748b; font-size: 0.82rem;'>📅 {c_vdate}</span>", unsafe_allow_html=True)
            with c_col4:
                notes_snippet = f" | {c_notes[:35]}..." if c_notes else ""
                st.markdown(f"""
                <span style="display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.83rem; font-weight: 700; {rem_badge_style}">
                    {c_remarks}
                </span><br>
                <span style='color: #64748b; font-size: 0.82rem;'>Contactable: {c_contactable}{notes_snippet}</span>
                """, unsafe_allow_html=True)
            with c_col5:
                if st.button("✏️ Load / Edit", key=f"btn_hist_{sheet_row_num}_{idx_call}", use_container_width=True, help="Load this student record in Update Mode"):
                    found, src = load_student_by_phone(c_phone)
                    st.session_state.existing_master_row = sheet_row_num
                    st.toast(f"Loaded {c_student_name} (Queue {q_num_str}) in Update Mode (Row #{sheet_row_num})!", icon="📝")
                    st.rerun()
            
            if idx_call < len(latest_5_calls) - 1:
                st.markdown("<hr style='margin: 8px 0; border: none; border-top: 1px solid #f1f5f9;'>", unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="footer">© 2026 Anudip Foundation for Social Welfare | High Speed Verification System v4.0</div>', unsafe_allow_html=True)