import streamlit as st
import streamlit.components.v1 as components
from datetime import date, datetime
import json
import os
import re
import time
import urllib.parse
import csv
import io
import warnings
import threading
from concurrent.futures import ThreadPoolExecutor

# Suppress Streamlit deprecation warnings for clean console logs (resolves Picture 3 issue)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*st\\.components\\.v1\\.html.*")
warnings.filterwarnings("ignore", message=".*st\\.iframe.*")

PROGRESS_ENROLLMENT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spoc_enrollment_progress.json")
LOCAL_ENROLLMENT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "enrollment_data.csv")
LOCAL_ENROLLMENT_EXCEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Enrollment_Verification.xlsx")
DATA_CACHE_TTL = 900  # 15 minutes TTL for zero API rate limit and lightning speed

# High-Speed Background Sync Executor & File Safety Lock
_CSV_FILE_LOCK = threading.Lock()
_ENROLLMENT_BG_EXECUTOR = ThreadPoolExecutor(max_workers=3, thread_name_prefix="enr_sync")

# ==============================================================================
# 🎯 DROPDOWN CONSTANTS (MATCHING ENROLLMENT EXCEL & SUPPORT SHEET)
# ==============================================================================

# Support Sheet / Column 37 (Enroll Remarks) Options for Uncontactable
ENROLLMENT_UNABLE_TO_TRACK_OPTIONS = [
    "Did not respond to our call",
    "Network Issue",
    "Not a student of Anudip",
    "Language issue",
    "Switched off",
    "Wrong Number",
    "Incoming Call Is Not Available",
    "Left The Course",
    "Cource Complete",
    "Confirmed Name & Disconnected.",
    "Disconnected,Did'nt Share All Information."
]

# Educational List from Column 42 of Enrollment Excel
ENROLLMENT_EDUCATION_OPTIONS = [
    " ",
    "12 Pass",
    "Graduate",
    "Below 10 Pass",
    "10 Pass",
    "1st Yr",
    "2nd Yr",
    "3rd Yr",
    "Final Yr",
    "Under Graduate Diploma",
    "Post Graduate Diploma",
    "ITI",
    "ITI Pursuing",
    "Post Graduate",
    "Post Graduate Pursuing"
]

# Column 41: Why They Joined Course If Stu Working
ENROLLMENT_WHY_JOINED_OPTIONS = [
    "For better Job opportunity",
    "For skill development and job opportunity",
    "Interested in IT-jobs",
    "Skill Develoment",
    "Don’t wont to share",
    "Other"
]

ENROLLMENT_QUALITY_OPTIONS = [
    "Excellent",
    "Very Good",
    "Good",
    "Average",
    "Poor",
    " "
]

ENROLLMENT_CLASSES_WEEK_OPTIONS = [
    "#NA",
    "1 Day",
    "2 Days",
    "3 Days",
    "4 Days",
    "5 Days",
    "6 Days",
    "Daily",
    "Online / Flexible"
]

ENROLLMENT_CLASS_MODE_OPTIONS = [
    "Online",
    "Offline",
    "Hybrid",
    "Dont Share"
]

ENROLLMENT_MONTHS_OPTIONS = [
    "#NA",
    "Less than 1 Month",
    "1 Month",
    "2 Months",
    "3 Months",
    "4 Months",
    "5 Months",
    "6 Months",
    "7-12 Months",
    "More than 12 months"
]

ENROLLMENT_TRI_STATE_OPTIONS = [
    "Yes",
    "No",
    "Don't Share"
]

# Dropdown list for Question 3: Got information about Anudip (matching picture & Excel column T)
ENROLLMENT_GOT_INFO_OPTIONS = [
    "Friend",
    "Neighbour",
    "Relative",
    "College",
    "Faculty",
    "Social Media",
    "Others..",
    "Don't want to share",
    " "
]

ENROLLMENT_SATISFIED_OPTIONS = [
    "Yes",
    "No",
    "Average",
    "Don't Want To Share"
]

ENROLLMENT_CONTACTED_BLANK_REMARKS = {
    "Confirmed Name & Disconnected.",
    "Not a student of Anudip",
    "Language issue"
}

ENROLLMENT_QUICK_CONTACTED_OPTIONS = [
    "Full Verification (Complete Survey)",
    "Confirmed Name & Disconnected.",
    "Not a student of Anudip",
    "Language issue"
]

ENROLLMENT_REMARKS_YES_OPTIONS = [
    "Successfully Verified / All Details Confirmed",
    "Enrolled & Attending Regular Classes",
    "Interested in Placement",
    "Course In Progress",
    "Left The Course",
    "Cource Complete",
    "Confirmed Name & Disconnected.",
    "Not a student of Anudip",
    "Language issue",
    "Disconnected,Did'nt Share All Information."
]

# Master 43 Headers
ENROLLMENT_HEADERS = [
    "Called By", "Batch Code", "Course Name", "Start Date", "Student Code",
    "Student Name", "DOB", "Gender", "Mobile No.", "Alt Mobile No",
    "Center Code", "State", "Come To Know", "Referral Person Name",
    "Education Qualification", "Funder Name", "Enrollment Status",
    # Yellow Marked Verification Columns (18 to 41 / R to AO)
    "Contactable", "Class started (Yes/No)", "Got information about Anudip",
    "Referral Person Name(Yes/No)", "Please fill the Name", "Your_DOB", "Monthly Family Income RS.",
    "Satisfied With Conversation", "Classes In A Week", "Class Mode", "Quality Of Classes",
    "Current Educational Status", "Verification Date", "Interest In Job",
    "Present Working Status", "COMPANY NAME", "Salary", "Part Time /Full Time",
    "How Many Months Working", "Did They Left The Job After Joining Course",
    "Why They Joined Course, If Stu Working", "Enroll Remarks", "Remarks 2", "Remarks 3",
    # Call tracking columns (42 to 43 / AP to AQ)
    "Call_Status", "Call_id"
]

# ==============================================================================
# 🛠️ HELPER FUNCTIONS
# ==============================================================================
def clean_phone(phone_val) -> str:
    if not phone_val:
        return ""
    digits = re.sub(r"\D", "", str(phone_val).strip())
    return digits[-10:] if len(digits) >= 10 else digits

def parse_date_safe(d_val):
    if not d_val:
        return None
    if isinstance(d_val, (date, datetime)):
        return d_val if isinstance(d_val, date) else d_val.date()
    d_str = str(d_val).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(d_str[:10], fmt).date()
        except Exception:
            pass
    return None

def normalize_tri_val(val, default="Yes"):
    if val is None:
        return default
    v = str(val).strip()
    if not v:
        return default
    if any(k in v.upper() for k in ["DONT", "DON'T", "DIDNT", "DIDN'T", "REFUSE", "SHARE"]):
        return "Don't Share"
    if v.upper() == "NO":
        return "No"
    if v.upper() == "YES":
        return "Yes"
    return default

def get_tri_option_index(val, default="Yes"):
    norm = normalize_tri_val(val, default)
    if norm == "Don't Share":
        return 2
    if norm == "No":
        return 1
    return 0

def get_enrollment_highest_verified_index(student_list):
    """
    Returns index of the highest student row in student_list that has already been verified.
    """
    if not student_list:
        return -1
    highest = -1
    for idx, s in enumerate(student_list):
        cont = str(s.get("contactable", "")).strip().lower()
        if cont in ["yes", "no"]:
            highest = idx
    return highest

def update_in_memory_enrollment_row(row_num, payload, call_status="Done", call_id="3300"):
    """
    Updates the active in-memory master rows in session state immediately.
    Guarantees instantaneous UI re-render without hitting Google Sheets API.
    """
    try:
        if "enrollment_master_rows" in st.session_state and st.session_state.enrollment_master_rows:
            m_rows = st.session_state.enrollment_master_rows
            if 0 < row_num <= len(m_rows):
                idx = row_num - 1
                curr = list(m_rows[idx])
                if len(curr) < 43:
                    curr.extend([""] * (43 - len(curr)))
                if payload:
                    for i, val in enumerate(payload):
                        curr[17 + i] = str(val)
                curr[41] = call_status
                curr[42] = call_id
                m_rows[idx] = curr
                st.session_state.enrollment_master_rows = m_rows

        if "custom_enrollment_rows" in st.session_state and st.session_state.custom_enrollment_rows:
            crows = st.session_state.custom_enrollment_rows
            if 0 < row_num <= len(crows):
                idx = row_num - 1
                curr = list(crows[idx])
                if len(curr) < 43:
                    curr.extend([""] * (43 - len(curr)))
                if payload:
                    for i, val in enumerate(payload):
                        curr[17 + i] = str(val)
                curr[41] = call_status
                curr[42] = call_id
                crows[idx] = curr
                st.session_state.custom_enrollment_rows = crows
    except Exception:
        pass

