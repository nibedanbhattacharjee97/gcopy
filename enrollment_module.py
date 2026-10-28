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

# Suppress Streamlit deprecation warnings for clean console logs (resolves Picture 3 issue)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*st\\.components\\.v1\\.html.*")
warnings.filterwarnings("ignore", message=".*st\\.iframe.*")

PROGRESS_ENROLLMENT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spoc_enrollment_progress.json")
LOCAL_ENROLLMENT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "enrollment_data.csv")
LOCAL_ENROLLMENT_EXCEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Enrollment_Verification.xlsx")
DATA_CACHE_TTL = 900  # 15 minutes TTL for zero API rate limit and lightning speed

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

ENROLLMENT_REMARKS_YES_OPTIONS = [
    "Successfully Verified / All Details Confirmed",
    "Enrolled & Attending Regular Classes",
    "Interested in Placement",
    "Course In Progress",
    "Left The Course",
    "Cource Complete",
    "Confirmed Name & Disconnected.",
    "Disconnected,Did'nt Share All Information."
]

# Master 39 Headers
ENROLLMENT_HEADERS = [
    "Called By", "Batch Code", "Course Name", "Start Date", "Student Code",
    "Student Name", "DOB", "Gender", "Mobile No.", "Alt Mobile No",
    "Center Code", "State", "Come To Know", "Referral Person Name",
    "Education Qualification", "Funder Name", "Enrollment Status",
    # Yellow Marked Verification Columns (18 to 39 / R to AM)
    "Contactable", "Class started (Yes/No)", "Got information about Anudip",
    "Referral Person Name(Yes/No)", "Your_DOB", "Monthly Family Income RS.",
    "Satisfied With Conversation", "Classes In A Week", "Quality Of Classes",
    "Current Educational Status", "Verification Date", "Interest In Job",
    "Present Working Status", "COMPANY NAME", "Salary", "Part Time /Full Time",
    "How Many Months Working", "Did They Left The Job After Joining Course",
    "Why They Joined Course, If Stu Working", "Enroll Remarks", "Remarks 2", "Remarks 3"
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
    v = (val or "").strip()
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

def update_local_enrollment_row(row_num, payload):
    """Updates local CSV and session cache for zero data loss."""
    try:
        if os.path.exists(LOCAL_ENROLLMENT_CSV):
            with open(LOCAL_ENROLLMENT_CSV, "r", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            if 0 < row_num <= len(rows):
                idx = row_num - 1
                curr = list(rows[idx])
                if len(curr) < 39:
                    curr.extend([""] * (39 - len(curr)))
                for i, val in enumerate(payload):
                    curr[17 + i] = str(val)
                rows[idx] = curr
                with open(LOCAL_ENROLLMENT_CSV, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerows(rows)
        if "custom_enrollment_rows" in st.session_state and st.session_state.custom_enrollment_rows:
            crows = st.session_state.custom_enrollment_rows
            if 0 < row_num <= len(crows):
                idx = row_num - 1
                curr = list(crows[idx])
                if len(curr) < 39:
                    curr.extend([""] * (39 - len(curr)))
                for i, val in enumerate(payload):
                    curr[17 + i] = str(val)
                crows[idx] = curr
                st.session_state.custom_enrollment_rows = crows
    except Exception:
        pass

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
                row_39 = [str(c) if c is not None else "" for c in r[:39]]
                if len(row_39) < 39:
                    row_39.extend([""] * (39 - len(row_39)))
                rows.append(row_39)
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
    Matches the 39-column layout (Columns 1-17 Static, Columns 18-39 Yellow Marked).
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
            padded = list(r) + [""] * max(0, 42 - len(r))
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
                # Yellow Marked Verified columns (18 to 39 / R to AM)
                "contactable": padded[17].strip(),
                "class_started": padded[18].strip(),
                "got_info_anudip": padded[19].strip(),
                "referral_person_ok": padded[20].strip(),
                "your_dob": padded[21].strip(),
                "monthly_income": padded[22].strip(),
                "satisfied_conversation": padded[23].strip(),
                "classes_in_week": padded[24].strip(),
                "quality_of_classes": padded[25].strip(),
                "current_edu_status": padded[26].strip(),
                "verification_date": padded[27].strip(),
                "interest_in_job": padded[28].strip(),
                "present_working_status": padded[29].strip(),
                "company_name": padded[30].strip(),
                "salary": padded[31].strip(),
                "part_full_time": padded[32].strip(),
                "how_many_months": padded[33].strip(),
                "left_job_after_joining": padded[34].strip(),
                "why_joined_course": padded[35].strip(),
                "enroll_remarks": padded[36].strip(),
                "remarks_2": padded[37].strip(),
                "remarks_3": padded[38].strip() if len(padded) > 38 else ""
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
        st.caption("Click **Jump** next to any student to dial immediately:")
        preview_rows = fresh_items[:100]
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
        for s in no_items[:100]:
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
        headers = ENROLLMENT_HEADERS

    if live_history is None:
        live_history = []
    live_map = {r_num: r_data for r_num, r_data in live_history}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)

    for s in students_subset:
        r_num = s["row_num"]
        live_entry = live_map.get(r_num)
        if live_entry:
            pad_live = list(live_entry) + [""] * max(0, 22 - len(live_entry))
            row = [
                s["called_by"], s["batch_code"], s["course_name"], s["start_date"],
                s["student_code"], s["student_name"], s["dob"], s["gender"],
                s["contact_number"], s["alt_contact_number"], s["centre_code"],
                s["state"], s["come_to_know"], s["referral_person_name"],
                s["education_qualification"], s["funder_name"], s["enrollment_status"],
                # Yellow Marked Verified columns
                pad_live[0], pad_live[1], pad_live[2], pad_live[3], pad_live[4],
                pad_live[5], pad_live[6], pad_live[7], pad_live[8], pad_live[9],
                pad_live[10], pad_live[11], pad_live[12], pad_live[13], pad_live[14],
                pad_live[15], pad_live[16], pad_live[17], pad_live[18], pad_live[19],
                pad_live[20], pad_live[21]
            ]
        else:
            row = [
                s["called_by"], s["batch_code"], s["course_name"], s["start_date"],
                s["student_code"], s["student_name"], s["dob"], s["gender"],
                s["contact_number"], s["alt_contact_number"], s["centre_code"],
                s["state"], s["come_to_know"], s["referral_person_name"],
                s["education_qualification"], s["funder_name"], s["enrollment_status"],
                # Yellow Marked Verified columns
                s["contactable"], s["class_started"], s["got_info_anudip"],
                s["referral_person_ok"], s["your_dob"], s["monthly_income"],
                s["satisfied_conversation"], s["classes_in_week"], s["quality_of_classes"],
                s["current_edu_status"], s["verification_date"], s["interest_in_job"],
                s["present_working_status"], s["company_name"], s["salary"],
                s["part_full_time"], s["how_many_months"], s["left_job_after_joining"],
                s["why_joined_course"], s["enroll_remarks"], s["remarks_2"], s["remarks_3"]
            ]
        writer.writerow(row)

    return output.getvalue().encode("utf-8")

def render_enrollment_sidebar_download(all_enrollment_students, current_spoc, is_admin=False, live_history=None, all_rows=None):
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
                            new_rows.append([str(c) if c is not None else "" for c in row[:39]])

                if new_rows and len(new_rows) > 1:
                    st.session_state.custom_enrollment_rows = new_rows
                    fetch_enrollment_master_data.clear()
                    st.success(f"✅ Loaded {len(new_rows)-1} students from uploaded file!")
                    if st.button("Apply & Refresh Queue", key="enr_apply_upload_btn", use_container_width=True):
                        st.rerun()
            except Exception as e:
                st.error(f"Error reading file: {e}")

    live_map = {r_num: r_data[0].strip().lower() for r_num, r_data in live_history if len(r_data) > 0}

    all_spocs = sorted(list({s["called_by"].strip().title() for s in all_enrollment_students if s["called_by"]}))

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

    yes_students, no_students = [], []
    for s in target_students:
        cont = live_map.get(s["row_num"], s["contactable"].strip().lower())
        if cont == "yes":
            yes_students.append(s)
        elif cont == "no":
            no_students.append(s)

    total_students = yes_students + no_students
    yes_cnt, no_cnt, total_cnt = len(yes_students), len(no_students), len(total_students)

    now_str = datetime.now().strftime("%Y%m%d_%H%M")
    sheet_headers = ENROLLMENT_HEADERS

    yes_csv = build_enrollment_csv(yes_students, live_history, headers=sheet_headers)
    st.sidebar.download_button(
        label=f"📥 Download 'Yes' Data ({yes_cnt})",
        data=yes_csv,
        file_name=f"Enrollment_Yes_Data_{safe_name}_{now_str}.csv",
        mime="text/csv",
        use_container_width=True,
        key=f"sb_dl_enr_yes_{safe_name}"
    )

    no_csv = build_enrollment_csv(no_students, live_history, headers=sheet_headers)
    st.sidebar.download_button(
        label=f"📥 Download 'No' Data ({no_cnt})",
        data=no_csv,
        file_name=f"Enrollment_No_Data_{safe_name}_{now_str}.csv",
        mime="text/csv",
        use_container_width=True,
        key=f"sb_dl_enr_no_{safe_name}"
    )

    total_csv = build_enrollment_csv(total_students, live_history, headers=sheet_headers)
    st.sidebar.download_button(
        label=f"📥 Download 'Total' Data ({total_cnt})",
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

    all_rows = fetch_enrollment_master_data(enrollment_ws)
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
        all_rows=all_rows
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
        fetch_enrollment_master_data.clear()
        st.cache_data.clear()
        st.toast("Database cache refreshed from Google Sheets!", icon="🔄")
        st.rerun()

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

    status_badge_html = f"""
        <span style="background: #fef3c7; color: #92400e; border: 1.5px solid #fcd34d; padding: 4px 12px; border-radius: 6px; font-weight: 800; font-size: 0.88rem;">
            ✏️ EDIT & UPDATE MODE (Row #{current_student['row_num']})
        </span>
    """ if (is_edit_mode or is_already_verified) else f"""
        <span style="background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.85rem;">
            ✨ FRESH CALL VERIFICATION (Target #{current_q_idx + 1})
        </span>
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
            with st.spinner("⚡ High Speed Sync to Google Sheets..."):
                payload = [
                    "No",                           # R: Contactable
                    "",                             # S: Class started (Yes/No)
                    "",                             # T: Got information about Anudip
                    "",                             # U: Referral Person Name(Yes/No)
                    "",                             # V: Your_DOB
                    "",                             # W: Monthly Family Income RS.
                    "",                             # X: Satisfied With Conversation
                    "",                             # Y: Classes In A Week
                    "",                             # Z: Quality Of Classes
                    "",                             # AA: Current Educational Status
                    str(date.today()),              # AB: Verification Date
                    "",                             # AC: Interest In Job
                    "",                             # AD: Present Working Status
                    "",                             # AE: COMPANY NAME
                    "",                             # AF: Salary
                    "",                             # AG: Part Time /Full Time
                    "",                             # AH: How Many Months Working
                    "",                             # AI: Did They Left The Job After Joining Course
                    "",                             # AJ: Why They Joined Course, If Stu Working
                    f_nocont_reason,                # AK: Enroll Remarks
                    f_remarks_2_no.strip(),         # AL: Remarks 2
                    f_remarks_3_no.strip()          # AM: Remarks 3
                ]

                try:
                    if enrollment_ws:
                        enrollment_ws.update(values=[payload], range_name=f"R{current_student['row_num']}:AM{current_student['row_num']}")
                    update_local_enrollment_row(current_student['row_num'], payload)
                    fetch_enrollment_master_data.clear()

                    st.session_state.enrollment_live_history.insert(0, (current_student['row_num'], list(payload)))
                    st.session_state.enrollment_live_history = st.session_state.enrollment_live_history[:25]
                    st.session_state.pop("enrollment_editing_row", None)

                    st.toast(f"✅ Saved Target #{current_q_idx + 1} ({current_student['student_name']}) as Not Contactable!", icon="🚫")

                    if current_q_idx + 1 < total_assigned_queue:
                        st.session_state.enrollment_queue_index = current_q_idx + 1
                        next_s = active_queue_students[current_q_idx + 1]
                        save_enrollment_progress(current_spoc, current_q_idx + 1, next_s["contact_number"], active_call_index=st.session_state.get("enrollment_active_call_index", 0))

                    time.sleep(0.3)
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error saving to Google Sheets: {ex}")

    # --------------------------------------------------------------------------
    # ✅ CONDITION: IF CONTACTABLE == YES -> Complete Enrollment Verification Form
    # --------------------------------------------------------------------------
    else:
        st.markdown("<div style='margin-top: 14px;'></div>", unsafe_allow_html=True)

        # ----------------------------------------------------------------------
        # Section 1: Course & Training Details
        # ----------------------------------------------------------------------
        st.markdown("""
            <div style="font-weight: 800; color: #0f4c81; font-size: 1.08rem; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                <span>🎓 Section 1: Course & Training Details</span>
            </div>
        """, unsafe_allow_html=True)

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
            def_ref_val = row_preset.get("referral_person_ok", current_student["referral_person_ok"]).strip().capitalize() or "Yes"
            def_ref_idx = 0 if def_ref_val == "Yes" else (1 if def_ref_val == "No" else 2)
            f_referral_ok = st.radio(
                "Referral Person Name(Yes/No)",
                ["Yes", "No", "N/A"],
                index=def_ref_idx,
                horizontal=True,
                label_visibility="collapsed",
                key=f"enr_rad_ref_{current_student['row_num']}"
            )

        col_q4, col_q5, col_q6 = st.columns(3)

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
            st.markdown('<div class="question-pill-header">7. Quality Of Classes</div>', unsafe_allow_html=True)
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

        col_q7, col_q8, col_q9 = st.columns(3)

        with col_q7:
            st.markdown('<div class="question-pill-header">8. Current Educational Status</div>', unsafe_allow_html=True)
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

        with col_q8:
            st.markdown('<div class="question-pill-header">9. Monthly Family Income (RS.)</div>', unsafe_allow_html=True)
            f_income = st.text_input(
                "Monthly Family Income RS.",
                value=str(row_preset.get("monthly_income", current_student["monthly_income"])),
                placeholder="E.g. 15000, 20000, Below 10000...",
                label_visibility="collapsed",
                key=f"enr_txt_inc_{current_student['row_num']}"
            )

        with col_q9:
            st.markdown('<div class="question-pill-header">10. Satisfied With Conversation?</div>', unsafe_allow_html=True)
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
            st.markdown('<div class="question-pill-header">11. Interest In Job?</div>', unsafe_allow_html=True)
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
            st.markdown('<div class="question-pill-header">12. Present Working Status (Currently Employed)?</div>', unsafe_allow_html=True)
            def_ws_val = row_preset.get("present_working_status", current_student["present_working_status"]).strip().capitalize()
            def_ws_idx = 0 if def_ws_val == "Yes" else 1
            f_working_status = st.radio(
                "Present Working Status",
                ["Yes", "No"],
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
        btn_submit_label = f"💾 Update & Insert Enrollment Verification (Row #{current_student['row_num']})" if (is_edit_mode or is_already_verified) else "💾 Submit Enrollment Verification"
        if st.button(btn_submit_label, type="primary", use_container_width=True, key=f"enr_btn_submit_{current_student['row_num']}"):
            with st.spinner("⚡ High Speed Sync to Google Sheets..."):
                payload = [
                    "Yes",                                           # R: Contactable
                    f_class_started,                                 # S: Class started (Yes/No)
                    f_got_info,                                      # T: Got information about Anudip
                    f_referral_ok,                                   # U: Referral Person Name(Yes/No)
                    str(f_your_dob),                                 # V: Your_DOB
                    str(f_income).strip(),                           # W: Monthly Family Income RS.
                    f_satisfied,                                     # X: Satisfied With Conversation
                    f_classes_week,                                  # Y: Classes In A Week
                    f_quality,                                       # Z: Quality Of Classes
                    f_edu_status,                                    # AA: Current Educational Status
                    str(date.today()),                               # AB: Verification Date
                    f_job_interest,                                  # AC: Interest In Job
                    f_working_status,                                # AD: Present Working Status
                    f_comp_name.strip() if f_working_status == "Yes" else "", # AE: COMPANY NAME
                    str(f_salary).strip() if f_working_status == "Yes" else "", # AF: Salary
                    f_part_full if f_working_status == "Yes" else "",# AG: Part Time /Full Time
                    f_months_work if f_working_status == "Yes" else "", # AH: How Many Months Working
                    f_left_job if f_working_status == "Yes" else "", # AI: Did They Left The Job After Joining Course
                    f_why_joined if f_working_status == "Yes" else "", # AJ: Why They Joined Course, If Stu Working
                    f_enroll_remarks,                                # AK: Enroll Remarks
                    f_remarks_2.strip(),                             # AL: Remarks 2
                    f_remarks_3.strip()                              # AM: Remarks 3
                ]

                try:
                    if enrollment_ws:
                        enrollment_ws.update(values=[payload], range_name=f"R{current_student['row_num']}:AM{current_student['row_num']}")
                    update_local_enrollment_row(current_student['row_num'], payload)
                    fetch_enrollment_master_data.clear()

                    st.session_state.enrollment_live_history.insert(0, (current_student['row_num'], list(payload)))
                    st.session_state.enrollment_live_history = st.session_state.enrollment_live_history[:25]
                    st.session_state.pop("enrollment_editing_row", None)

                    st.toast(f"✅ Target #{current_q_idx + 1} ({current_student['student_name']}) saved successfully in Google Sheets!", icon="🎯")

                    if current_q_idx + 1 < total_assigned_queue:
                        st.session_state.enrollment_queue_index = current_q_idx + 1
                        next_s = active_queue_students[current_q_idx + 1]
                        save_enrollment_progress(current_spoc, current_q_idx + 1, next_s["contact_number"], active_call_index=st.session_state.get("enrollment_active_call_index", 0))

                    time.sleep(0.3)
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error saving to Google Sheets: {ex}")

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
                        stat_txt += f" • {hist_payload[19]}"
                    else:
                        stat_txt += f" • Working: {hist_payload[12]}"
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
                            "your_dob": hist_payload[4],
                            "monthly_income": hist_payload[5],
                            "satisfied_conversation": hist_payload[6],
                            "classes_in_week": hist_payload[7],
                            "quality_of_classes": hist_payload[8],
                            "current_edu_status": hist_payload[9],
                            "interest_in_job": hist_payload[11],
                            "present_working_status": hist_payload[12],
                            "company_name": hist_payload[13],
                            "salary": hist_payload[14],
                            "part_full_time": hist_payload[15],
                            "how_many_months": hist_payload[16],
                            "left_job_after_joining": hist_payload[17],
                            "why_joined_course": hist_payload[18],
                            "enroll_remarks": hist_payload[19],
                            "remarks_2": hist_payload[20],
                            "remarks_3": hist_payload[21] if len(hist_payload) > 21 else "",
                            "nocont_reason": hist_payload[19] if hist_payload[0] == "No" else ""
                        }
                        st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