def update_local_enrollment_row(row_num, payload, call_status="Done", call_id="3300"):
    """Updates local CSV and session cache for zero data loss."""
    try:
        with _CSV_FILE_LOCK:
            if os.path.exists(LOCAL_ENROLLMENT_CSV):
                with open(LOCAL_ENROLLMENT_CSV, "r", encoding="utf-8") as f:
                    rows = list(csv.reader(f))
                if 0 < row_num <= len(rows):
                    idx = row_num - 1
                    curr = list(rows[idx])
                    if len(curr) < 43:
                        curr.extend([""] * (43 - len(curr)))
                    if payload:
                        for i, val in enumerate(payload):
                            curr[17 + i] = str(val)
                    curr[41] = call_status
                    curr[42] = call_id
                    rows[idx] = curr
                    with open(LOCAL_ENROLLMENT_CSV, "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerows(rows)
    except Exception:
        pass

def batch_update_local_enrollment_rows(updates_map):
    """
    updates_map: dict of {row_num: (payload, call_status, call_id)}
    Updates local CSV in a single pass for lightning-fast disk I/O.
    """
    if not updates_map:
        return
    try:
        with _CSV_FILE_LOCK:
            if os.path.exists(LOCAL_ENROLLMENT_CSV):
                with open(LOCAL_ENROLLMENT_CSV, "r", encoding="utf-8") as f:
                    rows = list(csv.reader(f))
                for row_num, (payload, call_status, call_id) in updates_map.items():
                    if 0 < row_num <= len(rows):
                        idx = row_num - 1
                        curr = list(rows[idx])
                        if len(curr) < 43:
                            curr.extend([""] * (43 - len(curr)))
                        if payload and len(payload) > 0:
                            for i, val in enumerate(payload):
                                curr[17 + i] = str(val)
                        if call_status is not None:
                            curr[41] = str(call_status)
                        if call_id is not None:
                            curr[42] = str(call_id)
                        rows[idx] = curr
                with open(LOCAL_ENROLLMENT_CSV, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerows(rows)
    except Exception:
        pass

def batch_update_in_memory_enrollment_rows(updates_map):
    """
    updates_map: dict of {row_num: (payload, call_status, call_id)}
    Updates in-memory session rows in a single microsecond pass.
    """
    if not updates_map:
        return
    try:
        for key in ["enrollment_master_rows", "custom_enrollment_rows"]:
            if key in st.session_state and st.session_state[key]:
                m_rows = st.session_state[key]
                for row_num, (payload, call_status, call_id) in updates_map.items():
                    if 0 < row_num <= len(m_rows):
                        idx = row_num - 1
                        curr = list(m_rows[idx])
                        if len(curr) < 43:
                            curr.extend([""] * (43 - len(curr)))
                        if payload and len(payload) > 0:
                            for i, val in enumerate(payload):
                                curr[17 + i] = str(val)
                        if call_status is not None:
                            curr[41] = str(call_status)
                        if call_id is not None:
                            curr[42] = str(call_id)
                        m_rows[idx] = curr
                st.session_state[key] = m_rows
    except Exception:
        pass

def _bg_sync_worker(ws, row_num, payload, call_status="Done", call_id="3300"):
    """
    Background worker: Syncs row to local CSV and Google Sheets with retry.
    Never blocks UI interaction.
    """
    # 1. Update local CSV immediately so disk backup is safe
    try:
        update_local_enrollment_row(row_num, payload, call_status, call_id)
    except Exception:
        pass

    # 2. Update Google Sheets in background with retry
    if ws:
        for attempt in range(1, 4):
            try:
                # 24 verification columns R:AO
                if payload and len(payload) > 0:
                    ws.update(values=[payload], range_name=f"R{row_num}:AO{row_num}")
                # Separate update for AP:AQ (Call_Status, Call_id)
                try:
                    if ws.col_count >= 43:
                        ws.update(values=[[call_status, call_id]], range_name=f"AP{row_num}:AQ{row_num}")
                except Exception:
                    pass
                break
            except Exception:
                if attempt < 3:
                    time.sleep(1.0)

def dispatch_enrollment_sync(ws, row_num, payload, call_status="Done", call_id="3300"):
    """Dispatches background sync for zero UI delay."""
    _ENROLLMENT_BG_EXECUTOR.submit(_bg_sync_worker, ws, row_num, list(payload), call_status, call_id)

# ==============================================================================
# 💾 PERSISTENCE & QUEUE PROGRESS FOR ENROLLMENT
# ==============================================================================
def load_all_enrollment_progress():
    if os.path.exists(PROGRESS_ENROLLMENT_FILE):
        try:
            with open(PROGRESS_ENROLLMENT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_enrollment_progress(spoc_name, queue_index, phone="", active_call_index=None):
    if not spoc_name:
        return
    try:
        data = load_all_enrollment_progress()
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
        with open(PROGRESS_ENROLLMENT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def get_saved_enrollment_index(spoc_name, student_list):
    """
    Smart auto-resume for Enrollment SPOC: resumes at the first uncalled fresh student.
    """
    if not spoc_name or not student_list:
        return 0, 0
    data = load_all_enrollment_progress()
    saved = data.get(spoc_name.strip().lower(), {})
    saved_active = saved.get("active_call_index", saved.get("queue_index", 0))
    if not isinstance(saved_active, int) or saved_active < 0 or saved_active >= len(student_list):
        saved_active = 0

    highest_verified = get_enrollment_highest_verified_index(student_list)
    if highest_verified >= 0 and (highest_verified + 1) < len(student_list):
        effective_active = max(saved_active, highest_verified + 1)
    else:
        effective_active = saved_active

    saved_phone = clean_phone(saved.get("phone", ""))
    if saved_phone:
        for idx, item in enumerate(student_list):
            if clean_phone(item.get("contact_number", "")) == saved_phone:
                return idx, max(idx, effective_active)

    saved_idx = saved.get("queue_index", 0)
    if highest_verified >= 0 and (highest_verified + 1) < len(student_list):
        if saved_idx <= highest_verified:
            target_idx = highest_verified + 1
        else:
            target_idx = saved_idx
    elif isinstance(saved_idx, int) and 0 <= saved_idx < len(student_list):
        target_idx = saved_idx
    else:
        target_idx = min(len(student_list) - 1, effective_active)

    return target_idx, max(target_idx, effective_active)

# ==============================================================================
# 📥 DATA FETCHING & MODELING (GOOGLE SHEETS + FALLBACK LOCAL CSV/EXCEL)
# ==============================================================================
def load_excel_enrollment_rows(file_path):
    try:
        import openpyxl
        wb = openpyxl.load_workbook(file_path, data_only=True)
        ws_active = wb["Enrollment_Verification"] if "Enrollment_Verification" in wb.sheetnames else wb.active
        rows = []
        for r in ws_active.iter_rows(values_only=True):
            if any(r):
                row_41 = [str(c) if c is not None else "" for c in r[:41]]
                if len(row_41) < 41:
                    row_41.extend([""] * (41 - len(row_41)))
                rows.append(row_41)
        if len(rows) > 1 and any(len(r) > 0 and str(r[0]).strip() for r in rows[1:]):
            return rows
    except Exception:
        pass
    return []

def load_csv_enrollment_rows(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
        if len(rows) > 1 and any(len(r) > 0 and str(r[0]).strip() for r in rows[1:]):
            return rows
    except Exception:
        pass
    return []

@st.cache_data(ttl=DATA_CACHE_TTL)
def fetch_enrollment_master_data(_enrollment_ws):
    """
    Fetches all rows from Google Sheet 'enrollment_Verification' (15-min cache).
    Falls back to session upload, local Enrollment_Verification.xlsx, or enrollment_data.csv.
    """
    # 1. Try Google Sheets
    if _enrollment_ws:
        try:
            rows = _enrollment_ws.get_all_values()
            if rows and len(rows) > 1 and any(len(r) > 0 and str(r[0]).strip() for r in rows[1:]):
                return rows
        except Exception:
            pass

    # 2. Try session state custom upload
    if "custom_enrollment_rows" in st.session_state and st.session_state.custom_enrollment_rows:
        c_rows = st.session_state.custom_enrollment_rows
        if len(c_rows) > 1 and any(len(r) > 0 and str(r[0]).strip() for r in c_rows[1:]):
            return c_rows

    # 3. Try local Excel (Enrollment_Verification.xlsx)
    if os.path.exists(LOCAL_ENROLLMENT_EXCEL):
        rows = load_excel_enrollment_rows(LOCAL_ENROLLMENT_EXCEL)
        if rows:
            return rows

    # 4. Try local CSV fallback (enrollment_data.csv)
    if os.path.exists(LOCAL_ENROLLMENT_CSV):
        rows = load_csv_enrollment_rows(LOCAL_ENROLLMENT_CSV)
        if rows:
            return rows

    # 5. Check parent directory fallbacks
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p_excel = os.path.join(parent_dir, "Enrollment_Verification.xlsx")
    if os.path.exists(p_excel):
        rows = load_excel_enrollment_rows(p_excel)
        if rows:
            return rows

    p_csv = os.path.join(parent_dir, "enrollment_data.csv")
    if os.path.exists(p_csv):
        rows = load_csv_enrollment_rows(p_csv)
        if rows:
            return rows

    return []

def parse_all_enrollment_students(all_rows):
    """
    Parses all student rows from the Enrollment Sheet.
    Matches the 43-column layout (Columns 1-17 Static, Columns 18-41 Yellow Marked, Columns 42-43 Call_Status & Call_id).
    """
    if not all_rows or len(all_rows) <= 1:
        return []
    students = []
    q_idx = 0
    for r_idx, r in enumerate(all_rows[1:], start=2):
        if not any(r):
            continue
        assigned_spoc = str(r[0]).strip() if len(r) > 0 else ""
        has_content = bool(assigned_spoc) or (len(r) > 4 and bool(str(r[4]).strip())) or (len(r) > 5 and bool(str(r[5]).strip()))
        if has_content:
            if not assigned_spoc:
                assigned_spoc = "Unassigned"
            padded = list(r) + [""] * max(0, 43 - len(r))
            raw_cont = padded[17].strip()
            raw_vdate = padded[29].strip()
            call_status = padded[41].strip() if len(padded) > 41 and padded[41].strip() else ("Done" if (raw_cont.lower() in ["yes", "no"] or raw_vdate) else "Progress")
            call_id = padded[42].strip() if len(padded) > 42 and padded[42].strip() else ("3300" if r_idx <= 3301 else "3300_Update")

            students.append({
                "row_num": r_idx,
                "queue_index": q_idx,
                "called_by": assigned_spoc,
                "batch_code": padded[1].strip(),
                "course_name": padded[2].strip(),
                "start_date": padded[3].strip(),
                "student_code": padded[4].strip(),
                "student_name": padded[5].strip(),
                "dob": padded[6].strip(),
                "gender": padded[7].strip(),
                "contact_number": padded[8].strip(),
                "alt_contact_number": padded[9].strip(),
                "centre_code": padded[10].strip(),
                "state": padded[11].strip(),
                "come_to_know": padded[12].strip(),
                "referral_person_name": padded[13].strip(),
                "education_qualification": padded[14].strip(),
                "funder_name": padded[15].strip(),
                "enrollment_status": padded[16].strip(),
                # Yellow Marked Verified columns (18 to 41 / R to AO)
                "contactable": raw_cont,
                "class_started": padded[18].strip(),
                "got_info_anudip": padded[19].strip(),
                "referral_person_ok": padded[20].strip(),
                "referral_name_fill": padded[21].strip(),
                "your_dob": padded[22].strip(),
                "monthly_income": padded[23].strip(),
                "satisfied_conversation": padded[24].strip(),
                "classes_in_week": padded[25].strip(),
                "class_mode": padded[26].strip(),
                "quality_of_classes": padded[27].strip(),
                "current_edu_status": padded[28].strip(),
                "verification_date": raw_vdate,
                "interest_in_job": padded[30].strip(),
                "present_working_status": padded[31].strip(),
                "company_name": padded[32].strip(),
                "salary": padded[33].strip(),
                "part_full_time": padded[34].strip(),
                "how_many_months": padded[35].strip(),
                "left_job_after_joining": padded[36].strip(),
                "why_joined_course": padded[37].strip(),
                "enroll_remarks": padded[38].strip(),
                "remarks_2": padded[39].strip(),
                "remarks_3": padded[40].strip() if len(padded) > 40 else "",
                # Call tracking columns (42 to 43 / AP to AQ)
                "call_status": call_status,
                "call_id": call_id
            })
            q_idx += 1
    return students

def get_enrollment_students_for_spoc(all_rows, spoc_name):
    """
    Filters and returns structured enrollment student records for the specified SPOC.
    Admin users can access all records.
    """
    if len(all_rows) <= 1:
        return []

    spoc_clean = (spoc_name or "").strip().lower()
    ADMIN_USERS = {"nibedan", "pritam", "kalpana", "koushik"}
    is_admin = spoc_clean in ADMIN_USERS

    all_students = parse_all_enrollment_students(all_rows)
    if is_admin:
        return all_students

    spoc_students = [s for s in all_students if s["called_by"].strip().lower() == spoc_clean]
    for i, s in enumerate(spoc_students):
        s["queue_index"] = i
    return spoc_students

# ==============================================================================
# 📊 REAL-TIME STATS & QUEUES
# ==============================================================================
def compute_enrollment_stats(students, live_history=None):
    if live_history is None:
        live_history = []
    live_map = {}
    for r_num, row_data in live_history:
        if len(row_data) > 0:
            live_map[r_num] = row_data[0].strip().lower()

    total_assigned = len(students)
    yes_cnt, no_cnt = 0, 0
    fresh_list = []
    no_list = []

    for s in students:
        r_num = s["row_num"]
        cont = live_map.get(r_num, s["contactable"].strip().lower())
        if cont == "yes":
            yes_cnt += 1
        elif cont == "no":
            no_cnt += 1
            no_list.append(s)
        else:
            fresh_list.append(s)

    total_called = yes_cnt + no_cnt
    fresh_pending = len(fresh_list)
    contactable_pct = (yes_cnt / total_called * 100.0) if total_called > 0 else 0.0

    just_nums_text = "\n".join([clean_phone(s["contact_number"]) for s in fresh_list if clean_phone(s["contact_number"])])

    return {
        "total_assigned": total_assigned,
        "total_called": total_called,
        "yes_count": yes_cnt,
        "no_count": no_cnt,
        "fresh_pending": fresh_pending,
        "contactable_pct": contactable_pct,
        "fresh_list": fresh_list,
        "no_list": no_list,
        "just_numbers_text": just_nums_text
    }

# ==============================================================================
# 📋 FRESH CALL LIST UI COMPONENT
# ==============================================================================
def render_enrollment_fresh_call_list(fresh_stats, current_spoc):
    f_spoc = current_spoc.title()
    v_pending = fresh_stats["fresh_pending"]
    v_assigned = fresh_stats["total_assigned"]
    v_called = fresh_stats["total_called"]
    v_yes = fresh_stats["yes_count"]
    v_no = fresh_stats["no_count"]
    just_nums_text = fresh_stats["just_numbers_text"]
    fresh_items = fresh_stats["fresh_list"]

    st.markdown(f"""
        <div style="background: linear-gradient(135deg, #f0fdf4 0%, #ffffff 100%); border: 1.5px solid #86efac; border-left: 5px solid #16a34a; border-radius: 8px; padding: 10px 14px; margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                <span style="font-weight: 800; color: #166534; font-size: 1.05rem;">📋 Fresh Calling Queue: {f_spoc}</span>
                <span style="background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; padding: 2px 8px; border-radius: 12px; font-weight: 700; font-size: 0.82rem;">{v_pending} Pending</span>
            </div>
            <div style="margin-top: 6px; font-size: 0.82rem; color: #374151;">
                📊 <b>Formula:</b> Total Assigned ({v_assigned}) − Called ({v_called}) [Yes: {v_yes} + No: {v_no}] = <b style="color: #15803d;">{v_pending} Fresh Pending</b>
            </div>
        </div>
    """, unsafe_allow_html=True)

    if v_pending == 0:
        st.success(f"🎉 Outstanding work! All {v_assigned} assigned enrollment calls for {f_spoc} have been completed.")
        return

    tab_nums, tab_queue = st.tabs(["🔢 Just Numbers (Raw List)", "📋 Interactive Call List"])

    with tab_nums:
        st.caption(f"📲 Pending uncalled phone numbers ({v_pending} remaining). Copy or download below:")
        st.text_area(
            "Just Numbers",
            value=just_nums_text,
            height=160,
            key=f"enr_ta_just_nums_{f_spoc}",
            help="Click inside and press Ctrl+A / Ctrl+C to copy all pending numbers directly into your dialer."
        )

        c_dl1, c_dl2 = st.columns(2)
        with c_dl1:
            st.download_button(
                label=f"📥 Download Just Numbers ({v_pending})",
                data=just_nums_text,
                file_name=f"Enrollment_Pending_Numbers_{f_spoc}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                mime="text/plain",
                use_container_width=True,
                key=f"enr_dl_just_nums_{f_spoc}"
            )
        with c_dl2:
            st.info("💡 Tip: Use your auto-dialer or mobile softphone with this list.")

    with tab_queue:
        st.caption("Click **Jump** next to any student to dial immediately (showing top 40):")
        preview_rows = fresh_items[:40]
        for s in preview_rows:
            cq_col1, cq_col2, cq_col3, cq_col4 = st.columns([0.8, 2.5, 2.2, 1.0])
            with cq_col1:
                st.markdown(f"<b>#{s['queue_index'] + 1}</b>", unsafe_allow_html=True)
            with cq_col2:
                st.markdown(f"<b>{s['student_name']}</b><br><small style='color: #64748b;'>{s['course_name']}</small>", unsafe_allow_html=True)
            with cq_col3:
                p_c = clean_phone(s['contact_number'])
                st.markdown(f"<a href='tel:{p_c}' style='color: #1a73e8; font-weight: 700; text-decoration: none;'>📞 {p_c}</a>", unsafe_allow_html=True)
            with cq_col4:
                if st.button("Jump 🎯", key=f"enr_jump_fresh_{s['row_num']}", use_container_width=True):
                    st.session_state.enrollment_queue_index = s["queue_index"]
                    save_enrollment_progress(current_spoc, s["queue_index"], s["contact_number"], active_call_index=st.session_state.get("enrollment_active_call_index", 0))
                    st.rerun()

# ==============================================================================
# 🚫 UNCONTACTABLE / NO LIST UI COMPONENT
# ==============================================================================
def render_enrollment_not_contactable_list(fresh_stats, current_spoc):
    f_spoc = current_spoc.title()
    no_items = fresh_stats["no_list"]
    no_cnt = len(no_items)

    st.markdown(f"""
        <div style="background: linear-gradient(135deg, #fff7ed 0%, #ffffff 100%); border: 1.5px solid #fed7aa; border-left: 5px solid #ea580c; border-radius: 8px; padding: 10px 14px; margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                <span style="font-weight: 800; color: #9a3412; font-size: 1.05rem;">🚫 Uncontactable ('No') Targets: {f_spoc}</span>
                <span style="background: #ffedd5; color: #c2410c; border: 1px solid #fed7aa; padding: 2px 8px; border-radius: 12px; font-weight: 700; font-size: 0.82rem;">{no_cnt} Unreached</span>
            </div>
            <div style="margin-top: 6px; font-size: 0.82rem; color: #4b5563;">
                Students previously logged as Not Contactable (Switched Off, Ringing, Wrong Number, etc.) for redial.
            </div>
        </div>
    """, unsafe_allow_html=True)

    if no_cnt == 0:
        st.info("No uncontactable records for this SPOC.")
        return

    no_nums_text = "\n".join([clean_phone(s["contact_number"]) for s in no_items if clean_phone(s["contact_number"])])

    t_raw, t_call = st.tabs(["🔢 Uncontactable Numbers", "🔄 Redial Queue"])
    with t_raw:
        st.text_area(
            "Uncontactable Numbers",
            value=no_nums_text,
            height=140,
            key=f"enr_ta_no_nums_{f_spoc}"
        )
        st.download_button(
            label=f"📥 Download Uncontactable Numbers ({no_cnt})",
            data=no_nums_text,
            file_name=f"Enrollment_Uncontactable_Numbers_{f_spoc}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
            mime="text/plain",
            use_container_width=True,
            key=f"enr_dl_no_nums_{f_spoc}"
        )

    with t_call:
        st.caption("Showing top 40 unreached targets for redial:")
        for s in no_items[:40]:
            cq1, cq2, cq3, cq4 = st.columns([0.8, 2.5, 2.2, 1.0])
            with cq1:
                st.markdown(f"<b>#{s['queue_index'] + 1}</b>", unsafe_allow_html=True)
            with cq2:
                reason = s.get("enroll_remarks", "") or "Not Contactable"
                st.markdown(f"<b>{s['student_name']}</b><br><small style='color: #dc2626;'>{reason}</small>", unsafe_allow_html=True)
            with cq3:
                p_c = clean_phone(s['contact_number'])
                st.markdown(f"<a href='tel:{p_c}' style='color: #1a73e8; font-weight: 700; text-decoration: none;'>📞 {p_c}</a>", unsafe_allow_html=True)
            with cq4:
                if st.button("Retry 🔄", key=f"enr_retry_no_{s['row_num']}", use_container_width=True):
                    st.session_state.enrollment_queue_index = s["queue_index"]
                    st.session_state.enrollment_editing_row = s["row_num"]
                    save_enrollment_progress(current_spoc, s["queue_index"], s["contact_number"], active_call_index=st.session_state.get("enrollment_active_call_index", 0))
                    st.rerun()

# ==============================================================================
# 📥 SIDEBAR REPORT DOWNLOAD & EXCEL UPLOADER
# ==============================================================================
def build_enrollment_csv(students_subset, live_history=None, headers=None):
    if headers is None:
        headers = list(ENROLLMENT_HEADERS)
    else:
        headers = list(headers)

    if "Call_Status" not in headers:
        headers.append("Call_Status")
    if "Call_id" not in headers:
        headers.append("Call_id")

    if live_history is None:
        live_history = []
    live_map = {}
    for item in live_history:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            live_map[item[0]] = item[1]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)

    for s in students_subset:
        r_num = s.get("row_num")
        live_entry = live_map.get(r_num)
        if live_entry:
            pad_live = list(live_entry) + [""] * max(0, 24 - len(live_entry))
            cont = pad_live[0].strip()
            vdate = pad_live[12].strip()
            verif_cols = [
                pad_live[0], pad_live[1], pad_live[2], pad_live[3], pad_live[4],
                pad_live[5], pad_live[6], pad_live[7], pad_live[8], pad_live[9],
                pad_live[10], pad_live[11], pad_live[12], pad_live[13], pad_live[14],
                pad_live[15], pad_live[16], pad_live[17], pad_live[18], pad_live[19],
                pad_live[20], pad_live[21], pad_live[22], pad_live[23]
            ]
        else:
            cont = s.get("contactable", "").strip()
            vdate = s.get("verification_date", "").strip()
            verif_cols = [
                cont, s.get("class_started", ""), s.get("got_info_anudip", ""),
                s.get("referral_person_ok", ""), s.get("referral_name_fill", ""), s.get("your_dob", ""), s.get("monthly_income", ""),
                s.get("satisfied_conversation", ""), s.get("classes_in_week", ""), s.get("class_mode", ""), s.get("quality_of_classes", ""),
                s.get("current_edu_status", ""), vdate, s.get("interest_in_job", ""),
                s.get("present_working_status", ""), s.get("company_name", ""), s.get("salary", ""),
                s.get("part_full_time", ""), s.get("how_many_months", ""), s.get("left_job_after_joining", ""),
                s.get("why_joined_course", ""), s.get("enroll_remarks", ""), s.get("remarks_2", ""), s.get("remarks_3", "")
            ]

        is_done = (cont.lower() in ["yes", "no"]) or bool(vdate)
        row_status = "Done" if is_done else s.get("call_status", "Progress")
        row_call_id = s.get("call_id") or ("3300" if (r_num and r_num <= 3301) else "3300_Update")

        row = [
            s.get("called_by", ""), s.get("batch_code", ""), s.get("course_name", ""), s.get("start_date", ""),
            s.get("student_code", ""), s.get("student_name", ""), s.get("dob", ""), s.get("gender", ""),
            s.get("contact_number", ""), s.get("alt_contact_number", ""), s.get("centre_code", ""),
            s.get("state", ""), s.get("come_to_know", ""), s.get("referral_person_name", ""),
            s.get("education_qualification", ""), s.get("funder_name", ""), s.get("enrollment_status", "")
        ] + verif_cols + [row_status, row_call_id]

        writer.writerow(row)

    return "\ufeff" + output.getvalue()

def render_enrollment_sidebar_download(all_enrollment_students, current_spoc, is_admin=False, live_history=None, all_rows=None, enrollment_ws=None):
    if live_history is None:
        live_history = []

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📥 Enrollment Reports & Tools")

    # Optional Excel / CSV Upload Tool for Supervisors / SPOCs
    with st.sidebar.expander("📂 Upload New Enrollment Excel / CSV", expanded=False):
        uploaded_file = st.file_uploader(
            "Upload Excel (.xlsx) or CSV",
            type=["xlsx", "xls", "csv"],
            key="enr_excel_uploader",
            help="Upload an updated Enrollment verification file. The yellow-marked columns will be verified and saved."
        )
        if uploaded_file is not None:
            try:
                if uploaded_file.name.endswith(".csv"):
                    content = uploaded_file.getvalue().decode("utf-8", errors="ignore")
                    reader = csv.reader(io.StringIO(content))
                    new_rows = list(reader)
                else:
                    import openpyxl
                    wb = openpyxl.load_workbook(uploaded_file, data_only=True)
                    ws_active = wb["Enrollment_Verification"] if "Enrollment_Verification" in wb.sheetnames else wb.active
                    new_rows = []
                    for row in ws_active.iter_rows(values_only=True):
                        if any(row):
                            new_rows.append([str(c) if c is not None else "" for c in row[:43]])

                if new_rows and len(new_rows) > 1:
                    st.session_state.custom_enrollment_rows = new_rows
                    st.session_state.enrollment_master_rows = [list(r) for r in new_rows]
                    fetch_enrollment_master_data.clear()
                    st.success(f"✅ Loaded {len(new_rows)-1} students from uploaded file!")
                    if st.button("Apply & Refresh Queue", key="enr_apply_upload_btn", use_container_width=True):
                        st.rerun()
            except Exception as e:
                st.error(f"Error reading file: {e}")

    live_map = {}
    for item in live_history:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            live_map[item[0]] = item[1]

    all_spocs = sorted(list({s["called_by"].strip().title() for s in all_enrollment_students if s.get("called_by")}))

    if is_admin:
        sel_download_spoc = st.sidebar.selectbox(
            "Download Data For:",
            ["All Team Combined"] + all_spocs,
            index=0,
            key="enr_sb_download_spoc_sel"
        )
        if sel_download_spoc == "All Team Combined":
            target_students = all_enrollment_students
            safe_name = "All_Team"
        else:
            target_students = [s for s in all_enrollment_students if s["called_by"].strip().lower() == sel_download_spoc.strip().lower()]
            safe_name = sel_download_spoc.replace(" ", "_")
    else:
        target_students = [s for s in all_enrollment_students if s["called_by"].strip().lower() == current_spoc.strip().lower()]
        safe_name = current_spoc.title().replace(" ", "_")

    now_str = datetime.now().strftime("%Y%m%d_%H%M")

    # Dynamic Call ID Filter (Discovers all unique Call IDs from target_students: 3300, 3300_Update)
    found_cids = sorted(list({str(s.get("call_id", "")).strip() for s in target_students if str(s.get("call_id", "")).strip()}))
    for def_cid in ["3300", "3300_Update"]:
        if def_cid not in found_cids and any(str(s.get("call_id", "")).strip() == def_cid for s in all_enrollment_students):
            found_cids.append(def_cid)
    found_cids = sorted(found_cids)
    if not found_cids:
        found_cids = ["3300", "3300_Update"]
    call_id_opts = ["All Call IDs"] + found_cids
    sel_call_id = st.sidebar.selectbox("🏷️ Filter by Call ID:", call_id_opts, index=0, key=f"sb_enr_cid_{safe_name}")

    filtered_students = target_students
    if sel_call_id != "All Call IDs":
        filtered_students = [s for s in target_students if str(s.get("call_id", "")).strip() == sel_call_id]

    done_students = []
    progress_students = []
    yes_students = []
    no_students = []

    for s in filtered_students:
        r_num = s["row_num"]
        lp = live_map.get(r_num)
        cont = lp[0].strip().lower() if (lp and len(lp) > 0) else s.get("contactable", "").strip().lower()
        vdate = lp[12].strip() if (lp and len(lp) > 12) else s.get("verification_date", "").strip()
        is_done = (cont in ["yes", "no"]) or bool(vdate)

        if is_done:
            done_students.append(s)
            if cont == "yes":
                yes_students.append(s)
            else:
                no_students.append(s)
        else:
            progress_students.append(s)

    total_students = filtered_students
    done_cnt = len(done_students)
    prog_cnt = len(progress_students)
    yes_cnt = len(yes_students)
    no_cnt = len(no_students)
    total_cnt = len(total_students)

    sheet_headers = ENROLLMENT_HEADERS

    # Styled container matching the design
    st.sidebar.markdown(f"""
        <div style="background: #ffffff; border: 2.2px solid #22c55e; border-radius: 10px; padding: 12px 14px; margin-top: 10px; margin-bottom: 12px; box-shadow: 0 2px 10px rgba(34, 197, 94, 0.15);">
            <div style="font-weight: 800; color: #15803d; font-size: 0.96rem; text-align: center; text-transform: uppercase; letter-spacing: 0.5px;">
                📥 Enrollment Data Download ({safe_name})
            </div>
            <div style="display: flex; justify-content: space-around; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; padding: 6px 4px; font-size: 0.78rem; font-weight: 700; margin-top: 8px;">
                <span style="color: #15803d;">✅ Done: {done_cnt}</span>
                <span style="color: #ea580c;">⏳ Progress: {prog_cnt}</span>
                <span style="color: #1e40af;">📊 Total: {total_cnt}</span>
            </div>
            <div style="display: flex; justify-content: space-around; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px 4px; font-size: 0.76rem; font-weight: 600; margin-top: 4px;">
                <span style="color: #16a34a;">🟢 Yes: {yes_cnt}</span>
                <span style="color: #dc2626;">🔴 No: {no_cnt}</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # 🏁 High Speed One-Click Action to mark all filtered calls as Done
    if prog_cnt > 0 and len(filtered_students) > 0:
        btn_cid_label = f" ({sel_call_id})" if sel_call_id != "All Call IDs" else ""
        if st.sidebar.button(f"🏁 ALL CALLS DONE{btn_cid_label}", type="primary", key=f"sb_enr_all_done_{safe_name}_{sel_call_id}", use_container_width=True, help="Instantly marks all calls in this scope as 'Done' in Google Sheet"):
            updates_map = {}
            batch_updates = []
            for s in filtered_students:
                s["call_status"] = "Done"
                cid = s.get("call_id", "3300")
                updates_map[s["row_num"]] = ([], "Done", cid)
                batch_updates.append({
                    'range': f'AP{s["row_num"]}:AQ{s["row_num"]}',
                    'values': [['Done', cid]]
                })
            # 1. Instant sub-millisecond local update
            batch_update_in_memory_enrollment_rows(updates_map)
            batch_update_local_enrollment_rows(updates_map)
            # 2. Async background sync to Google Sheet (Zero UI wait)
            if enrollment_ws and batch_updates:
                _ENROLLMENT_BG_EXECUTOR.submit(enrollment_ws.batch_update, batch_updates)
            st.toast(f"🎉 All calls for {safe_name}{btn_cid_label} marked as 'Done' in Google Sheet!", icon="✅")
            time.sleep(0.2)
            st.rerun()

    # 1. Download 'Call Done' Data (Completed Calls)
    done_csv = build_enrollment_csv(done_students, live_history, headers=sheet_headers)
    st.sidebar.download_button(
        label=f"✅ Download 'Call Done' Data ({done_cnt})",
        data=done_csv,
        file_name=f"Enrollment_CallDone_Data_{safe_name}_{now_str}.csv",
        mime="text/csv",
        use_container_width=True,
        key=f"sb_dl_enr_done_{safe_name}"
    )

    # 2. Download 'In Progress' Data (For reassigning if SPOC left)
    prog_csv = build_enrollment_csv(progress_students, live_history, headers=sheet_headers)
    st.sidebar.download_button(
        label=f"⏳ Download 'In Progress' Data ({prog_cnt})",
        data=prog_csv,
        file_name=f"Enrollment_InProgress_Data_{safe_name}_{now_str}.csv",
        mime="text/csv",
        use_container_width=True,
        key=f"sb_dl_enr_prog_{safe_name}"
    )

    # 3. Yes Data Download Button
    yes_csv = build_enrollment_csv(yes_students, live_history, headers=sheet_headers)
    st.sidebar.download_button(
        label=f"🟢 Download 'Yes' Data ({yes_cnt})",
        data=yes_csv,
        file_name=f"Enrollment_Yes_Data_{safe_name}_{now_str}.csv",
        mime="text/csv",
        use_container_width=True,
        key=f"sb_dl_enr_yes_{safe_name}"
    )

    # 4. No Data Download Button
    no_csv = build_enrollment_csv(no_students, live_history, headers=sheet_headers)
    st.sidebar.download_button(
        label=f"🔴 Download 'No' Data ({no_cnt})",
        data=no_csv,
        file_name=f"Enrollment_No_Data_{safe_name}_{now_str}.csv",
        mime="text/csv",
        use_container_width=True,
        key=f"sb_dl_enr_no_{safe_name}"
    )

    # 5. Total Data Download Button
    total_csv = build_enrollment_csv(total_students, live_history, headers=sheet_headers)
    st.sidebar.download_button(
        label=f"📊 Download 'Total' Data ({total_cnt})",
        data=total_csv,
        file_name=f"Enrollment_Total_Data_{safe_name}_{now_str}.csv",
        mime="text/csv",
        use_container_width=True,
        key=f"sb_dl_enr_total_{safe_name}"
    )

# ==============================================================================
# 🚀 MAIN ENROLLMENT VERIFICATION DASHBOARD
# ==============================================================================
def render_enrollment_dashboard(enrollment_ws, current_spoc, is_admin=False):
    # Modern styling matching screenshot 2 & placement module
    st.markdown("""
        <style>
            .stButton > button {
                border-radius: 8px !important;
                font-weight: 700 !important;
                height: 3.0em !important;
                transition: all 0.15s ease-in-out !important;
                border: 1px solid #cbd5e1 !important;
                background-color: #ffffff !important;
                color: #1e293b !important;
            }
            .stButton > button:hover {
                transform: translateY(-1px) !important;
                box-shadow: 0 4px 12px rgba(0,0,0,0.08) !important;
                border-color: #94a3b8 !important;
                background-color: #f8fafc !important;
            }
            .stButton > button[kind="primary"] {
                background: #ff4b4b !important;
                color: #ffffff !important;
                border: none !important;
            }
            .profile-card-enhanced {
                background: #ffffff;
                border: 1.5px solid #e2e8f0;
                border-radius: 12px;
                padding: 16px 20px;
                margin-bottom: 14px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.03);
            }
            .profile-title-bar {
                display: flex;
                align-items: center;
                gap: 8px;
                font-weight: 800;
                color: #0f4c81;
                font-size: 1.18rem;
                margin-bottom: 14px;
            }
            .profile-label-styled {
                font-size: 0.78rem;
                color: #64748b;
                text-transform: uppercase;
                font-weight: 700;
                letter-spacing: 0.5px;
                margin-bottom: 2px;
            }
            .profile-val-styled {
                font-size: 1.02rem;
                font-weight: 700;
                color: #0f172a;
            }
            .question-pill-header {
                font-size: 0.94rem;
                font-weight: 800;
                color: #1e3a8a;
                margin-bottom: 6px;
                display: flex;
                align-items: center;
                gap: 6px;
            }
            .fresh-call-header-btn button {
                border: 1.5px solid #2e7d32 !important;
                background-color: #ffffff !important;
                color: #1b5e20 !important;
                font-weight: 700 !important;
            }
            .fresh-call-header-btn button:hover {
                background-color: #f0fdf4 !important;
                border-color: #1b5e20 !important;
            }
            .no-list-header-btn button {
                border: 1.5px solid #c2410c !important;
                background-color: #ffffff !important;
                color: #9a3412 !important;
                font-weight: 700 !important;
            }
            .no-list-header-btn button:hover {
                background-color: #fff7ed !important;
                border-color: #9a3412 !important;
            }
        </style>
    """, unsafe_allow_html=True)

    # Session State initializations
    if "enrollment_live_history" not in st.session_state:
        st.session_state.enrollment_live_history = []
    if "enrollment_queue_index" not in st.session_state:
        st.session_state.enrollment_queue_index = 0
    if "enrollment_active_call_index" not in st.session_state:
        st.session_state.enrollment_active_call_index = 0

    if "enrollment_master_rows" not in st.session_state or not st.session_state.enrollment_master_rows:
        raw_rows = fetch_enrollment_master_data(enrollment_ws)
        st.session_state.enrollment_master_rows = [list(r) for r in raw_rows] if raw_rows else []

    all_rows = st.session_state.enrollment_master_rows
    if not all_rows:
        st.error("⚠️ Could not load data from Google Sheet 'enrollment_Verification' or local data file. Please verify permissions or upload an Enrollment excel.")
        return

    all_enrollment_students = parse_all_enrollment_students(all_rows)
    if not all_enrollment_students:
        st.warning("No enrollment records found.")
        return

    all_spocs = sorted(list({s["called_by"].strip().title() for s in all_enrollment_students if s["called_by"]}))

    # Sidebar Downloads & File Uploader
    render_enrollment_sidebar_download(
        all_enrollment_students=all_enrollment_students,
        current_spoc=current_spoc,
        is_admin=is_admin,
        live_history=st.session_state.enrollment_live_history,
        all_rows=all_rows,
        enrollment_ws=enrollment_ws
    )

    # Top Brand Header Banner
    st.markdown("""
        <div style="background: linear-gradient(135deg, #0e3b6e 0%, #155e75 100%); padding: 1.2rem 1.6rem; border-radius: 12px; color: white; margin-bottom: 1.2rem; box-shadow: 0 4px 14px rgba(14, 59, 110, 0.25);">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
                <div>
                    <h2 style="color: #ffffff; margin: 0; font-size: 1.5rem; font-weight: 800; letter-spacing: -0.5px;">⚡ High Speed Enrollment Verification System</h2>
                    <p style="color: #a5f3fc; margin: 3px 0 0 0; font-size: 0.92rem;">Enrollment Telecalling Portal | Google Sheet: <b>enrollment_Verification</b> (Yellow Marked Form)</p>
                </div>
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="background: rgba(255,255,255,0.18); padding: 6px 14px; border-radius: 20px; font-weight: 700; font-size: 0.88rem; border: 1px solid rgba(255,255,255,0.3);">
                        🎓 Enrollment Module
                    </span>
                    <span style="background: #10b981; color: #ffffff; padding: 6px 14px; border-radius: 20px; font-weight: 800; font-size: 0.88rem;">
                        👤 {current_spoc}
                    </span>
                </div>
            </div>
        </div>
    """.replace("{current_spoc}", current_spoc.title()), unsafe_allow_html=True)

    # ==========================================================================
    # 📊 PERFORMANCE VIEW SELECTOR (Board 1 & Board 2)
    # ==========================================================================
    view_options = ["🌐 All Team Combined (Portal Total)"] + all_spocs

    col_view_lbl, col_view_sel = st.columns([1.5, 2.5])
    with col_view_lbl:
        st.markdown("<div style='padding-top: 6px; font-weight: 800; color: #0f4c81; font-size: 1.05rem;'>📊 Select Performance View:</div>", unsafe_allow_html=True)
    with col_view_sel:
        forced_view = st.session_state.get("enr_perf_view")
        if forced_view and forced_view in view_options:
            default_v_idx = view_options.index(forced_view)
        elif not is_admin and current_spoc.title() in view_options:
            default_v_idx = view_options.index(current_spoc.title())
        else:
            default_v_idx = 0

        selected_perf_view = st.selectbox(
            "Select Performance View",
            view_options,
            index=default_v_idx,
            label_visibility="collapsed",
            key="enr_perf_view_selector_box"
        )
        st.session_state.enr_perf_view = selected_perf_view

    if selected_perf_view == "🌐 All Team Combined (Portal Total)":
        display_scope_name = "All Team Combined"
        scoped_students = all_enrollment_students
    else:
        display_scope_name = selected_perf_view
        scoped_students = [s for s in all_enrollment_students if s["called_by"].strip().lower() == selected_perf_view.strip().lower()]

    scope_stats = compute_enrollment_stats(scoped_students, st.session_state.enrollment_live_history)
    v_assigned = scope_stats["total_assigned"]
    v_called = scope_stats["total_called"]
    v_yes = scope_stats["yes_count"]
    v_no = scope_stats["no_count"]
    v_pending = scope_stats["fresh_pending"]
    v_rate = scope_stats["contactable_pct"]

    col_b1, col_b2 = st.columns(2)
    with col_b1:
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #f0fdf4 0%, #ffffff 100%); border: 1.5px solid #86efac; border-left: 6px solid #16a34a; border-radius: 12px; padding: 14px 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); min-height: 165px;">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div>
                    <span style="font-size: 0.8rem; font-weight: 700; color: #166534; text-transform: uppercase; letter-spacing: 0.5px;">📋 Board 1: Calling Pipeline ({display_scope_name})</span>
                    <div style="display: flex; align-items: baseline; gap: 10px; margin-top: 4px;">
                        <span style="font-size: 2.3rem; font-weight: 900; color: #15803d; line-height: 1;">{v_pending}</span>
                        <span style="font-size: 1.05rem; font-weight: 800; color: #166534;">Fresh Calls Pending</span>
                    </div>
                </div>
                <span style="background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; padding: 4px 10px; border-radius: 20px; font-size: 0.82rem; font-weight: 700;">Target: {v_assigned}</span>
            </div>
            <div style="margin-top: 12px; padding-top: 10px; border-top: 1px dashed #bbf7d0; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; font-size: 0.88rem;">
                <span style="color: #374151;">Total Assigned: <b>{v_assigned}</b></span>
                <span style="color: #2563eb;">Total Called: <b>{v_called}</b></span>
                <span style="color: #16a34a;">Yes (Contacted): <b>{v_yes}</b></span>
                <span style="color: #dc2626;">No (Unreached): <b>{v_no}</b></span>
            </div>
            <div style="margin-top: 8px; font-size: 0.78rem; color: #6b7280;">
                📊 <b>Formula:</b> Total Calls ({v_assigned}) − Called ({v_called}) [Yes: {v_yes} + No: {v_no}] = <b>{v_pending} Fresh Pending</b>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_b2:
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #eff6ff 0%, #ffffff 100%); border: 1.5px solid #bfdbfe; border-left: 6px solid #2563eb; border-radius: 12px; padding: 14px 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); min-height: 165px;">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div>
                    <span style="font-size: 0.8rem; font-weight: 700; color: #1e40af; text-transform: uppercase; letter-spacing: 0.5px;">📈 Board 2: Contactability Rate ({display_scope_name})</span>
                    <div style="display: flex; align-items: baseline; gap: 10px; margin-top: 4px;">
                        <span style="font-size: 2.3rem; font-weight: 900; color: #1d4ed8; line-height: 1;">{v_rate:.1f}%</span>
                        <span style="font-size: 1.05rem; font-weight: 800; color: #1e40af;">Contacted Ratio</span>
                    </div>
                </div>
                <span style="background: #dbeafe; color: #1d4ed8; border: 1px solid #bfdbfe; padding: 4px 10px; border-radius: 20px; font-size: 0.82rem; font-weight: 700;">Rate of Yes</span>
            </div>
            <div style="margin-top: 12px; padding-top: 10px; border-top: 1px dashed #bfdbfe; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; font-size: 0.88rem;">
                <span style="color: #374151;">Yes Count: <b style="color: #16a34a;">{v_yes}</b></span>
                <span style="color: #374151;">Total Called: <b>{v_called}</b></span>
                <span style="color: #374151;">Pending Uncalled: <b>{v_pending}</b></span>
            </div>
            <div style="margin-top: 8px; font-size: 0.78rem; color: #6b7280;">
                📊 <b>Formula:</b> [Yes Count ({v_yes}) ÷ Total Called ({v_called})] × 100 = <b>{v_rate:.1f}%</b>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

    # Popovers for Fresh Call Queue & Uncontactable Queue
    col_hdr_btns1, col_hdr_btns2 = st.columns(2)
    with col_hdr_btns1:
        st.markdown('<div class="fresh-call-header-btn">', unsafe_allow_html=True)
        with st.popover(f"📋 Fresh Calling Queue ({v_pending} Pending)", use_container_width=True):
            render_enrollment_fresh_call_list(scope_stats, selected_perf_view if selected_perf_view != "🌐 All Team Combined (Portal Total)" else current_spoc)
        st.markdown('</div>', unsafe_allow_html=True)

    with col_hdr_btns2:
        st.markdown('<div class="no-list-header-btn">', unsafe_allow_html=True)
        with st.popover(f"🚫 Uncontactable ('No') Queue ({v_no} Unreached)", use_container_width=True):
            render_enrollment_not_contactable_list(scope_stats, selected_perf_view if selected_perf_view != "🌐 All Team Combined (Portal Total)" else current_spoc)
        st.markdown('</div>', unsafe_allow_html=True)

    # ==========================================================================
    # 🎯 TARGET SELECTION & NAVIGATION
    # ==========================================================================
    if is_admin:
        if selected_perf_view != "🌐 All Team Combined (Portal Total)":
            active_queue_students = scoped_students
            for i, s in enumerate(active_queue_students):
                s["queue_index"] = i
        else:
            admin_spoc_list = ["All SPOCs"] + all_spocs
            sel_admin_spoc = st.selectbox(
                "👤 Admin Filter: Working Queue for SPOC",
                admin_spoc_list,
                index=0,
                key="enr_admin_spoc_filter"
            )
            if sel_admin_spoc == "All SPOCs":
                active_queue_students = all_enrollment_students
            else:
                active_queue_students = [s for s in all_enrollment_students if s["called_by"].strip().lower() == sel_admin_spoc.strip().lower()]
                for i, s in enumerate(active_queue_students):
                    s["queue_index"] = i
    else:
        spoc_matches = [s for s in all_enrollment_students if s["called_by"].strip().lower() == current_spoc.strip().lower()]
        if spoc_matches:
            active_queue_students = spoc_matches
            for i, s in enumerate(active_queue_students):
                s["queue_index"] = i
        else:
            # Fallback so no SPOC is ever locked out of viewing their queue
            active_queue_students = scoped_students if scoped_students else all_enrollment_students
            for i, s in enumerate(active_queue_students):
                s["queue_index"] = i

    # Discover unique Call IDs in active_queue_students
    available_q_cids = sorted(list({str(s.get("call_id", "")).strip() for s in active_queue_students if str(s.get("call_id", "")).strip()}))
    sel_q_cid = "All Call IDs"
    if len(available_q_cids) > 1:
        col_qf1, col_qf2 = st.columns([2.5, 3.5])
        with col_qf1:
            q_cid_options = [f"All Call IDs ({len(active_queue_students)})"] + [f"{cid} ({sum(1 for s in active_queue_students if str(s.get('call_id', '')).strip() == cid)})" for cid in available_q_cids]
            sel_q_opt = st.selectbox(
                "🏷️ Filter Calling Queue by Call ID:",
                q_cid_options,
                index=0,
                key=f"enr_q_cid_filter_{current_spoc}"
            )
            if "(" in sel_q_opt:
                sel_q_cid = sel_q_opt.split(" (")[0].strip()
        if sel_q_cid != "All Call IDs":
            active_queue_students = [s for s in active_queue_students if str(s.get("call_id", "")).strip() == sel_q_cid]
            for i, s in enumerate(active_queue_students):
                s["queue_index"] = i

    total_assigned_queue = len(active_queue_students)
    if total_assigned_queue == 0:
        active_queue_students = all_enrollment_students
        total_assigned_queue = len(active_queue_students)
        if total_assigned_queue == 0:
            st.warning("No enrollment verification records found. Please check data file or Google Sheet.")
            return

    # Auto-resume verification index
    saved_q, saved_act = get_saved_enrollment_index(current_spoc, active_queue_students)
    if "enrollment_queue_index" not in st.session_state:
        st.session_state.enrollment_queue_index = saved_q
    if "enrollment_active_call_index" not in st.session_state:
        st.session_state.enrollment_active_call_index = saved_act

    current_q_idx = st.session_state.enrollment_queue_index
    if current_q_idx >= total_assigned_queue:
        current_q_idx = total_assigned_queue - 1
        st.session_state.enrollment_queue_index = current_q_idx
    if current_q_idx < 0:
        current_q_idx = 0
        st.session_state.enrollment_queue_index = 0

    current_student = active_queue_students[current_q_idx]

    # Quick Search Bar
    st.markdown('<div class="profile-card-enhanced" style="padding: 10px 14px; margin-bottom: 12px;">', unsafe_allow_html=True)
    c_srch1, c_srch2 = st.columns([4, 1.2])
    with c_srch1:
        search_query = st.text_input(
            "🔍 Fast Student Search (Name / Student Code / Phone / Batch)",
            placeholder="Type student name, student code (AF...), phone, or batch...",
            label_visibility="collapsed",
            key="enr_fast_search_input"
        )
    with c_srch2:
        if st.button("Search 🔎", use_container_width=True, key="enr_search_btn"):
            if search_query.strip():
                sq = search_query.strip().lower()
                matched_idx = next(
                    (i for i, s in enumerate(active_queue_students)
                     if sq in s["student_name"].lower() or sq in clean_phone(s["contact_number"]) or sq in s["student_code"].lower() or sq in s["batch_code"].lower()),
                    None
                )
                if matched_idx is not None:
                    st.session_state.enrollment_queue_index = matched_idx
                    st.session_state.enrollment_editing_row = active_queue_students[matched_idx]["row_num"]
                    save_enrollment_progress(current_spoc, matched_idx, active_queue_students[matched_idx]["contact_number"], active_call_index=st.session_state.get("enrollment_active_call_index", 0))
                    st.toast(f"Found student #{matched_idx + 1}: {active_queue_students[matched_idx]['student_name']}", icon="🎯")
                    st.rerun()
                else:
                    st.error("No student matching search query.")
    st.markdown('</div>', unsafe_allow_html=True)

    # Navigation Controls Bar
    c_first, c_prev, c_next, c_last, c_clear, c_refresh = st.columns([1, 1, 1, 1, 1.2, 1.2])
    if c_first.button("⏮ First", use_container_width=True, disabled=(current_q_idx == 0)):
        st.session_state.enrollment_queue_index = 0
        first_s = active_queue_students[0]
        save_enrollment_progress(current_spoc, 0, first_s["contact_number"], active_call_index=st.session_state.get("enrollment_active_call_index", 0))
        st.rerun()

    if c_prev.button("◀ Prev", use_container_width=True, disabled=(current_q_idx <= 0)):
        st.session_state.enrollment_queue_index = max(0, current_q_idx - 1)
        prev_s = active_queue_students[st.session_state.enrollment_queue_index]
        save_enrollment_progress(current_spoc, st.session_state.enrollment_queue_index, prev_s["contact_number"], active_call_index=st.session_state.get("enrollment_active_call_index", 0))
        st.rerun()

    if c_next.button("Next ▶", use_container_width=True, disabled=(current_q_idx >= total_assigned_queue - 1)):
        st.session_state.enrollment_queue_index = min(total_assigned_queue - 1, current_q_idx + 1)
        if st.session_state.enrollment_queue_index > st.session_state.get("enrollment_active_call_index", 0):
            st.session_state.enrollment_active_call_index = st.session_state.enrollment_queue_index
        next_s = active_queue_students[st.session_state.enrollment_queue_index]
        save_enrollment_progress(current_spoc, st.session_state.enrollment_queue_index, next_s["contact_number"], active_call_index=st.session_state.get("enrollment_active_call_index", 0))
        st.rerun()

    if c_last.button("⏭ Last", use_container_width=True, disabled=(current_q_idx == total_assigned_queue - 1)):
        st.session_state.enrollment_queue_index = total_assigned_queue - 1
        last_s = active_queue_students[total_assigned_queue - 1]
        save_enrollment_progress(current_spoc, total_assigned_queue - 1, last_s["contact_number"], active_call_index=st.session_state.get("enrollment_active_call_index", 0))
        st.rerun()

    if c_clear.button("🧹 Clear Form", use_container_width=True):
        row_k = current_student["row_num"]
        st.session_state.pop(f"enr_preset_{row_k}", None)
        st.session_state.pop("enrollment_editing_row", None)
        keys_to_remove = [k for k in st.session_state.keys() if f"_{row_k}" in k and k.startswith("enr_")]
        for k in keys_to_remove:
            st.session_state.pop(k, None)
        st.toast("Form cleared for current student!", icon="🧹")
        st.rerun()

    if c_refresh.button("🔄 Refresh DB", use_container_width=True):
        st.session_state.pop("enrollment_master_rows", None)
        fetch_enrollment_master_data.clear()
        st.cache_data.clear()
        st.toast("Database cache refreshed from Google Sheets!", icon="🔄")
        st.rerun()

    # ==========================================================================
    # 🏁 HIGH SPEED "ALL CALLS DONE" FINALIZE ACTION FOR EACH RESPECTIVE SPOC
    # ==========================================================================
    total_spoc_calls = len(active_queue_students)
    done_spoc_calls = sum(1 for s in active_queue_students if s.get("call_status") == "Done")
    prog_spoc_calls = total_spoc_calls - done_spoc_calls

    if prog_spoc_calls > 0:
        st.markdown(f"""
            <div style="background: #ffffff; border: 2.2px solid #0284c7; border-radius: 10px; padding: 12px 16px; margin-bottom: 12px; box-shadow: 0 2px 10px rgba(2, 132, 199, 0.12);">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                    <div>
                        <span style="color: #0369a1; font-size: 1.05rem; font-weight: 800;">📞 Calling Scope: {current_spoc.title()}</span>
                        <div style="color: #475569; font-size: 0.86rem; margin-top: 3px;">
                            ✅ Done: <b style="color: #16a34a;">{done_spoc_calls}</b> &nbsp;|&nbsp; ⏳ In Progress: <b style="color: #ea580c;">{prog_spoc_calls}</b> &nbsp;|&nbsp; 📊 Total Allocated: <b>{total_spoc_calls}</b>
                        </div>
                    </div>
                    <div style="color: #0f172a; font-size: 0.84rem; background: #f0f9ff; border: 1px solid #bae6fd; padding: 6px 12px; border-radius: 6px; font-weight: 600;">
                        💡 After calling your students, click <b>ALL CALLS DONE</b> below to mark all your student calls as Done in Google Sheet.
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)

        c_done_btn, c_done_help = st.columns([2.5, 3.5])
        with c_done_btn:
            btn_cid_suffix = f" ({sel_q_cid})" if 'sel_q_cid' in locals() and sel_q_cid != "All Call IDs" else ""
            if st.button(f"🏁 ALL CALLS DONE{btn_cid_suffix} — Finalize in Google Sheet", type="primary", use_container_width=True, key=f"enr_main_done_{current_spoc}", help="Click when you have called your students. Instantly sets Call_Status = Done in Google Sheet for all your calls"):
                updates_map = {}
                batch_updates = []
                for s in active_queue_students:
                    s["call_status"] = "Done"
                    cid = s.get("call_id") or ("3300" if s["row_num"] <= 3301 else "3300_Update")
                    updates_map[s["row_num"]] = ([], "Done", cid)
                    batch_updates.append({
                        'range': f'AP{s["row_num"]}:AQ{s["row_num"]}',
                        'values': [['Done', cid]]
                    })
                # 1. Instant sub-millisecond local update
                batch_update_in_memory_enrollment_rows(updates_map)
                batch_update_local_enrollment_rows(updates_map)
                # 2. Async background sync to Google Sheet (Zero UI wait)
                if enrollment_ws and batch_updates:
                    _ENROLLMENT_BG_EXECUTOR.submit(enrollment_ws.batch_update, batch_updates)
                st.balloons()
                st.toast(f"🎉 Success! All {total_spoc_calls} calls for {current_spoc.title()} are now marked as 'Done' in Google Sheet!", icon="✅")
                time.sleep(0.2)
                st.rerun()
        with c_done_help:
            st.caption("⚡ **One-Click Sync**: Updates all student rows allocated to you to **`Call_Status: Done`** in Google Sheet and updates your downloadable SPOC reports.")
    else:
        st.markdown(f"""
            <div style="background: linear-gradient(135deg, #dcfce7, #f0fdf4); border: 2.2px solid #22c55e; border-radius: 10px; padding: 12px 18px; margin-bottom: 12px; text-align: center; box-shadow: 0 2px 10px rgba(34, 197, 94, 0.15);">
                <span style="font-size: 1.15rem; font-weight: 800; color: #15803d;">🎉 All Respective Calls Finished for {current_spoc.title()}!</span>
                <div style="font-size: 0.88rem; color: #166534; margin-top: 4px;">
                    All <b>{total_spoc_calls}</b> allocated student records are marked as <b>Call_Status: Done</b> in Google Sheet. You can download the completed data from the sidebar.
                </div>
            </div>
        """, unsafe_allow_html=True)

    # Progress Bar
    prog_pct = min((current_q_idx + 1) / total_assigned_queue, 1.0) if total_assigned_queue > 0 else 0
    st.progress(prog_pct)

    # Calling Target Banner
    col_t1, col_t2 = st.columns([5, 1.1])
    phone_clean = clean_phone(current_student['contact_number'])

    with col_t1:
        # Safe HTML rendering without deprecation warnings
        components.html(f"""
        <!DOCTYPE html>
        <html>
        <head>
        <style>
            * {{ box-sizing: border-box; }}
            body {{
                margin: 0; padding: 0; background: transparent;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            }}
            .queue-banner {{
                background: linear-gradient(135deg, #e0f2fe 0%, #f0fdfa 100%);
                padding: 8px 16px; border-radius: 8px; border-left: 5px solid #0284c7;
                display: flex; justify-content: space-between; align-items: center; height: 48px;
            }}
            .banner-left {{
                font-size: 1.0rem; color: #0369a1; font-weight: 700;
                display: flex; align-items: center; gap: 8px; white-space: nowrap;
                overflow: hidden; text-overflow: ellipsis;
            }}
            .phone-link {{ color: #0284c7; font-weight: 800; font-size: 1.08rem; text-decoration: underline; }}
            .copy-banner-btn {{
                border: 1.5px solid #0284c7; background-color: #ffffff; color: #0369a1;
                font-weight: 700; font-size: 0.90rem; border-radius: 6px; padding: 5px 14px;
                cursor: pointer; transition: all 0.2s ease-in-out; display: inline-flex;
                align-items: center; gap: 5px; white-space: nowrap;
            }}
            .copy-banner-btn:hover {{ background-color: #e0f2fe; border-color: #0369a1; transform: translateY(-1px); }}
            .copy-banner-btn.copied {{ background-color: #10b981 !important; color: #ffffff !important; border-color: #059669 !important; }}
        </style>
        </head>
        <body>
        <div class="queue-banner">
            <div class="banner-left">
                <span>🎯 Calling Target <b>#{current_q_idx + 1} of {total_assigned_queue}</b></span>
                <span>•</span>
                <span style="color: #0f172a;">{current_student['student_name']}</span>
                <span>•</span>
                <a href="tel:{phone_clean}" class="phone-link">📞 {phone_clean}</a>
            </div>
            <div>
                <button id="copyBtn" class="copy-banner-btn" onclick="copyNumber()">📋 Copy Phone Number</button>
            </div>
        </div>
        <script>
        function copyNumber() {{
            const num = "{phone_clean}";
            if (navigator.clipboard && window.isSecureContext) {{
                navigator.clipboard.writeText(num).then(showSuccess, fallbackCopy);
            }} else {{
                fallbackCopy();
            }}
            function showSuccess() {{
                const btn = document.getElementById("copyBtn");
                btn.innerHTML = "✅ Copied!";
                btn.className = "copy-banner-btn copied";
                setTimeout(() => {{
                    btn.innerHTML = "📋 Copy Phone Number";
                    btn.className = "copy-banner-btn";
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

    with col_t2:
        if st.button("⏭ Skip", use_container_width=True, key=f"enr_skip_btn_{current_student['row_num']}"):
            st.session_state.enrollment_queue_index = min(total_assigned_queue - 1, current_q_idx + 1)
            next_s = active_queue_students[st.session_state.enrollment_queue_index]
            save_enrollment_progress(current_spoc, st.session_state.enrollment_queue_index, next_s["contact_number"], active_call_index=st.session_state.get("enrollment_active_call_index", 0))
            st.toast("Skipped to next target", icon="⏭")
            st.rerun()

    # ==========================================================================
    # 👤 STUDENT ENROLLMENT PROFILE DETAILS (MATCHING SCREENSHOT 2)
    # ==========================================================================
    st.markdown('<div class="profile-card-enhanced">', unsafe_allow_html=True)
    st.markdown("""
        <div class="profile-title-bar">
            <span>🎓 Student Enrollment Profile Details</span>
        </div>
    """, unsafe_allow_html=True)

    p_col1, p_col2, p_col3, p_col4 = st.columns(4)
    with p_col1:
        st.markdown(f"<div class='profile-label-styled'>Student Name</div><div class='profile-val-styled' style='font-size: 1.15rem; color: #0f172a;'>{current_student['student_name']}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label-styled' style='margin-top:10px;'>Student Code</div><div class='profile-val-styled' style='font-family: monospace; font-size: 0.95rem; background: #f1f5f9; padding: 2px 6px; border-radius: 4px; display: inline-block;'>{current_student['student_code'] or 'N/A'}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label-styled' style='margin-top:10px;'>Gender & DOB</div><div class='profile-val-styled' style='text-transform: capitalize;'>{current_student['gender'] or 'N/A'} &nbsp;•&nbsp; <b>{current_student['dob'] or 'N/A'}</b></div>", unsafe_allow_html=True)

    with p_col2:
        phone_raw = current_student['contact_number']
        wa_text = urllib.parse.quote(f"Hello {current_student['student_name']}, calling from Anudip Foundation regarding your course enrollment ({current_student['course_name']}). Could you please confirm your training details? Thank you!")
        st.markdown(f"""
            <div class='profile-label-styled'>Contact Number</div>
            <div style='display: flex; align-items: center; gap: 8px; flex-wrap: wrap;'>
                <a href='tel:{phone_raw}' style='color:#0284c7; font-weight:800; font-size:1.15rem; text-decoration: none;'>📞 {phone_raw}</a>
                <a href='https://wa.me/91{clean_phone(phone_raw)}?text={wa_text}' target='_blank' style='background:#25d366; color:white; padding:2px 8px; border-radius:12px; font-size:0.75rem; text-decoration:none; font-weight:700;'>💬 WhatsApp</a>
            </div>
        """, unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label-styled' style='margin-top:10px;'>Alt. Contact</div><div class='profile-val-styled'>{current_student['alt_contact_number'] if current_student['alt_contact_number'] != '0' else 'None'}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label-styled' style='margin-top:10px;'>Funder Name</div><div class='profile-val-styled'><span style='background: #e0f2fe; color: #0369a1; padding: 2px 8px; border-radius: 12px; font-size: 0.85rem; font-weight: 700;'>{current_student['funder_name'] or 'N/A'}</span></div>", unsafe_allow_html=True)

    with p_col3:
        st.markdown(f"<div class='profile-label-styled'>Batch Code</div><div class='profile-val-styled' style='color:#0f4c81;'>{current_student['batch_code']}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label-styled' style='margin-top:10px;'>Course Name</div><div class='profile-val-styled' style='font-size: 0.95rem; line-height: 1.3;'>{current_student['course_name']}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label-styled' style='margin-top:10px;'>Start Date / Centre</div><div class='profile-val-styled' style='font-family: monospace;'>{current_student['start_date'] or 'N/A'} &nbsp;•&nbsp; <b>{current_student['centre_code']} ({current_student['state']})</b></div>", unsafe_allow_html=True)

    with p_col4:
        is_dropped = "drop" in current_student['enrollment_status'].lower()
        badge_bg = "#fee2e2" if is_dropped else "#dcfce7"
        badge_fg = "#991b1b" if is_dropped else "#166534"
        badge_txt = current_student['enrollment_status'].capitalize() or "Enrolled"
        st.markdown(f"<div class='profile-label-styled'>Enrollment Status</div><div class='profile-val-styled'><span style='background: {badge_bg}; color: {badge_fg}; padding: 3px 10px; border-radius: 12px; font-size: 0.85rem; font-weight: 800;'>{badge_txt}</span></div>", unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label-styled' style='margin-top:10px;'>Come To Know</div><div class='profile-val-styled'>{current_student['come_to_know'] or 'Direct'}</div>", unsafe_allow_html=True)
        ref_p = current_student['referral_person_name'] or "N/A"
        st.markdown(f"<div class='profile-label-styled' style='margin-top:10px;'>Referral / Qualification</div><div class='profile-val-styled'>{ref_p} &nbsp;•&nbsp; <span style='color: #475569;'>{current_student['education_qualification'] or 'N/A'}</span></div>", unsafe_allow_html=True)

    # Accent Divider Bar (Yellow/Gold highlighting the Yellow-Mark section)
    st.markdown('<div style="height: 4px; background: linear-gradient(90deg, #eab308 0%, #facc15 100%); border-radius: 2px; margin: 16px 0 16px 0;"></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ==========================================================================
    # 📝 CALL VERIFICATION QUESTIONNAIRE (YELLOW MARKED EXCEL COLUMNS R TO AM)
    # ==========================================================================
    is_already_verified = bool(current_student["contactable"])
    is_edit_mode = st.session_state.get("enrollment_editing_row") == current_student["row_num"]

    cur_cid = current_student.get("call_id", "3300")
    cur_cstatus = "Done" if (is_edit_mode or is_already_verified) else current_student.get("call_status", "Progress")
    cstatus_bg = "#dcfce7" if cur_cstatus == "Done" else "#fef3c7"
    cstatus_fg = "#166534" if cur_cstatus == "Done" else "#92400e"
    cstatus_bd = "#bbf7d0" if cur_cstatus == "Done" else "#fde68a"

    status_badge_html = f"""
        <div style="display: flex; gap: 6px; align-items: center; flex-wrap: wrap;">
            <span style="background: #e0f2fe; color: #0369a1; border: 1.5px solid #bae6fd; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.84rem;">
                🏷️ Call ID: {cur_cid}
            </span>
            <span style="background: {cstatus_bg}; color: {cstatus_fg}; border: 1.5px solid {cstatus_bd}; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.84rem;">
                📞 Status: {cur_cstatus}
            </span>
            <span style="background: #fef3c7; color: #92400e; border: 1.5px solid #fcd34d; padding: 4px 12px; border-radius: 6px; font-weight: 800; font-size: 0.88rem;">
                ✏️ EDIT & UPDATE MODE (Row #{current_student['row_num']})
            </span>
        </div>
    """ if (is_edit_mode or is_already_verified) else f"""
        <div style="display: flex; gap: 6px; align-items: center; flex-wrap: wrap;">
            <span style="background: #e0f2fe; color: #0369a1; border: 1.5px solid #bae6fd; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.84rem;">
                🏷️ Call ID: {cur_cid}
            </span>
            <span style="background: {cstatus_bg}; color: {cstatus_fg}; border: 1.5px solid {cstatus_bd}; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.84rem;">
                📞 Status: {cur_cstatus}
            </span>
            <span style="background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.85rem;">
                ✨ FRESH CALL VERIFICATION (Target #{current_q_idx + 1})
            </span>
        </div>
    """

    st.markdown('<div class="profile-card-enhanced" style="border-top: 4px solid #eab308;">', unsafe_allow_html=True)
    st.markdown(f"""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.2rem; flex-wrap: wrap; gap: 8px;">
            <div style="font-size: 1.22rem; font-weight: 800; color: #0f4c81; display: flex; align-items: center; gap: 8px;">
                📝 Enrollment Verification Form (Yellow Marked Columns)
            </div>
            <div>{status_badge_html}</div>
        </div>
    """, unsafe_allow_html=True)

    if is_edit_mode or is_already_verified:
        st.markdown(f"""
            <div style="background: #fffbeb; border: 1.5px solid #fde68a; border-left: 6px solid #d97706; padding: 10px 14px; border-radius: 8px; margin-bottom: 14px;">
                <b style="color: #92400e; font-size: 0.98rem;">✏️ Reviewing & Updating Target #{current_q_idx + 1} — {current_student['student_name']} (Row #{current_student['row_num']}):</b>
                <div style="color: #b45309; font-size: 0.85rem; margin-top: 2px;">
                    Previously saved details are loaded below. Update any fields and click <b>Update & Insert Enrollment Verification</b> to save your changes to Google Sheets.
                </div>
            </div>
        """, unsafe_allow_html=True)

    row_preset = st.session_state.get(f"enr_preset_{current_student['row_num']}", {})

    # 1. Question: Is the student Contactable?
    if "contactable" in row_preset:
        def_cont_idx = 0 if row_preset["contactable"] == "Yes" else 1
    else:
        def_cont_idx = 0 if current_student["contactable"].strip().lower() != "no" else 1

    st.markdown("""
        <div class="question-pill-header" style="text-align: left; background: #eff6ff; border-color: #bfdbfe; color: #1e40af; padding: 8px 12px; border-radius: 8px;">
            1. Is the student Contactable? (Call Status)
        </div>
    """, unsafe_allow_html=True)

    f_contactable = st.radio(
        "Is the student Contactable? (Call Status)",
        ["Yes", "No"],
        index=def_cont_idx,
        horizontal=True,
        label_visibility="collapsed",
        key=f"enr_rad_cont_{current_student['row_num']}"
    )

    # --------------------------------------------------------------------------
    # ❌ CONDITION: IF CONTACTABLE == NO
    # --------------------------------------------------------------------------
    if f_contactable == "No":
        st.markdown("""
            <div style="background: #fff7ed; border: 1.5px solid #fed7aa; border-left: 5px solid #ea580c; padding: 12px 16px; border-radius: 8px; margin: 12px 0;">
                <b style="color: #9a3412; font-size: 0.98rem;">🚫 Student Not Contactable:</b>
                <span style="color: #c2410c; font-size: 0.9rem; margin-left: 8px;">Please select the call disposition / reason below to log this target.</span>
            </div>
        """, unsafe_allow_html=True)

        existing_rem = row_preset.get("nocont_reason", current_student["enroll_remarks"].strip())
        def_nocont_idx = 0
        if existing_rem in ENROLLMENT_UNABLE_TO_TRACK_OPTIONS:
            def_nocont_idx = ENROLLMENT_UNABLE_TO_TRACK_OPTIONS.index(existing_rem)

        c_no1, c_no2 = st.columns(2)
        with c_no1:
            st.markdown('<div class="question-pill-header">Call Remarks / Unable To Reach Reason</div>', unsafe_allow_html=True)
            f_nocont_reason = st.selectbox(
                "Call Remarks / Unable To Reach Reason",
                ENROLLMENT_UNABLE_TO_TRACK_OPTIONS,
                index=def_nocont_idx,
                label_visibility="collapsed",
                key=f"enr_sel_nocont_{current_student['row_num']}"
            )

        with c_no2:
            st.markdown('<div class="question-pill-header">Verification Date</div>', unsafe_allow_html=True)
            f_vdate_no = st.date_input(
                "Verification Date",
                value=date.today(),
                disabled=True,
                label_visibility="collapsed",
                key=f"enr_date_no_{current_student['row_num']}"
            )

        c_no3, c_no4 = st.columns(2)
        with c_no3:
            f_remarks_2_no = st.text_input(
                "Remarks 2 (SPOC Notes)",
                value=row_preset.get("remarks_2", current_student["remarks_2"]),
                key=f"enr_ta_rem2_no_{current_student['row_num']}",
                placeholder="E.g. Called twice, ringing no response..."
            )
        with c_no4:
            f_remarks_3_no = st.text_input(
                "Remarks 3 (Supervisor / Center Notes)",
                value=row_preset.get("remarks_3", current_student["remarks_3"]),
                key=f"enr_ta_rem3_no_{current_student['row_num']}",
                placeholder="Optional supervisor comment..."
            )

        st.markdown("<br>", unsafe_allow_html=True)
        btn_label_no = f"💾 Update & Insert Uncontactable Call (Row #{current_student['row_num']})" if (is_edit_mode or is_already_verified) else "🔴 Save & Insert Uncontactable Call"
        if st.button(btn_label_no, type="primary", use_container_width=True, key=f"enr_sub_no_{current_student['row_num']}"):
            payload = [
                "No",                           # R: Contactable
                "",                             # S: Class started (Yes/No)
                "",                             # T: Got information about Anudip
                "",                             # U: Referral Person Name(Yes/No)
                "",                             # V: Please fill the Name
                "",                             # W: Your_DOB
                "",                             # X: Monthly Family Income RS.
                "",                             # Y: Satisfied With Conversation
                "",                             # Z: Classes In A Week
                "",                             # AA: Class Mode
                "",                             # AB: Quality Of Classes
                "",                             # AC: Current Educational Status
                str(date.today()),              # AD: Verification Date
                "",                             # AE: Interest In Job
                "",                             # AF: Present Working Status
                "",                             # AG: COMPANY NAME
                "",                             # AH: Salary
                "",                             # AI: Part Time /Full Time
                "",                             # AJ: How Many Months Working
                "",                             # AK: Did They Left The Job After Joining Course
                "",                             # AL: Why They Joined Course, If Stu Working
                f_nocont_reason,                # AM: Enroll Remarks
                f_remarks_2_no.strip(),         # AN: Remarks 2
                f_remarks_3_no.strip()          # AO: Remarks 3
            ]

            try:
                p_cid = current_student.get("call_id", "3300")
                current_student["call_status"] = "Done"

                # 1. Update in-memory session rows immediately (Sub-millisecond)
                update_in_memory_enrollment_row(current_student['row_num'], payload, call_status="Done", call_id=p_cid)

                # 2. Asynchronous background sync to Google Sheets & local CSV
                dispatch_enrollment_sync(enrollment_ws, current_student['row_num'], payload, call_status="Done", call_id=p_cid)

                # 3. Update session live history
                st.session_state.enrollment_live_history.insert(0, (current_student['row_num'], list(payload)))
                st.session_state.enrollment_live_history = st.session_state.enrollment_live_history[:25]
                st.session_state.pop("enrollment_editing_row", None)

                # 4. Instant UI Toast
                st.toast(f"✅ Saved Target #{current_q_idx + 1} ({current_student['student_name']}) as Not Contactable!", icon="🚫")

                # 5. Advance to next student in queue
                if current_q_idx + 1 < total_assigned_queue:
                    st.session_state.enrollment_queue_index = current_q_idx + 1
                    next_s = active_queue_students[current_q_idx + 1]
                    save_enrollment_progress(current_spoc, current_q_idx + 1, next_s["contact_number"], active_call_index=st.session_state.get("enrollment_active_call_index", 0))

                # 6. Instant UI re-render
                st.rerun()
            except Exception as ex:
                st.error(f"Error saving: {ex}")

    # --------------------------------------------------------------------------
    # ✅ CONDITION: IF CONTACTABLE == YES -> Complete Enrollment Verification Form
    # --------------------------------------------------------------------------
    else:
        st.markdown("<div style='margin-top: 14px;'></div>", unsafe_allow_html=True)

        existing_outcome = row_preset.get("call_outcome", row_preset.get("enroll_remarks", current_student.get("enroll_remarks", ""))).strip()
        def_co_idx = 0
        if existing_outcome in ENROLLMENT_CONTACTED_BLANK_REMARKS:
            def_co_idx = ENROLLMENT_QUICK_CONTACTED_OPTIONS.index(existing_outcome)

        st.markdown("""
            <div class="question-pill-header" style="text-align: left; background: #f0fdf4; border-color: #bbf7d0; color: #166534; padding: 8px 12px; border-radius: 8px; margin-top: 10px;">
                📞 Verification Outcome / Call Type (Contactable = Yes)
            </div>
        """, unsafe_allow_html=True)

        f_call_outcome = st.radio(
            "Verification Outcome / Call Type",
            ENROLLMENT_QUICK_CONTACTED_OPTIONS,
            index=def_co_idx,
            horizontal=True,
            label_visibility="collapsed",
            key=f"enr_rad_outcome_{current_student['row_num']}"
        )

        if f_call_outcome in ENROLLMENT_CONTACTED_BLANK_REMARKS:
            st.markdown(f"""
                <div style="background: #eff6ff; border: 1.5px solid #bfdbfe; border-left: 5px solid #2563eb; padding: 12px 16px; border-radius: 8px; margin: 12px 0;">
                    <b style="color: #1e40af; font-size: 0.98rem;">📞 Student Contacted — {f_call_outcome}:</b>
                    <div style="color: #1e3a8a; font-size: 0.88rem; margin-top: 3px;">
                        The student answered the call (Contactable: <b>Yes</b>), but the full verification survey could not be completed.
                        All fields in Section 1 (Course & Training Details) and Section 2 (Employment & Career Interests) will be saved as <b>empty ("")</b>.
                    </div>
                </div>
            """, unsafe_allow_html=True)

            c_qc1, c_qc2 = st.columns(2)
            with c_qc1:
                st.markdown('<div class="question-pill-header">Enroll Remarks (Outcome)</div>', unsafe_allow_html=True)
                st.text_input(
                    "Enroll Remarks",
                    value=f_call_outcome,
                    disabled=True,
                    label_visibility="collapsed",
                    key=f"enr_txt_qcrem_{current_student['row_num']}"
                )
            with c_qc2:
                st.markdown('<div class="question-pill-header">Verification Date</div>', unsafe_allow_html=True)
                st.date_input(
                    "Verification Date",
                    value=date.today(),
                    disabled=True,
                    label_visibility="collapsed",
                    key=f"enr_date_qcdate_{current_student['row_num']}"
                )

            c_qc3, c_qc4 = st.columns(2)
            with c_qc3:
                f_remarks_2_quick = st.text_input(
                    "Remarks 2 (SPOC Notes)",
                    value=row_preset.get("remarks_2", current_student["remarks_2"]),
                    key=f"enr_txt_rem2_quick_{current_student['row_num']}",
                    placeholder="E.g. Student confirmed name then disconnected..."
                )
            with c_qc4:
                f_remarks_3_quick = st.text_input(
                    "Remarks 3 (Supervisor / Center Notes)",
                    value=row_preset.get("remarks_3", current_student["remarks_3"]),
                    key=f"enr_txt_rem3_quick_{current_student['row_num']}",
                    placeholder="Optional supervisor comment..."
                )

            st.markdown("<br>", unsafe_allow_html=True)
            btn_label_quick = f"💾 Update & Insert Verification (Row #{current_student['row_num']})" if (is_edit_mode or is_already_verified) else f"💾 Save & Insert Call ({f_call_outcome})"
            if st.button(btn_label_quick, type="primary", use_container_width=True, key=f"enr_btn_quick_{current_student['row_num']}"):
                payload = [
                    "Yes",                          # R: Contactable
                    "",                             # S: Class started (Yes/No)
                    "",                             # T: Got information about Anudip
                    "",                             # U: Referral Person Name(Yes/No)
                    "",                             # V: Please fill the Name
                    "",                             # W: Your_DOB
                    "",                             # X: Monthly Family Income RS.
                    "",                             # Y: Satisfied With Conversation
                    "",                             # Z: Classes In A Week
                    "",                             # AA: Class Mode
                    "",                             # AB: Quality Of Classes
                    "",                             # AC: Current Educational Status
                    str(date.today()),              # AD: Verification Date
                    "",                             # AE: Interest In Job
                    "",                             # AF: Present Working Status
                    "",                             # AG: COMPANY NAME
                    "",                             # AH: Salary
                    "",                             # AI: Part Time /Full Time
                    "",                             # AJ: How Many Months Working
                    "",                             # AK: Did They Left The Job After Joining Course
                    "",                             # AL: Why They Joined Course, If Stu Working
                    f_call_outcome,                 # AM: Enroll Remarks
                    f_remarks_2_quick.strip(),      # AN: Remarks 2
                    f_remarks_3_quick.strip()       # AO: Remarks 3
                ]

                try:
                    p_cid = current_student.get("call_id", "3300")
                    current_student["call_status"] = "Done"

                    # 1. Update in-memory session rows immediately (Sub-millisecond)
                    update_in_memory_enrollment_row(current_student['row_num'], payload, call_status="Done", call_id=p_cid)

                    # 2. Asynchronous background sync to Google Sheets & local CSV
                    dispatch_enrollment_sync(enrollment_ws, current_student['row_num'], payload, call_status="Done", call_id=p_cid)

                    # 3. Update session live history
                    st.session_state.enrollment_live_history.insert(0, (current_student['row_num'], list(payload)))
                    st.session_state.enrollment_live_history = st.session_state.enrollment_live_history[:25]
                    st.session_state.pop("enrollment_editing_row", None)

                    # 4. Instant UI Toast
                    st.toast(f"✅ Saved Target #{current_q_idx + 1} ({current_student['student_name']}) as Contactable: {f_call_outcome}!", icon="🎯")

                    # 5. Advance queue index and save progress
                    if current_q_idx + 1 < total_assigned_queue:
                        st.session_state.enrollment_queue_index = current_q_idx + 1
                        next_s = active_queue_students[current_q_idx + 1]
                        save_enrollment_progress(current_spoc, current_q_idx + 1, next_s["contact_number"], active_call_index=st.session_state.get("enrollment_active_call_index", 0))

                    # 6. Instant UI re-render
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error saving: {ex}")
        else:
            # ----------------------------------------------------------------------
            # Section 1: Course & Training Details
            # ----------------------------------------------------------------------
            st.markdown("""
                <div style="font-weight: 800; color: #0f4c81; font-size: 1.08rem; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                    <span>🎓 Section 1: Course & Training Details</span>
                </div>
            """, unsafe_allow_html=True)

            ref_key = f"enr_rad_ref_{current_student['row_num']}"
            raw_ref_val = row_preset.get("referral_person_ok", current_student["referral_person_ok"]).strip()
            def_ref_val = "Yes" if raw_ref_val.lower() == "yes" else ("No" if raw_ref_val.lower() == "no" else ("N/A" if raw_ref_val else "Yes"))
            current_ref_choice = st.session_state.get(ref_key, def_ref_val)
            is_ref_yes = (current_ref_choice == "Yes")

            if is_ref_yes:
                col_q1, col_q2, col_q3, col_q3_name = st.columns([1, 1, 1, 1])
            else:
                col_q1, col_q2, col_q3 = st.columns(3)

            with col_q1:
                st.markdown('<div class="question-pill-header">2. Class started? (Yes/No)</div>', unsafe_allow_html=True)
                def_cs_val = row_preset.get("class_started", current_student["class_started"]).strip().capitalize() or "Yes"
                def_cs_idx = 0 if def_cs_val == "Yes" else 1
                f_class_started = st.radio(
                    "Class started (Yes/No)",
                    ["Yes", "No","Dont Share"],
                    index=def_cs_idx,
                    horizontal=True,
                    label_visibility="collapsed",
                    key=f"enr_rad_cs_{current_student['row_num']}"
                )

            with col_q2:
                st.markdown('<div class="question-pill-header">3. Got information about Anudip?</div>', unsafe_allow_html=True)
                raw_info = str(row_preset.get("got_info_anudip", current_student.get("got_info_anudip", "")) or "").strip()
                def_info_idx = 0
                if raw_info:
                    for idx, opt in enumerate(ENROLLMENT_GOT_INFO_OPTIONS):
                        if opt.lower() == raw_info.lower() or opt.lower().replace(".", "") == raw_info.lower().replace(".", ""):
                            def_info_idx = idx
                            break
                elif current_student.get("come_to_know"):
                    ctk = str(current_student["come_to_know"]).strip().lower()
                    for idx, opt in enumerate(ENROLLMENT_GOT_INFO_OPTIONS):
                        if opt.lower() in ctk or ctk in opt.lower():
                            def_info_idx = idx
                            break
                f_got_info = st.selectbox(
                    "Got information about Anudip",
                    ENROLLMENT_GOT_INFO_OPTIONS,
                    index=def_info_idx,
                    label_visibility="collapsed",
                    key=f"enr_sel_info_{current_student['row_num']}"
                )

            with col_q3:
                ref_txt = f" ({current_student['referral_person_name']})" if current_student['referral_person_name'] else ""
                st.markdown(f'<div class="question-pill-header">4. Referral Person Name{ref_txt}?</div>', unsafe_allow_html=True)
                def_ref_idx = 0 if def_ref_val == "N/A" else (1 if def_ref_val == "No" else 2)
                f_referral_ok = st.radio(
                    "Referral Person Name(Yes/No)",
                    ["Yes", "No", "N/A"],
                    index=def_ref_idx,
                    horizontal=True,
                    label_visibility="collapsed",
                    key=ref_key
                )

            if is_ref_yes:
                with col_q3_name:
                    st.markdown('<div class="question-pill-header" style="background: #eff6ff; border-color: #93c5fd; color: #1e40af;">✍️ Please fill the Name</div>', unsafe_allow_html=True)
                    def_ref_name = row_preset.get("referral_name_fill", current_student.get("referral_name_fill", "") or current_student.get("referral_person_name", "")).strip()
                    f_referral_name_fill = st.text_input(
                        "Please fill the Name",
                        value=def_ref_name,
                        placeholder="Enter referral person name...",
                        label_visibility="collapsed",
                        key=f"enr_txt_refname_{current_student['row_num']}"
                    )
            else:
                f_referral_name_fill = ""

            col_q4, col_q5, col_q6, col_q7 = st.columns(4)

            with col_q4:
                st.markdown('<div class="question-pill-header">5. Your DOB (Verification)</div>', unsafe_allow_html=True)
                raw_dob = parse_date_safe(row_preset.get("your_dob", current_student["your_dob"] or current_student["dob"]))
                if not raw_dob:
                    raw_dob = date(2004, 1, 1)
                f_your_dob = st.date_input(
                    "Your_DOB",
                    value=raw_dob,
                    label_visibility="collapsed",
                    key=f"enr_date_dob_{current_student['row_num']}"
                )

            with col_q5:
                st.markdown('<div class="question-pill-header">6. Classes In A Week</div>', unsafe_allow_html=True)
                def_cw_val = row_preset.get("classes_in_week", current_student["classes_in_week"]).strip()
                def_cw_idx = 2  # default 3 Days
                if def_cw_val in ENROLLMENT_CLASSES_WEEK_OPTIONS:
                    def_cw_idx = ENROLLMENT_CLASSES_WEEK_OPTIONS.index(def_cw_val)
                f_classes_week = st.selectbox(
                    "Classes In A Week",
                    ENROLLMENT_CLASSES_WEEK_OPTIONS,
                    index=def_cw_idx,
                    label_visibility="collapsed",
                    key=f"enr_sel_cw_{current_student['row_num']}"
                )

            with col_q6:
                st.markdown('<div class="question-pill-header">7. Class Mode</div>', unsafe_allow_html=True)
                def_cm_val = row_preset.get("class_mode", current_student.get("class_mode", "")).strip()
                def_cm_idx = 0
                if def_cm_val:
                    for idx, opt in enumerate(ENROLLMENT_CLASS_MODE_OPTIONS):
                        if opt.lower() == def_cm_val.lower() or (opt.lower() == "hybrid" and "hybr" in def_cm_val.lower()) or (opt.lower() == "dont share" and ("dont" in def_cm_val.lower() or "don't" in def_cm_val.lower())):
                            def_cm_idx = idx
                            break
                f_class_mode = st.selectbox(
                    "Class Mode",
                    ENROLLMENT_CLASS_MODE_OPTIONS,
                    index=def_cm_idx,
                    label_visibility="collapsed",
                    key=f"enr_sel_cm_{current_student['row_num']}"
                )

            with col_q7:
                st.markdown('<div class="question-pill-header">8. Quality Of Classes</div>', unsafe_allow_html=True)
                def_q_val = row_preset.get("quality_of_classes", current_student["quality_of_classes"]).strip()
                def_q_idx = 1  # default Very Good
                if def_q_val in ENROLLMENT_QUALITY_OPTIONS:
                    def_q_idx = ENROLLMENT_QUALITY_OPTIONS.index(def_q_val)
                f_quality = st.selectbox(
                    "Quality Of Classes",
                    ENROLLMENT_QUALITY_OPTIONS,
                    index=def_q_idx,
                    label_visibility="collapsed",
                    key=f"enr_sel_quality_{current_student['row_num']}"
                )

            col_q8, col_q9, col_q10 = st.columns(3)

            with col_q8:
                st.markdown('<div class="question-pill-header">9. Current Educational Status</div>', unsafe_allow_html=True)
                def_edu_val = row_preset.get("current_edu_status", current_student["current_edu_status"] or current_student["education_qualification"]).strip()
                def_edu_idx = 0
                if def_edu_val in ENROLLMENT_EDUCATION_OPTIONS:
                    def_edu_idx = ENROLLMENT_EDUCATION_OPTIONS.index(def_edu_val)
                f_edu_status = st.selectbox(
                    "Current Educational Status",
                    ENROLLMENT_EDUCATION_OPTIONS,
                    index=def_edu_idx,
                    label_visibility="collapsed",
                    key=f"enr_sel_edu_{current_student['row_num']}"
                )

            with col_q9:
                st.markdown('<div class="question-pill-header">10. Monthly Family Income (RS.)</div>', unsafe_allow_html=True)
                f_income = st.text_input(
                    "Monthly Family Income RS.",
                    value=str(row_preset.get("monthly_income", current_student["monthly_income"])),
                    placeholder="E.g. 15000, 20000, Below 10000...",
                    label_visibility="collapsed",
                    key=f"enr_txt_inc_{current_student['row_num']}"
                )

            with col_q10:
                st.markdown('<div class="question-pill-header">11. Satisfied With Conversation?</div>', unsafe_allow_html=True)
                def_sat_val = row_preset.get("satisfied_conversation", current_student["satisfied_conversation"]).strip()
                def_sat_idx = 0
                if def_sat_val in ENROLLMENT_SATISFIED_OPTIONS:
                    def_sat_idx = ENROLLMENT_SATISFIED_OPTIONS.index(def_sat_val)
                f_satisfied = st.selectbox(
                    "Satisfied With Conversation",
                    ENROLLMENT_SATISFIED_OPTIONS,
                    index=def_sat_idx,
                    label_visibility="collapsed",
                    key=f"enr_sel_sat_{current_student['row_num']}"
                )

            st.markdown("<hr style='margin: 18px 0;'>", unsafe_allow_html=True)

            # ----------------------------------------------------------------------
            # Section 2: Employment & Career Interests
            # ----------------------------------------------------------------------
            st.markdown("""
                <div style="font-weight: 800; color: #0f4c81; font-size: 1.08rem; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                    <span>💼 Section 2: Employment & Career Interests</span>
                </div>
            """, unsafe_allow_html=True)

            col_w1, col_w2 = st.columns(2)
            with col_w1:
                st.markdown('<div class="question-pill-header">12. Interest In Job?</div>', unsafe_allow_html=True)
                def_ij_val = row_preset.get("interest_in_job", current_student["interest_in_job"])
                def_ij_idx = get_tri_option_index(def_ij_val, default="Yes")
                f_job_interest = st.radio(
                    "Interest In Job",
                    ENROLLMENT_TRI_STATE_OPTIONS,
                    index=def_ij_idx,
                    horizontal=True,
                    label_visibility="collapsed",
                    key=f"enr_rad_ij_{current_student['row_num']}"
                )

            with col_w2:
                st.markdown('<div class="question-pill-header">13. Present Working Status (Currently Employed)?</div>', unsafe_allow_html=True)
                def_ws_val = row_preset.get("present_working_status", current_student["present_working_status"])
                def_ws_idx = get_tri_option_index(def_ws_val, default="No")
                f_working_status = st.radio(
                    "Present Working Status",
                    ["Yes", "No", "dont share"],
                    index=def_ws_idx,
                    horizontal=True,
                    label_visibility="collapsed",
                    key=f"enr_rad_ws_{current_student['row_num']}"
                )

            # Conditional fields if Student is working
            if f_working_status == "Yes":
                st.markdown("""
                    <div style="background: #f0fdf4; border: 1.5px solid #86efac; border-left: 5px solid #16a34a; padding: 10px 14px; border-radius: 8px; margin: 10px 0; color: #166534; font-size: 0.92rem; font-weight: 700;">
                        💼 Student is Currently Working — Please capture Employment & Job Details:
                    </div>
                """, unsafe_allow_html=True)

                c_emp1, c_emp2, c_emp3 = st.columns(3)
                with c_emp1:
                    f_comp_name = st.text_input(
                        "Company Name",
                        value=row_preset.get("company_name", current_student["company_name"]),
                        placeholder="E.g. TCS, Reliance, Retail...",
                        key=f"enr_txt_comp_{current_student['row_num']}"
                    )
                with c_emp2:
                    f_salary = st.text_input(
                        "Salary (RS.)",
                        value=str(row_preset.get("salary", current_student["salary"])),
                        placeholder="E.g. 15000, 18000...",
                        key=f"enr_txt_sal_{current_student['row_num']}"
                    )
                with c_emp3:
                    def_pf_val = row_preset.get("part_full_time", current_student["part_full_time"]).strip().title()
                    def_pf_idx = 0 if def_pf_val == "Full Time" else (1 if def_pf_val == "Part Time" else 0)
                    f_part_full = st.selectbox(
                        "Part Time / Full Time",
                        ["Full Time", "Part Time"],
                        index=def_pf_idx,
                        key=f"enr_sel_pf_{current_student['row_num']}"
                    )

                c_emp4, c_emp5, c_emp6 = st.columns(3)
                with c_emp4:
                    def_hm_val = row_preset.get("how_many_months", current_student["how_many_months"]).strip()
                    def_hm_idx = 2  # default 2 Months
                    if def_hm_val in ENROLLMENT_MONTHS_OPTIONS:
                        def_hm_idx = ENROLLMENT_MONTHS_OPTIONS.index(def_hm_val)
                    f_months_work = st.selectbox(
                        "How Many Months Working?",
                        ENROLLMENT_MONTHS_OPTIONS,
                        index=def_hm_idx,
                        key=f"enr_sel_hm_{current_student['row_num']}"
                    )
                with c_emp5:
                    def_lj_val = row_preset.get("left_job_after_joining", current_student["left_job_after_joining"]).strip().capitalize() or "No"
                    def_lj_idx = 0 if def_lj_val == "Yes" else (1 if def_lj_val == "No" else 2)
                    f_left_job = st.radio(
                        "Did They Left Job After Joining Course?",
                        ["Yes", "No", "N/A"],
                        index=def_lj_idx,
                        horizontal=True,
                        key=f"enr_rad_lj_{current_student['row_num']}"
                    )
                with c_emp6:
                    def_wj_val = row_preset.get("why_joined_course", current_student["why_joined_course"]).strip()
                    def_wj_idx = 0
                    if def_wj_val in ENROLLMENT_WHY_JOINED_OPTIONS:
                        def_wj_idx = ENROLLMENT_WHY_JOINED_OPTIONS.index(def_wj_val)
                    f_why_joined = st.selectbox(
                        "Why They Joined Course, If Stu Working?",
                        ENROLLMENT_WHY_JOINED_OPTIONS,
                        index=def_wj_idx,
                        key=f"enr_sel_wj_{current_student['row_num']}"
                    )
            else:
                f_comp_name = ""
                f_salary = ""
                f_part_full = ""
                f_months_work = ""
                f_left_job = ""
                f_why_joined = ""

            st.markdown("<hr style='margin: 18px 0;'>", unsafe_allow_html=True)

            # ----------------------------------------------------------------------
            # Section 3: Final Disposition & Remarks
            # ----------------------------------------------------------------------
            st.markdown("""
                <div style="font-weight: 800; color: #0f4c81; font-size: 1.08rem; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                    <span>📋 Section 3: Final Disposition & Remarks</span>
                </div>
            """, unsafe_allow_html=True)

            c_rem1, c_rem2 = st.columns([1.5, 1.0])
            with c_rem1:
                existing_er = row_preset.get("enroll_remarks", current_student["enroll_remarks"]).strip()
                def_er_idx = 0
                if existing_er in ENROLLMENT_REMARKS_YES_OPTIONS:
                    def_er_idx = ENROLLMENT_REMARKS_YES_OPTIONS.index(existing_er)
                f_enroll_remarks = st.selectbox(
                    "Enroll Remarks (Final Disposition)",
                    ENROLLMENT_REMARKS_YES_OPTIONS,
                    index=def_er_idx,
                    key=f"enr_sel_er_{current_student['row_num']}"
                )
            with c_rem2:
                st.date_input(
                    "Verification Date",
                    value=date.today(),
                    disabled=True,
                    key=f"enr_date_vdate_{current_student['row_num']}"
                )

            c_rem3, c_rem4 = st.columns(2)
            with c_rem3:
                f_remarks_2 = st.text_input(
                    "Remarks 2 (SPOC Notes)",
                    value=row_preset.get("remarks_2", current_student["remarks_2"]),
                    key=f"enr_txt_rem2_{current_student['row_num']}",
                    placeholder="E.g. Verified with student, details confirmed..."
                )
            with c_rem4:
                f_remarks_3 = st.text_input(
                    "Remarks 3 (Supervisor / Center Notes)",
                    value=row_preset.get("remarks_3", current_student["remarks_3"]),
                    key=f"enr_txt_rem3_{current_student['row_num']}",
                    placeholder="Optional supervisor notes..."
                )

            st.markdown("<br>", unsafe_allow_html=True)
            btn_submit_label = f"💾 Update & Insert Enrollment Verification (Row #{current_student['row_num']})" if (is_edit_mode or is_already_verified) else "🎯 Submit Enrollment Verification"
            if st.button(btn_submit_label, type="primary", use_container_width=True, key=f"enr_btn_submit_{current_student['row_num']}"):
                is_blank_exit = f_enroll_remarks in ENROLLMENT_CONTACTED_BLANK_REMARKS
                payload = [
                    "Yes",                                           # R: Contactable
                    "" if is_blank_exit else f_class_started,        # S: Class started (Yes/No)
                    "" if is_blank_exit else f_got_info,             # T: Got information about Anudip
                    "" if is_blank_exit else f_referral_ok,          # U: Referral Person Name(Yes/No)
                    "" if is_blank_exit else (f_referral_name_fill.strip() if f_referral_ok == "Yes" else ""), # V: Please fill the Name
                    "" if is_blank_exit else str(f_your_dob),        # W: Your_DOB
                    "" if is_blank_exit else str(f_income).strip(),  # X: Monthly Family Income RS.
                    "" if is_blank_exit else f_satisfied,            # Y: Satisfied With Conversation
                    "" if is_blank_exit else f_classes_week,         # Z: Classes In A Week
                    "" if is_blank_exit else f_class_mode,           # AA: Class Mode
                    "" if is_blank_exit else f_quality,              # AB: Quality Of Classes
                    "" if is_blank_exit else f_edu_status,           # AC: Current Educational Status
                    str(date.today()),                               # AD: Verification Date
                    "" if is_blank_exit else f_job_interest,         # AE: Interest In Job
                    "" if is_blank_exit else f_working_status,       # AF: Present Working Status
                    "" if is_blank_exit else (f_comp_name.strip() if f_working_status == "Yes" else ""), # AG: COMPANY NAME
                    "" if is_blank_exit else (str(f_salary).strip() if f_working_status == "Yes" else ""), # AH: Salary
                    "" if is_blank_exit else (f_part_full if f_working_status == "Yes" else ""),# AI: Part Time /Full Time
                    "" if is_blank_exit else (f_months_work if f_working_status == "Yes" else ""), # AJ: How Many Months Working
                    "" if is_blank_exit else (f_left_job if f_working_status == "Yes" else ""), # AK: Did They Left The Job After Joining Course
                    "" if is_blank_exit else (f_why_joined if f_working_status == "Yes" else ""), # AL: Why They Joined Course, If Stu Working
                    f_enroll_remarks,                                # AM: Enroll Remarks
                    f_remarks_2.strip(),                             # AN: Remarks 2
                    f_remarks_3.strip()                              # AO: Remarks 3
                ]

                try:
                    p_cid = current_student.get("call_id", "3300")
                    current_student["call_status"] = "Done"

                    # 1. Update in-memory session rows immediately (Sub-millisecond)
                    update_in_memory_enrollment_row(current_student['row_num'], payload, call_status="Done", call_id=p_cid)

                    # 2. Asynchronous background sync to Google Sheets & local CSV
                    dispatch_enrollment_sync(enrollment_ws, current_student['row_num'], payload, call_status="Done", call_id=p_cid)

                    # 3. Update session live history
                    st.session_state.enrollment_live_history.insert(0, (current_student['row_num'], list(payload)))
                    st.session_state.enrollment_live_history = st.session_state.enrollment_live_history[:25]
                    st.session_state.pop("enrollment_editing_row", None)

                    # 4. Instant UI Toast
                    st.toast(f"✅ Target #{current_q_idx + 1} ({current_student['student_name']}) saved successfully in Google Sheets!", icon="🎯")

                    # 5. Advance queue index and save progress
                    if current_q_idx + 1 < total_assigned_queue:
                        st.session_state.enrollment_queue_index = current_q_idx + 1
                        next_s = active_queue_students[current_q_idx + 1]
                        save_enrollment_progress(current_spoc, current_q_idx + 1, next_s["contact_number"], active_call_index=st.session_state.get("enrollment_active_call_index", 0))

                    # 6. Instant UI re-render
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error saving: {ex}")

    st.markdown('</div>', unsafe_allow_html=True)

    # ==========================================================================
    # 🕒 RECENT ENROLLMENT VERIFICATIONS (LIVE AUDIT TRAIL & EDIT BUTTONS)
    # ==========================================================================
    if st.session_state.enrollment_live_history:
        st.markdown('<div class="profile-card-enhanced">', unsafe_allow_html=True)
        st.markdown("""
            <div style="font-weight: 800; color: #0f4c81; font-size: 1.05rem; margin-bottom: 8px;">
                🕒 Recently Verified in This Session (Live Audit Trail)
            </div>
        """, unsafe_allow_html=True)

        for hist_row_num, hist_payload in st.session_state.enrollment_live_history[:8]:
            hist_student = next((s for s in all_enrollment_students if s["row_num"] == hist_row_num), None)
            if hist_student:
                h_c1, h_c2, h_c3, h_c4 = st.columns([1.0, 2.8, 2.5, 1.2])
                with h_c1:
                    is_cont_yes = hist_payload[0] == "Yes"
                    b_color = "#16a34a" if is_cont_yes else "#dc2626"
                    st.markdown(f"<span style='color:{b_color}; font-weight:800;'>Row #{hist_row_num}</span>", unsafe_allow_html=True)
                with h_c2:
                    st.markdown(f"<b>{hist_student['student_name']}</b> <small>({hist_student['student_code']})</small>", unsafe_allow_html=True)
                with h_c3:
                    stat_txt = f"Contactable: {hist_payload[0]}"
                    if hist_payload[0] == "No":
                        stat_txt += f" • {hist_payload[21]}"
                    elif hist_payload[21] in ENROLLMENT_CONTACTED_BLANK_REMARKS:
                        stat_txt += f" • {hist_payload[21]}"
                    else:
                        stat_txt += f" • Working: {hist_payload[14]}"
                    st.markdown(f"<small style='color: #475569;'>{stat_txt}</small>", unsafe_allow_html=True)
                with h_c4:
                    if st.button("✏️ Edit", key=f"enr_edit_hist_{hist_row_num}", use_container_width=True):
                        # Find index in current active queue
                        match_q = next((i for i, s in enumerate(active_queue_students) if s["row_num"] == hist_row_num), None)
                        if match_q is not None:
                            st.session_state.enrollment_queue_index = match_q
                        st.session_state.enrollment_editing_row = hist_row_num
                        # Preset values into session state
                        st.session_state[f"enr_preset_{hist_row_num}"] = {
                            "contactable": hist_payload[0],
                            "class_started": hist_payload[1],
                            "got_info_anudip": hist_payload[2],
                            "referral_person_ok": hist_payload[3],
                            "referral_name_fill": hist_payload[4],
                            "your_dob": hist_payload[5],
                            "monthly_income": hist_payload[6],
                            "satisfied_conversation": hist_payload[7],
                            "classes_in_week": hist_payload[8],
                            "class_mode": hist_payload[9],
                            "quality_of_classes": hist_payload[10],
                            "current_edu_status": hist_payload[11],
                            "interest_in_job": hist_payload[13],
                            "present_working_status": hist_payload[14],
                            "company_name": hist_payload[15],
                            "salary": hist_payload[16],
                            "part_full_time": hist_payload[17],
                            "how_many_months": hist_payload[18],
                            "left_job_after_joining": hist_payload[19],
                            "why_joined_course": hist_payload[20],
                            "enroll_remarks": hist_payload[21],
                            "remarks_2": hist_payload[22],
                            "remarks_3": hist_payload[23] if len(hist_payload) > 23 else "",
                            "nocont_reason": hist_payload[21] if hist_payload[0] == "No" else "",
                            "call_outcome": hist_payload[21] if hist_payload[0] == "Yes" and hist_payload[21] in ENROLLMENT_CONTACTED_BLANK_REMARKS else "Full Verification (Complete Survey)"
                        }
                        st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
