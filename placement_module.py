import streamlit as st
import streamlit.components.v1 as components
from datetime import date, datetime
import json
import os
import re
import time
import urllib.parse

PROGRESS_PLACEMENT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spoc_placement_progress.json")
DATA_CACHE_TTL = 900  # 15 minutes TTL for zero API rate limit and lightning speed

# ==============================================================================
# 🎯 DROPDOWN CONSTANTS (MATCHING PLACEMENT EXCEL & USER SPECIFICATION - PICTURE 4)
# ==============================================================================

# Contactable == Yes Retention Status options
PLACEMENT_RETENTION_OPTIONS_YES = [
    "Working in same job",
    "Not_working_at_all",
    "Working in different job",
    "Confirmed Name But Didn't Share Any Information.",
    "Left_The_Job",
    "Will joined after some days"
]

# Contactable == No Retention Status option
PLACEMENT_RETENTION_OPTIONS_NO = [
    "Unable_to_track"
]

# All options combined for backward compatibility
PLACEMENT_RETENTION_OPTIONS = PLACEMENT_RETENTION_OPTIONS_YES + PLACEMENT_RETENTION_OPTIONS_NO

# Image 4 - Column 2: Unable_to_track reasons (When Contactable == No)
PLACEMENT_UNABLE_TO_TRACK_OPTIONS = [
    "Did not respond to our call",
    "Network issue",
    "Not a student of Anudip",
    "Language issue",
    "Switched off",
    "Incoming Call Is Not Avialable",
    "Wrong Number"
]

# Image 4 - Column 1: Not_working_at_all reasons (First-level under Not_working_at_all)
PLACEMENT_NOT_WORKING_OPTIONS = [
    "Did_not_joined_job_due_to_personal_issue",
    "Did_not_joined_job_due_to_profile_issue",
    "Did not get any information from the employer",
    "Did not get selected",
    "Did Not Attend Any Interview"
]

# Image 4 - Column 3: Did_not_joined_job_due_to_personal_issue sub-reasons
PLACEMENT_NOT_JOINED_PERSONAL_OPTIONS = [
    "Distance Issue",
    "As The Student Is Pursuing 1st Year",
    "As The Student Is Pursuing 2nd Year",
    "As The Student Is Pursuing 3rd Year",
    "Medical Issue"
]

# Image 4 - Column 4: Did_not_joined_job_due_to_profile_issue sub-reasons
PLACEMENT_NOT_JOINED_PROFILE_OPTIONS = [
    "Issue Regarding Job Role",
    "Issue Regarding Salary"
]

# Image 4 - Column 5: Left_The_Job reasons
PLACEMENT_LEFT_JOB_OPTIONS = [
    "Distance Issue",
    "Pursuing Higher Studies.",
    "Job Profile Did Not Match",
    "Family Issue",
    "Medical & Health Issue",
    "Don't Want To Share",
    "Casually Left The Job.",
    "Salary Issue",
    "Heavy Workload",
    "Unhealthy Work Environment.",
    "Office Timing",
    "Night Shift",
    "Internship/Project Completed",
    "Company Closed"
]

PLACEMENT_CONFIRMED_NAME_OPTIONS = [
    "Confirmed Name But Didn't Share Any Information.",
    "Refused to share job details",
    "Student Busy / Call Later"
]

PLACEMENT_WILL_JOIN_OPTIONS = [
    "Offer Letter Received - Awaiting DOJ",
    "Selected - Date of Joining Pending",
    "Under Background Verification",
    "Personal / Exam Delay Before Joining"
]

PLACEMENT_WORKING_REMARKS_OPTIONS = [
    "N/A - Currently Working",
    "Working Satisfactorily",
    "Looking for Better Opportunity"
]

PLACEMENT_MONTHS_OPTIONS = [
    "1 Month", "2 Months", "3 Months", "4 Months", "5 Months", "6 Months",
    "7 Months", "8 Months", "9 Months", "10 Months", "11 Months", "12 Months",
    "Less than 1 Months", "More than 12 months"
]

PLACEMENT_SATISFIED_OPTIONS = [
    "Yes",
    "No",
    "Don't want to share",
    "Don't know"
]

PLACEMENT_NPS_OPTIONS = [
    "10", "9", "8", "7", "6", "5", "4", "3", "2", "1", "0", "Don't Want To Share"
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

def get_placement_highest_verified_index(student_list):
    """
    Returns the index of the highest student row in student_list that has already been verified
    (contactable is 'Yes' or 'No'). Returns -1 if none have been verified yet.
    """
    if not student_list:
        return -1
    highest = -1
    for idx, s in enumerate(student_list):
        cont = str(s.get("contactable", "")).strip().lower()
        if cont in ["yes", "no"]:
            highest = idx
    return highest

# ==============================================================================
# 💾 PERSISTENCE & QUEUE PROGRESS FOR PLACEMENT
# ==============================================================================
def load_all_placement_progress():
    if os.path.exists(PROGRESS_PLACEMENT_FILE):
        try:
            with open(PROGRESS_PLACEMENT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_placement_progress(spoc_name, queue_index, phone="", active_call_index=None):
    if not spoc_name:
        return
    try:
        data = load_all_placement_progress()
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
        with open(PROGRESS_PLACEMENT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def get_saved_placement_index(spoc_name, student_list):
    """
    Smart auto-resume: If a SPOC previously called 2 students and 75 fresh calls are pending,
    she automatically resumes at Target #3 (the first uncalled fresh student)!
    """
    if not spoc_name or not student_list:
        return 0, 0
    data = load_all_placement_progress()
    saved = data.get(spoc_name.strip().lower(), {})
    saved_active = saved.get("active_call_index", saved.get("queue_index", 0))
    if not isinstance(saved_active, int) or saved_active < 0 or saved_active >= len(student_list):
        saved_active = 0

    highest_verified = get_placement_highest_verified_index(student_list)
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
    # If saved_idx was pointing to an already verified student, automatically advance to next fresh student
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
# 📊 CACHED DATA FETCHING & MODELING
# ==============================================================================
@st.cache_data(ttl=DATA_CACHE_TTL)
def fetch_placement_master_data(_placement_ws):
    """Fetches all rows from Placement_Verification worksheet (15-min cache)"""
    try:
        if _placement_ws:
            return _placement_ws.get_all_values()
        return []
    except Exception:
        return []

def parse_all_placement_students(all_rows):
    """Parses all student rows from the Google Sheet regardless of SPOC"""
    if len(all_rows) <= 1:
        return []
    students = []
    q_idx = 0
    for r_idx, r in enumerate(all_rows[1:], start=2):
        if len(r) > 0 and str(r[0]).strip():
            assigned_spoc = str(r[0]).strip()
            padded = list(r) + [""] * max(0, 34 - len(r))
            students.append({
                "row_num": r_idx,
                "queue_index": q_idx,
                "called_by": assigned_spoc,
                "student_name": padded[1].strip(),
                "cmis_id": padded[2].strip(),
                "donor_name": padded[3].strip(),
                "contact_number": padded[4].strip(),
                "alt_contact_number": padded[5].strip(),
                "gender": padded[6].strip(),
                "centre_code": padded[7].strip(),
                "centre_name": padded[8].strip(),
                "state": padded[9].strip(),
                "course": padded[10].strip(),
                "doj": padded[11].strip(),
                "company_name": padded[12].strip(),
                "designation": padded[13].strip(),
                "salary": padded[14].strip(),
                "job_location": padded[15].strip(),
                # Verified columns (Q to AG)
                "contactable": padded[16].strip(),
                "assessment_given": padded[17].strip(),
                "got_certificate": padded[18].strip(),
                "got_job_from_anudip": padded[19].strip(),
                "retention_status": padded[20].strip(),
                "how_many_months": padded[21].strip(),
                "current_company": padded[22].strip(),
                "current_salary": padded[23].strip(),
                "current_designation": padded[24].strip(),
                "current_doj": padded[25].strip(),
                "need_further_job": padded[26].strip(),
                "nps": padded[27].strip(),
                "verification_date": padded[28].strip(),
                "left_not_working_remarks": padded[29].strip(),
                "not_joined_remarks": padded[30].strip(),
                "satisfied_with_conversation": padded[31].strip(),
                "remarks_2": padded[32].strip() if len(padded) > 32 else ""
            })
            q_idx += 1
    return students

def get_placement_students_for_spoc(all_rows, spoc_name):
    """
    Parses and returns structured student records for the specified SPOC.
    If spoc_name is an admin, returns all records with ability to filter.
    """
    if len(all_rows) <= 1:
        return []

    spoc_clean = (spoc_name or "").strip().lower()
    ADMIN_USERS = {"nibedan", "pritam", "kalpana", "koushik"}
    is_admin = spoc_clean in ADMIN_USERS

    all_students = parse_all_placement_students(all_rows)
    if is_admin:
        return all_students
    
    # Filter to current SPOC
    spoc_students = [s for s in all_students if s["called_by"].strip().lower() == spoc_clean]
    for i, s in enumerate(spoc_students):
        s["queue_index"] = i
    return spoc_students

# ==============================================================================
# 🚀 REAL-TIME STATS & FRESH / NO QUEUES
# ==============================================================================
def compute_placement_stats(students, live_history=None):
    if live_history is None:
        live_history = []
    # Merge live buffer statuses
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
# 🟢 FRESH CALL LIST UI COMPONENT
# ==============================================================================
def render_placement_fresh_call_list(fresh_stats, current_spoc):
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
                <span style="font-weight: 800; color: #166534; font-size: 1.05rem;">🟢 Fresh Calling Queue: {f_spoc}</span>
                <span style="background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; padding: 2px 8px; border-radius: 12px; font-weight: 700; font-size: 0.82rem;">{v_pending} Pending</span>
            </div>
            <div style="margin-top: 6px; font-size: 0.82rem; color: #374151;">
                📊 <b>Formula:</b> Total Assigned ({v_assigned}) − Called ({v_called}) [Yes: {v_yes} + No: {v_no}] = <b style="color: #15803d;">{v_pending} Fresh Pending</b>
            </div>
        </div>
    """, unsafe_allow_html=True)

    if v_pending == 0:
        st.success(f"🎉 Outstanding work! All {v_assigned} assigned placement calls for {f_spoc} have been completed.")
        return

    tab_nums, tab_queue = st.tabs(["📱 Just Numbers (Raw List)", "📞 Interactive Call List"])

    with tab_nums:
        st.caption(f"📋 Pending uncalled phone numbers ({v_pending} remaining). Copy or download below:")
        st.text_area(
            "Just Numbers",
            value=just_nums_text,
            height=160,
            key=f"plc_ta_just_nums_{f_spoc}",
            help="Click inside and press Ctrl+A / Ctrl+C to copy all pending numbers directly into your dialer."
        )

        c_dl1, c_dl2 = st.columns(2)
        with c_dl1:
            st.download_button(
                label=f"📥 Download Just Numbers ({v_pending})",
                data=just_nums_text,
                file_name=f"Placement_Fresh_Numbers_{f_spoc}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                mime="text/plain",
                use_container_width=True,
                key=f"plc_dl_txt_{f_spoc}"
            )
        with c_dl2:
            csv_lines = ["Target_Num,Phone_Number,Student_Name,Company,Designation,Salary"]
            for item in fresh_items:
                csv_lines.append(f"Target #{item['queue_index']+1},{item['contact_number']},{item['student_name']},{item['company_name']},{item['designation']},{item['salary']}")
            st.download_button(
                label="📊 Download CSV Details",
                data="\n".join(csv_lines),
                file_name=f"Placement_Fresh_List_{f_spoc}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True,
                key=f"plc_dl_csv_{f_spoc}"
            )

    with tab_queue:
        q_search = st.text_input(
            "Search phone or student name",
            placeholder="Type 10-digit number or name...",
            key=f"plc_q_search_{f_spoc}",
            label_visibility="collapsed"
        )
        filtered = fresh_items
        if q_search.strip():
            clean_q = clean_phone(q_search.strip())
            name_q = q_search.strip().lower()
            filtered = [
                x for x in fresh_items
                if (clean_q and clean_q in clean_phone(x["contact_number"])) or (name_q in x["student_name"].lower()) or (f"#{x['queue_index']+1}" == q_search.strip())
            ]

        st.caption(f"Showing **{min(len(filtered), 25)}** of **{len(filtered)}** pending calls:")
        for it in filtered[:25]:
            col_i1, col_i2 = st.columns([3, 1.2])
            with col_i1:
                st.markdown(f"**Target #{it['queue_index']+1}**: `{it['contact_number']}` &nbsp;·&nbsp; *{it['student_name']}* ({it['company_name']})")
            with col_i2:
                if st.button("📞 Load", key=f"plc_btn_ld_{it['row_num']}", use_container_width=True):
                    st.session_state.placement_queue_index = it["queue_index"]
                    if it["queue_index"] > st.session_state.get("placement_active_call_index", 0):
                        st.session_state.placement_active_call_index = it["queue_index"]
                    save_placement_progress(current_spoc, it["queue_index"], it["contact_number"], active_call_index=st.session_state.placement_active_call_index)
                    st.toast(f"Loaded Target #{it['queue_index']+1} ({it['student_name']})!", icon="🎯")
                    st.rerun()

# ==============================================================================
# 📞 NOT CONTACTABLE POPUP COMPONENT
# ==============================================================================
def render_placement_not_contactable_list(fresh_stats, current_spoc):
    f_spoc = current_spoc.title()
    no_items = fresh_stats["no_list"]
    st.markdown(f"""
        <div style="background: linear-gradient(135deg, #fff7ed 0%, #ffffff 100%); border: 1.5px solid #fed7aa; border-left: 5px solid #ea580c; border-radius: 8px; padding: 10px 14px; margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 800; color: #9a3412; font-size: 1.05rem;">📞 Not Contactable ("No" Calls): {f_spoc}</span>
                <span style="background: #ffedd5; color: #c2410c; border: 1px solid #fed7aa; padding: 2px 8px; border-radius: 12px; font-weight: 700; font-size: 0.82rem;">{len(no_items)} Calls</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

    if not no_items:
        st.info("👍 No 'Not Contactable' calls recorded yet.")
        return

    for it in no_items[:30]:
        c1, c2 = st.columns([3, 1.2])
        with c1:
            st.markdown(f"**Target #{it['queue_index']+1}**: `{it['contact_number']}` &nbsp;·&nbsp; *{it['student_name']}*<br><small style='color: #c2410c;'>Reason: {it['left_not_working_remarks'] or 'Not Contactable'}</small>", unsafe_allow_html=True)
        with c2:
            if st.button("🔁 Re-Call", key=f"plc_recall_{it['row_num']}", use_container_width=True):
                st.session_state.placement_queue_index = it["queue_index"]
                save_placement_progress(current_spoc, it["queue_index"], it["contact_number"], active_call_index=st.session_state.get("placement_active_call_index", 0))
                st.toast(f"Re-calling Target #{it['queue_index']+1} ({it['student_name']})!", icon="🔁")
                st.rerun()

# ==============================================================================
# 🤖 ZERO-API LOCAL AI PARSING & COPILOT SUITE (100% OFFLINE, FREE, NO API KEY)
# ==============================================================================
def ai_parse_call_notes(raw_notes: str, student_info: dict) -> dict:
    """
    Intelligent Local NLP extractor (0ms latency, zero external API key needed).
    Parses unstructured caller notes/transcripts and maps them to structured verification fields.
    """
    if not raw_notes or not raw_notes.strip():
        return {}

    text = raw_notes.lower()
    extracted = {}

    # 1. Contactable check
    if any(k in text for k in ["not contactable", "didn't answer", "did not answer", "no response", "ringing", "switched off", "wrong number", "network issue", "busy"]):
        extracted["contactable"] = "No"
        extracted["retention_status"] = "Unable_to_track"
        if "switched off" in text:
            extracted["nocont_reason"] = "Switched off"
        elif "wrong number" in text:
            extracted["nocont_reason"] = "Wrong Number"
        elif "network" in text:
            extracted["nocont_reason"] = "Network issue"
        elif "not a student" in text or "not anudip" in text:
            extracted["nocont_reason"] = "Not a student of Anudip"
        elif "language" in text:
            extracted["nocont_reason"] = "Language issue"
        else:
            extracted["nocont_reason"] = "Did not respond to our call"
        return extracted

    # If reached here, student was contactable
    extracted["contactable"] = "Yes"

    # 2. Assessment
    if "assessment no" in text or "not given assessment" in text or "assessment fail" in text:
        extracted["assessment_given"] = "NO"
    else:
        extracted["assessment_given"] = "YES"

    # 3. Certificate
    if "no certificate" in text or "didn't get certificate" in text or "certificate not received" in text:
        extracted["got_certificate"] = "NO"
    else:
        extracted["got_certificate"] = "YES"

    # 4. Got Job from Anudip
    if "self placed" in text or "got job outside" in text or "job not from anudip" in text:
        extracted["got_job_from_anudip"] = "NO"
    else:
        extracted["got_job_from_anudip"] = "YES"

    # 5. Retention Status
    if any(k in text for k in ["left job", "left the job", "resigned", "quit", "discontinued", "left"]):
        extracted["retention_status"] = "Left_The_Job"
        if "higher studies" in text or "study" in text or "college" in text or "mca" in text or "btech" in text:
            extracted["left_remarks"] = "Pursuing Higher Studies."
        elif "distance" in text or "far" in text or "travel" in text:
            extracted["left_remarks"] = "Distance Issue"
        elif "salary" in text or "low pay" in text:
            extracted["left_remarks"] = "Salary Issue"
        elif "medical" in text or "health" in text or "sick" in text:
            extracted["left_remarks"] = "Medical & Health Issue"
        elif "family" in text or "marriage" in text or "parent" in text:
            extracted["left_remarks"] = "Family Issue"
        elif "night shift" in text:
            extracted["left_remarks"] = "Night Shift"
        elif "internship completed" in text or "project completed" in text:
            extracted["left_remarks"] = "Internship/Project Completed"
        else:
            extracted["left_remarks"] = "Casually Left The Job."

    elif any(k in text for k in ["not working", "unemployed", "jobless", "didn't join", "not joined"]):
        extracted["retention_status"] = "Not_working_at_all"
        if "personal" in text or "family" in text or "distance" in text:
            extracted["left_remarks"] = "Did_not_joined_job_due_to_personal_issue"
            extracted["not_joined_remarks"] = "Distance Issue" if "distance" in text else "Medical Issue"
        elif "profile" in text or "role" in text:
            extracted["left_remarks"] = "Did_not_joined_job_due_to_profile_issue"
            extracted["not_joined_remarks"] = "Issue Regarding Job Role"
        elif "interview" in text:
            extracted["left_remarks"] = "Did Not Attend Any Interview"
        elif "selected" in text:
            extracted["left_remarks"] = "Did not get selected"
        else:
            extracted["left_remarks"] = "Did not get any information from the employer"

    elif any(k in text for k in ["different job", "new company", "switched company", "changed job", "another company"]):
        extracted["retention_status"] = "Working in different job"
    elif any(k in text for k in ["will join", "joining next", "offer letter received", "joining after"]):
        extracted["retention_status"] = "Will joined after some days"
    elif any(k in text for k in ["didn't share", "refused", "busy call later", "withheld"]):
        extracted["retention_status"] = "Confirmed Name But Didn't Share Any Information."
    else:
        extracted["retention_status"] = "Working in same job"

    # Extract Salary if numeric digits found
    sal_match = re.search(r"(?:salary|sal|earning|stipend)?\s*(?:inr|rs\.?|₹)?\s*(\d{4,6}|\d{1,2}k)\b", text)
    if sal_match:
        val = sal_match.group(1).replace(",", "")
        if "k" in val:
            val = str(int(float(val.replace("k", "")) * 1000))
        extracted["salary"] = val
    else:
        if extracted.get("retention_status") in ["Working in same job", "Left_The_Job"]:
            extracted["salary"] = str(student_info.get("salary", ""))

    # Extract NPS rating
    nps_match = re.search(r"\b(?:nps|rating|rate|score)?\s*([0-9]|10)(?:\s*/\s*10)?\b", text)
    if nps_match:
        extracted["nps"] = nps_match.group(1)
    else:
        extracted["nps"] = "10"

    # Satisfaction
    if "not satisfied" in text or "unhappy" in text:
        extracted["satisfied"] = "No"
    else:
        extracted["satisfied"] = "Yes"

    # Need further job
    if any(k in text for k in ["need job", "looking for job", "needs another job", "better opportunity"]):
        extracted["need_further_job"] = "YES"
    else:
        extracted["need_further_job"] = "NO"

    return extracted

def generate_ai_calling_script(student: dict, lang: str = "English") -> dict:
    """Generates a dynamic multi-lingual calling script personalized for the student (No API key needed)"""
    s_name = student.get("student_name", "Student")
    company = student.get("company_name", "your placed company")
    desig = student.get("designation", "Intern")
    salary = student.get("salary", "10000")
    donor = student.get("donor_name", "Anudip")
    centre = student.get("centre_name", "Anudip Centre")

    if lang == "Telugu":
        greeting = f"నమస్కారం {s_name} గారూ! నేను అనుదీప్ ఫౌండేషన్ ({donor} ప్రోగ్రామ్, {centre}) నుండి మాట్లాడుతున్నాను. మీతో 1 నిమిషం మాట్లాడవచ్చా?"
        verification = f"మా రికార్డు ప్రకారం మీరు {company} లో {desig} గా (నెలకు ₹{salary}) చేరారు. మీరు ప్రస్తుతం ఇదే ఉద్యోగంలో కొనసాగుతున్నారా?"
        training_check = "అలాగే అనుదీప్ ట్రైనింగ్ అసెస్‌మెంట్ ఇచ్చారా మరియు మీకు అనుదీప్ నుండి సర్టిఫికేట్ అందిందా?"
        feedback = "మీ ప్రస్తుత ఉద్యోగ అనుభవం ఎలా ఉంది? అనుదీప్ శిక్షణపై 1 నుండి 10 వరకు ఎంత రేటింగ్ ఇస్తారు?"
        closing = f"ధన్యవాదాలు {s_name} గారూ! మీ కెరీర్‌లో మరింత ఉన్నత శిఖరాలకు చేరుకోవాలని అనుదీప్ ఫౌండేషన్ మరియు {donor} ఆశిస్తోంది. శుభదినం!"
    elif lang == "Hindi":
        greeting = f"नमस्ते {s_name} जी! मैं अनुदीप फाउंडेशन ({donor} प्रोजेक्ट, {centre}) से कॉल कर रहा/रही हूँ। क्या मेरी बात {s_name} से हो रही है?"
        verification = f"हमारे रिकॉर्ड के अनुसार आपका प्लेसमेंट {company} में {desig} के पद पर (वेतन ₹{salary}) हुआ था। क्या आप अभी भी इसी कंपनी में कार्यरत हैं?"
        training_check = "क्या आपने अनुदीप का असेसमेंट पूरा किया था और क्या आपको सर्टिफिकेट मिल गया है?"
        feedback = "कंपनी में आपका कार्य कैसा चल रहा है? अनुदीप ट्रेनिंग को आप 1 से 10 के पैमाने पर कितना स्कोर देंगे?"
        closing = f"धन्यवाद {s_name} जी! आपके उज्ज्वल भविष्य के लिए अनुदीप और {donor} की ओर से हार्दिक शुभकामनाएँ।"
    elif lang == "Bengali":
        greeting = f"নমস্কার {s_name}! আমি অনুদীপ ফাউন্ডেশন ({donor} প্রজেক্ট, {centre}) থেকে ফোন করছি। আপনার সাথে কি ১ মিনিট কথা বলা যাবে?"
        verification = f"আমাদের কাছে রেকর্ড রয়েছে যে আপনি {company}-তে {desig} পদে (মাসিক বেতন ₹{salary}) যোগ দিয়েছিলেন। আপনি কি এখনও সেখানেই কাজ করছেন?"
        training_check = "আপনি কি অনুদীপের কোর্স অ্যাসেসমেন্ট দিয়েছিলেন এবং সার্টিফিকেট পেয়েছেন?"
        feedback = "আপনার বর্তমান কাজের অভিজ্ঞতা কেমন? অনুদীপ ট্রেনিং ও সার্ভিসের জন্য ১ থেকে ১০-এর মধ্যে কত রেটিং দেবেন?"
        closing = f"অসংখ্য ধন্যবাদ {s_name}! আপনার উজ্জ্বল ভবিষ্যতের জন্য অনুদীপ ফাউন্ডেশনের পক্ষ থেকে আন্তরিক শুভেচ্ছা।"
    elif lang == "Tamil":
        greeting = f"வணக்கம் {s_name}! நான் அனுதீப் அறக்கட்டளையிலிருந்து ({donor} திட்டம்) அழைக்கிறேன். உங்களிடம் 1 நிமிடம் பேசலாமா?"
        verification = f"நீங்கள் {company} நிறுவனத்தில் {desig} ஆக (ரூ. {salary}) பணியில் இணைந்ததாக எங்கள் பதிவேட்டில் உள்ளது. நீங்கள் தற்போது அதே வேலையில் தொடர்கிறீர்களா?"
        training_check = "அனுதீப் பயிற்சி சான்றிதழ் உங்களுக்கு கிடைத்ததா?"
        feedback = "உங்கள் தற்போதைய வேலை அனுபவம் திருப்திகரமாக உள்ளதா? 1 முதல் 10 வரை எவ்வளவு மதிப்பீடு வழங்குவீர்கள்?"
        closing = f"நன்றி {s_name}! உங்கள் எதிர்கால வளர்ச்சிக்கு அனுதீப் அறக்கட்டளையின் வாழ்த்துக்கள்."
    else: # English
        greeting = f"Hello {s_name}! I am calling from Anudip Foundation ({donor} Program, {centre}). Am I speaking with {s_name}?"
        verification = f"As per our official records, you joined {company} as an {desig} (Monthly ₹{salary}). Are you currently continuing in this same position?"
        training_check = "Did you complete your final course assessment and have you received your Anudip completion certificate?"
        feedback = "How is your work experience at the company so far? On a scale of 0 to 10, how likely are you to recommend Anudip to friends and family?"
        closing = f"Thank you so much {s_name} for your valuable time. Anudip Foundation and {donor} wish you continued success in your career!"

    return {
        "greeting": greeting,
        "verification": verification,
        "training_check": training_check,
        "feedback": feedback,
        "closing": closing
    }

def compute_retention_risk_score(student: dict) -> dict:
    """Computes an AI Career & Retention Stability Score based on profile factors (Local Rule-based)"""
    salary_str = re.sub(r"\D", "", str(student.get("salary", "0")))
    salary = int(salary_str) if salary_str else 10000

    score = 85
    reasons = []

    if salary >= 15000:
        score += 10
        reasons.append("Competitive compensation (₹15,000+)")
    elif salary < 9000:
        score -= 15
        reasons.append("Entry-level stipend below ₹9,000")

    desig = str(student.get("designation", "")).lower()
    if "intern" in desig or "trainee" in desig:
        score -= 5
        reasons.append("Intern/Trainee role (tenure check recommended)")

    score = max(35, min(98, score))

    if score >= 80:
        badge_color = "#16a34a"
        bg_color = "#dcfce7"
        level = "High Stability (Low Risk)"
    elif score >= 60:
        badge_color = "#d97706"
        bg_color = "#fef3c7"
        level = "Moderate Retention Risk"
    else:
        badge_color = "#dc2626"
        bg_color = "#fee2e2"
        level = "High Retention Risk"

    return {
        "score": score,
        "level": level,
        "badge_color": badge_color,
        "bg_color": bg_color,
        "reasons": reasons
    }

# ==============================================================================
# 🖥️ MAIN PLACEMENT DASHBOARD RENDERER
# ==============================================================================
def render_placement_dashboard(placement_ws, current_spoc, is_admin=False):
    # Custom CSS for high-speed layout & modern card UI matching Images 1, 2, 3
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
                font-weight: 800;
                color: #0f172a;
            }
            .question-pill-header {
                background: #f8fafc;
                border: 1.5px solid #e2e8f0;
                border-radius: 8px 8px 0 0;
                padding: 7px 12px;
                font-size: 0.88rem;
                font-weight: 800;
                color: #1e293b;
                text-align: center;
            }
            .ai-copilot-box {
                background: linear-gradient(135deg, #f8fafc 0%, #eff6ff 100%);
                border: 1.5px solid #bfdbfe;
                border-radius: 10px;
                padding: 12px 16px;
                margin-top: 10px;
                margin-bottom: 14px;
            }
        </style>
    """, unsafe_allow_html=True)

    # 1. Fetch all placement rows (cached)
    all_rows = fetch_placement_master_data(placement_ws)
    if not all_rows:
        st.error("⚠️ Could not load data from Google Sheet 'Placement_Verification'. Please check permissions or connection.")
        return

    # Parse all records
    all_placement_students = parse_all_placement_students(all_rows)
    if not all_placement_students:
        st.warning("No placement records found in the Google Sheet.")
        return

    # Live session buffer initialization
    if "placement_live_history" not in st.session_state:
        st.session_state.placement_live_history = []

    # All distinct SPOCs from sheet
    all_spocs = sorted(list({s["called_by"].strip().title() for s in all_placement_students if s["called_by"]}))

    # Top Brand Header Banner
    st.markdown("""
        <div style="background: linear-gradient(135deg, #1e3a8a 0%, #0f4c81 100%); padding: 1.2rem 1.6rem; border-radius: 12px; color: white; margin-bottom: 1.2rem; box-shadow: 0 4px 14px rgba(15, 76, 129, 0.2);">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
                <div>
                    <h2 style="color: #ffffff; margin: 0; font-size: 1.5rem; font-weight: 800; letter-spacing: -0.5px;">⚡ High Speed Placement Verification System</h2>
                    <p style="color: #93c5fd; margin: 3px 0 0 0; font-size: 0.92rem;">Placement & Retention Calling Portal | Respective SPOC Verification Sheet</p>
                </div>
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="background: rgba(255,255,255,0.15); padding: 6px 14px; border-radius: 20px; font-weight: 700; font-size: 0.88rem; border: 1px solid rgba(255,255,255,0.3);">
                        💼 Placement Module
                    </span>
                    <span style="background: #22c55e; color: #ffffff; padding: 6px 14px; border-radius: 20px; font-weight: 800; font-size: 0.88rem;">
                        👤 {current_spoc}
                    </span>
                </div>
            </div>
        </div>
    """.replace("{current_spoc}", current_spoc.title()), unsafe_allow_html=True)

    # ==========================================================================
    # 🌟 IMAGE 1: PERFORMANCE VIEW SELECTOR (Board 1 & Board 2)
    # ==========================================================================
    view_options = ["🌟 All Team Combined (Portal Total)"] + all_spocs

    col_view_lbl, col_view_sel = st.columns([1.5, 2.5])
    with col_view_lbl:
        st.markdown("<div style='padding-top: 6px; font-weight: 800; color: #0f4c81; font-size: 1.05rem;'>📊 Select Performance View:</div>", unsafe_allow_html=True)
    with col_view_sel:
        # Check if view was overridden
        forced_view = st.session_state.get("plc_perf_view")
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
            key="plc_perf_view_selector_box"
        )
        st.session_state.plc_perf_view = selected_perf_view

    # Compute stats based on selected view
    if selected_perf_view == "🌟 All Team Combined (Portal Total)":
        display_scope_name = "All Team Combined"
        scoped_students = all_placement_students
    else:
        display_scope_name = selected_perf_view
        scoped_students = [s for s in all_placement_students if s["called_by"].strip().lower() == selected_perf_view.strip().lower()]

    scope_stats = compute_placement_stats(scoped_students, st.session_state.placement_live_history)
    v_assigned = scope_stats["total_assigned"]
    v_called = scope_stats["total_called"]
    v_yes = scope_stats["yes_count"]
    v_no = scope_stats["no_count"]
    v_pending = scope_stats["fresh_pending"]
    v_rate = scope_stats["contactable_pct"]

    # Render Dual Operational Boards
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        b1_card = f"""<div style="background: linear-gradient(135deg, #f0fdf4 0%, #ffffff 100%); border: 1.5px solid #86efac; border-left: 6px solid #16a34a; border-radius: 12px; padding: 14px 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); min-height: 165px;">
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
💡 <b>Calculation:</b> Total Calls ({v_assigned}) − Called ({v_called}) [Yes: {v_yes} + No: {v_no}] = <b>{v_pending} Fresh Pending</b>
</div>
</div>"""
        st.markdown(b1_card, unsafe_allow_html=True)

    with col_b2:
        b2_card = f"""<div style="background: linear-gradient(135deg, #eff6ff 0%, #ffffff 100%); border: 1.5px solid #93c5fd; border-left: 6px solid #2563eb; border-radius: 12px; padding: 14px 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); min-height: 165px;">
<div style="display: flex; justify-content: space-between; align-items: flex-start;">
<div>
<span style="font-size: 0.8rem; font-weight: 700; color: #1e40af; text-transform: uppercase; letter-spacing: 0.5px;">🎯 Board 2: Contactability Rate ({display_scope_name})</span>
<div style="display: flex; align-items: baseline; gap: 10px; margin-top: 4px;">
<span style="font-size: 2.3rem; font-weight: 900; color: #1d4ed8; line-height: 1;">{v_rate:.1f}%</span>
<span style="font-size: 1.05rem; font-weight: 800; color: #1e40af;">Contactable (% of Yes)</span>
</div>
</div>
<span style="background: #dbeafe; color: #1d4ed8; border: 1px solid #bfdbfe; padding: 4px 10px; border-radius: 20px; font-size: 0.82rem; font-weight: 700;">{v_yes}/{v_called} Contacted</span>
</div>
<div style="margin-top: 12px; padding-top: 10px; border-top: 1px dashed #bfdbfe; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; font-size: 0.88rem;">
<span style="color: #16a34a;">Contacted (Yes): <b>{v_yes}</b></span>
<span style="color: #2563eb;">Total Attempted: <b>{v_called}</b></span>
<span style="color: #dc2626;">Unreached (No): <b>{v_no}</b></span>
</div>
<div style="margin-top: 8px; font-size: 0.78rem; color: #6b7280;">
💡 <b>Calculation:</b> (Contacted Yes [{v_yes}] ÷ Total Called [{v_called}]) × 100 = <b>{v_rate:.1f}% Contactable</b>
</div>
</div>"""
        st.markdown(b2_card, unsafe_allow_html=True)

    # Popover buttons for Fresh Calls and Not Contactable
    col_pop1, col_pop2 = st.columns(2)
    with col_pop1:
        st.markdown('<div class="fresh-call-header-btn">', unsafe_allow_html=True)
        with st.popover(f"🟢 Fresh Calls ({v_pending} Pending) ⌄", use_container_width=True):
            render_placement_fresh_call_list(scope_stats, display_scope_name)
        st.markdown('</div>', unsafe_allow_html=True)

    with col_pop2:
        st.markdown('<div class="nocontact-header-btn">', unsafe_allow_html=True)
        with st.popover(f"📞 Not Contactable ({v_no}) ⌄", use_container_width=True):
            render_placement_not_contactable_list(scope_stats, display_scope_name)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 14px;'></div>", unsafe_allow_html=True)

    # Active Queue determination
    if is_admin and selected_perf_view != "🌟 All Team Combined (Portal Total)":
        active_queue_students = scoped_students
    else:
        active_queue_students = get_placement_students_for_spoc(all_rows, current_spoc)

    if not active_queue_students:
        st.warning(f"No students allocated for '{display_scope_name}'. Please choose another view.")
        return

    # Queue index management
    if "placement_queue_index" not in st.session_state:
        saved_q, saved_act = get_saved_placement_index(current_spoc, active_queue_students)
        st.session_state.placement_queue_index = saved_q
        st.session_state.placement_active_call_index = saved_act

    current_q_idx = st.session_state.placement_queue_index
    if current_q_idx >= len(active_queue_students):
        current_q_idx = max(0, len(active_queue_students) - 1)
        st.session_state.placement_queue_index = current_q_idx

    current_student = active_queue_students[current_q_idx]
    total_assigned_queue = len(active_queue_students)

    # ==========================================================================
    # 📍 RESUME BANNER (WELCOME BACK / RESUME PROGRESS LIKE IMPACT ASSESSMENT)
    # ==========================================================================
    if st.session_state.get("show_placement_resume_banner") and total_assigned_queue > 0 and current_q_idx > 0:
        res_c1, res_c2, res_c3 = st.columns([3.2, 1.2, 1.2])
        with res_c1:
            st.info(f"📍 **Welcome back, {current_spoc.title()}!** Resumed at Target **#{current_q_idx + 1}** of {total_assigned_queue} ({v_pending} fresh calls pending).")
        with res_c2:
            if st.button("▶️ Continue Here", type="primary", use_container_width=True, key="plc_resume_continue"):
                st.session_state.show_placement_resume_banner = False
                st.rerun()
        with res_c3:
            if st.button("⏮️ Start from #1", use_container_width=True, key="plc_resume_start1"):
                st.session_state.placement_queue_index = 0
                st.session_state.show_placement_resume_banner = False
                save_placement_progress(current_spoc, 0, active_queue_students[0]["contact_number"], active_call_index=st.session_state.get("placement_active_call_index", 0))
                st.rerun()

    if v_pending == 0:
        st.success(f"🎉 **Outstanding work, {current_spoc.title()}!** All {v_assigned} assigned placement calls have been completed.")

    # ==========================================================================
    # 🎛️ IMAGE 2 & USER PIC: SEARCH & FETCH BAR + 5 NAVIGATION BUTTONS
    # ==========================================================================
    c_search, c_fetch, c_start, c_prev, c_next, c_clear, c_refresh = st.columns([2.6, 1.3, 0.85, 0.85, 0.85, 1.05, 1.05])

    search_inp = c_search.text_input(
        "Search or Target",
        placeholder="Search phone or enter Target # (e.g. 71, 302)...",
        label_visibility="collapsed",
        key="plc_quick_search_input"
    )

    # ⚡ Fetch Details Button (Coral/Red primary button as in User Picture 2)
    if c_fetch.button("⚡ Fetch Details", use_container_width=True, type="primary", key="plc_btn_fetch_details"):
        target = search_inp.strip()
        if target:
            clean_num = target.lstrip("#").strip()
            found_target = None
            target_idx = None

            # 1. Check if numeric target number (e.g. 71, 302, 1, 1153)
            if clean_num.isdigit():
                t_num = int(clean_num)
                # Check within active queue first
                if 1 <= t_num <= len(active_queue_students):
                    target_idx = t_num - 1
                    found_target = active_queue_students[target_idx]
                else:
                    # Search across all students
                    for s in all_placement_students:
                        if s["queue_index"] + 1 == t_num or s["row_num"] == t_num:
                            found_target = s
                            for a_idx, a_s in enumerate(active_queue_students):
                                if a_s["row_num"] == s["row_num"]:
                                    target_idx = a_idx
                                    break
                            break

            # 2. Check if phone number
            if not found_target:
                c_phone = clean_phone(target)
                if c_phone:
                    for idx, s in enumerate(active_queue_students):
                        if c_phone in clean_phone(s["contact_number"]) or c_phone in clean_phone(s["alt_contact_number"]):
                            target_idx = idx
                            found_target = s
                            break
                    if not found_target:
                        for s in all_placement_students:
                            if c_phone in clean_phone(s["contact_number"]) or c_phone in clean_phone(s["alt_contact_number"]):
                                found_target = s
                                break

            # 3. Check if student name
            if not found_target:
                t_lower = target.lower()
                for idx, s in enumerate(active_queue_students):
                    if t_lower in s["student_name"].lower():
                        target_idx = idx
                        found_target = s
                        break
                if not found_target:
                    for s in all_placement_students:
                        if t_lower in s["student_name"].lower():
                            found_target = s
                            break

            if found_target:
                if target_idx is not None:
                    st.session_state.placement_queue_index = target_idx
                else:
                    st.session_state.plc_perf_view = "🌟 All Team Combined (Portal Total)"
                    st.session_state.plc_perf_view_selector_box = "🌟 All Team Combined (Portal Total)"
                    st.session_state.placement_queue_index = found_target["queue_index"]

                # If previously verified, load previous verification data for editing/updating!
                r_num = found_target["row_num"]
                if found_target.get("contactable"):
                    st.session_state[f"plc_preset_{r_num}"] = {
                        "contactable": "Yes" if found_target["contactable"].strip().lower() == "yes" else "No",
                        "assessment_given": found_target["assessment_given"] or "YES",
                        "got_certificate": found_target["got_certificate"] or "YES",
                        "got_job_from_anudip": found_target["got_job_from_anudip"] or "YES",
                        "retention_status": found_target["retention_status"] or "Working in same job",
                        "months": found_target["how_many_months"] or "3 Months",
                        "company": found_target["current_company"] or found_target["company_name"],
                        "salary": found_target["current_salary"] or found_target["salary"],
                        "designation": found_target["current_designation"] or found_target["designation"],
                        "doj": parse_date_safe(found_target["current_doj"]) or parse_date_safe(found_target["doj"]) or date.today(),
                        "need_further_job": found_target["need_further_job"] or "NO",
                        "nps": found_target["nps"] or "10",
                        "satisfied": found_target["satisfied_with_conversation"] or "Yes",
                        "verification_date": parse_date_safe(found_target["verification_date"]) or date.today(),
                        "left_remarks": found_target["left_not_working_remarks"],
                        "not_joined_remarks": found_target["not_joined_remarks"],
                        "nocont_reason": found_target["left_not_working_remarks"],
                        "remarks_2": found_target["remarks_2"]
                    }
                    keys_to_clear = [k for k in st.session_state.keys() if f"_{r_num}" in k and k.startswith("plc_")]
                    for k in keys_to_clear:
                        st.session_state.pop(k, None)
                    st.session_state.placement_editing_row = r_num

                st.toast(f"Loaded Target #{found_target['queue_index']+1} ({found_target['student_name']})!", icon="⚡")
                st.rerun()
            else:
                st.warning(f"No student record found matching '{target}'.")

    # 1. ⏮ #1 Button
    if c_start.button("⏮ #1", use_container_width=True, help="Jump to Target #1 (Queue beginning)", disabled=(current_q_idx == 0 or total_assigned_queue == 0)):
        st.session_state.placement_queue_index = 0
        save_placement_progress(current_spoc, 0, active_queue_students[0]["contact_number"], active_call_index=st.session_state.get("placement_active_call_index", 0))
        st.toast("Jumped to Target #1!", icon="⏮️")
        st.rerun()

    # 2. ⬅ Prev Button
    if c_prev.button("⬅ Prev", use_container_width=True, disabled=(current_q_idx <= 0 or total_assigned_queue == 0)):
        st.session_state.placement_queue_index = max(0, current_q_idx - 1)
        prev_s = active_queue_students[st.session_state.placement_queue_index]
        save_placement_progress(current_spoc, st.session_state.placement_queue_index, prev_s["contact_number"], active_call_index=st.session_state.get("placement_active_call_index", 0))
        st.rerun()

    # 3. Next ➡ Button
    if c_next.button("Next ➡", use_container_width=True, disabled=(current_q_idx >= total_assigned_queue - 1 or total_assigned_queue == 0)):
        st.session_state.placement_queue_index = min(total_assigned_queue - 1, current_q_idx + 1)
        if st.session_state.placement_queue_index > st.session_state.get("placement_active_call_index", 0):
            st.session_state.placement_active_call_index = st.session_state.placement_queue_index
        next_s = active_queue_students[st.session_state.placement_queue_index]
        save_placement_progress(current_spoc, st.session_state.placement_queue_index, next_s["contact_number"], active_call_index=st.session_state.get("placement_active_call_index", 0))
        st.rerun()

    # 4. 🧹 Clear Form Button
    if c_clear.button("🧹 Clear Form", use_container_width=True):
        row_k = current_student["row_num"]
        st.session_state.pop(f"plc_preset_{row_k}", None)
        st.session_state.pop("placement_editing_row", None)
        keys_to_remove = [k for k in st.session_state.keys() if f"_{row_k}" in k and k.startswith("plc_")]
        for k in keys_to_remove:
            st.session_state.pop(k, None)
        st.toast("Form cleared for current student!", icon="🧹")
        st.rerun()

    # 5. 🔄 Refresh DB Button
    if c_refresh.button("🔄 Refresh DB", use_container_width=True):
        fetch_placement_master_data.clear()
        st.cache_data.clear()
        st.toast("Database cache refreshed from Google Sheets!", icon="🔄")
        st.rerun()

    # ==========================================================================
    # 🎯 CALLING TARGET BANNER WITH 1-CLICK COPY PHONE NUMBER (EXACT PICTURE MATCH)
    # ==========================================================================
    prog_pct = min((current_q_idx + 1) / total_assigned_queue, 1.0) if total_assigned_queue > 0 else 0
    st.progress(prog_pct)

    col_t1, col_t2 = st.columns([5, 1.1])
    phone_clean = clean_phone(current_student['contact_number'])

    with col_t1:
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
                padding: 8px 16px;
                border-radius: 8px;
                border-left: 5px solid #1a73e8;
                display: flex;
                justify-content: space-between;
                align-items: center;
                height: 48px;
            }}
            .banner-left {{
                font-size: 1.0rem;
                color: #1e3a8a;
                font-weight: 700;
                display: flex;
                align-items: center;
                gap: 8px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }}
            .phone-link {{
                color: #1a73e8;
                font-weight: 800;
                font-size: 1.08rem;
                text-decoration: underline;
            }}
            .copy-banner-btn {{
                border: 1.5px solid #2e7d32;
                background-color: #ffffff;
                color: #1b5e20;
                font-weight: 700;
                font-size: 0.90rem;
                border-radius: 6px;
                padding: 5px 14px;
                cursor: pointer;
                transition: all 0.2s ease-in-out;
                display: inline-flex;
                align-items: center;
                gap: 5px;
                white-space: nowrap;
            }}
            .copy-banner-btn:hover {{
                background-color: #f0fdf4;
                border-color: #15803d;
                color: #14532d;
                transform: translateY(-1px);
            }}
            .copy-banner-btn.copied {{
                background-color: #16a34a !important;
                color: #ffffff !important;
                border-color: #15803d !important;
            }}
        </style>
        </head>
        <body>
        <div class="queue-banner">
            <div class="banner-left">
                <span>🎯 Calling Target <b>#{current_q_idx + 1} of {total_assigned_queue}</b></span>
                <span>·</span>
                <span style="color: #0f172a;">{current_student['student_name']}</span>
                <span>·</span>
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
        if st.button("⏭️ Skip", use_container_width=True, key=f"plc_skip_btn_{current_student['row_num']}"):
            st.session_state.placement_queue_index = min(total_assigned_queue - 1, current_q_idx + 1)
            next_s = active_queue_students[st.session_state.placement_queue_index]
            save_placement_progress(current_spoc, st.session_state.placement_queue_index, next_s["contact_number"], active_call_index=st.session_state.get("placement_active_call_index", 0))
            st.toast("Skipped to next target", icon="⏭️")
            st.rerun()

    # ==========================================================================
    # 🪪 IMAGE 3: STUDENT PLACEMENT PROFILE DETAILS (ENHANCED UI)
    # ==========================================================================
    st.markdown('<div class="profile-card-enhanced">', unsafe_allow_html=True)
    st.markdown("""
        <div class="profile-title-bar">
            <span>👤 Student Placement Profile Details</span>
        </div>
    """, unsafe_allow_html=True)

    # Clean 4-Column Grid matching Picture 3
    p_col1, p_col2, p_col3, p_col4 = st.columns(4)
    with p_col1:
        st.markdown(f"<div class='profile-label-styled'>Student Name</div><div class='profile-val-styled' style='font-size: 1.15rem; color: #0f172a;'>{current_student['student_name']}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label-styled' style='margin-top:10px;'>CMIS ID</div><div class='profile-val-styled' style='font-family: monospace; font-size: 0.95rem; background: #f1f5f9; padding: 2px 6px; border-radius: 4px; display: inline-block;'>{current_student['cmis_id'] or 'N/A'}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label-styled' style='margin-top:10px;'>Gender</div><div class='profile-val-styled' style='text-transform: capitalize;'>{current_student['gender'] or 'N/A'}</div>", unsafe_allow_html=True)

    with p_col2:
        phone_raw = current_student['contact_number']
        wa_text = urllib.parse.quote(f"Hello {current_student['student_name']}, calling from Anudip Foundation ({current_student['donor_name']}) regarding your placement verification. Could you please take 1 minute to confirm your employment status? Thank you!")
        st.markdown(f"""
            <div class='profile-label-styled'>Contact Number</div>
            <div style='display: flex; align-items: center; gap: 8px; flex-wrap: wrap;'>
                <a href='tel:{phone_raw}' style='color:#1a73e8; font-weight:800; font-size:1.15rem; text-decoration: none;'>📞 {phone_raw}</a>
                <a href='https://wa.me/91{clean_phone(phone_raw)}?text={wa_text}' target='_blank' style='background:#25d366; color:white; padding:2px 8px; border-radius:12px; font-size:0.75rem; text-decoration:none; font-weight:700;'>💬 WhatsApp</a>
            </div>
        """, unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label-styled' style='margin-top:10px;'>Alt. Contact</div><div class='profile-val-styled'>{current_student['alt_contact_number'] if current_student['alt_contact_number'] != '0' else 'None'}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label-styled' style='margin-top:10px;'>Donor Name</div><div class='profile-val-styled'><span style='background: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 12px; font-size: 0.85rem; font-weight: 700;'>{current_student['donor_name'] or 'N/A'}</span></div>", unsafe_allow_html=True)

    with p_col3:
        st.markdown(f"<div class='profile-label-styled'>Centre Name</div><div class='profile-val-styled' style='font-size: 0.92rem; line-height: 1.3;'>{current_student['centre_name']}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label-styled' style='margin-top:10px;'>Course / State</div><div class='profile-val-styled'>{current_student['course']} &nbsp;·&nbsp; <b>{current_student['state']}</b></div>", unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label-styled' style='margin-top:10px;'>Date of Joining (DOJ)</div><div class='profile-val-styled' style='font-family: monospace;'>{current_student['doj'] or 'N/A'}</div>", unsafe_allow_html=True)

    with p_col4:
        st.markdown(f"<div class='profile-label-styled'>Placed Company</div><div class='profile-val-styled' style='color:#0f4c81; font-size: 1.05rem;'>🏢 {current_student['company_name']}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label-styled' style='margin-top:10px;'>Designation</div><div class='profile-val-styled'>{current_student['designation']}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label-styled' style='margin-top:10px;'>Salary / Location</div><div class='profile-val-styled'>💰 ₹{current_student['salary']} &nbsp;·&nbsp; {current_student['job_location']}</div>", unsafe_allow_html=True)

    st.markdown('<div style="height: 4px; background: linear-gradient(90deg, #f59e0b 0%, #fbbf24 100%); border-radius: 2px; margin: 16px 0 16px 0;"></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ==========================================================================
    # ⚡ HIGH SPEED VERIFICATION & AI COPILOT SUITE (100% LOCAL, NO API KEY REQUIRED)
    # ==========================================================================
    ai_risk = compute_retention_risk_score(current_student)

    with st.expander("🤖 Local AI Calling Copilot & 1-Click Fast Presets (Click to Expand)", expanded=False):
        st.markdown("""
            <div style="background: #f0fdf4; border: 1.5px solid #86efac; border-left: 5px solid #16a34a; padding: 7px 12px; border-radius: 6px; margin-bottom: 10px; font-size: 0.85rem; color: #166534; font-weight: 700;">
                ⚡ 100% Free Built-in Local AI: No API Key or Internet Needed. Runs locally on your machine with ZERO latency and zero cost.
            </div>
        """, unsafe_allow_html=True)

        c_ai1, c_ai2 = st.columns([1.8, 1.2])
        with c_ai1:
            st.markdown(f"""
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <b style="color: #0f4c81; font-size: 0.95rem;">🗣️ Dynamic AI Calling Script</b>
                    <span style="background: {ai_risk['bg_color']}; color: {ai_risk['badge_color']}; padding: 2px 8px; border-radius: 12px; font-weight: 700; font-size: 0.78rem;">
                        Retention Health: {ai_risk['score']}% ({ai_risk['level']})
                    </span>
                </div>
            """, unsafe_allow_html=True)

            script_lang = st.radio("Choose Language", ["English", "Telugu", "Hindi", "Bengali", "Tamil"], horizontal=True, key=f"plc_lang_{current_student['row_num']}")
            script_data = generate_ai_calling_script(current_student, script_lang)

            st.markdown(f"""
                <div class="ai-copilot-box">
                    <p style="margin: 0 0 6px 0; color: #1e3a8a; font-weight: 700;">1. Greeting & Identity:</p>
                    <p style="margin: 0 0 8px 0; font-size: 0.92rem; color: #334155;"><i>"{script_data['greeting']}"</i></p>
                    <p style="margin: 0 0 6px 0; color: #1e3a8a; font-weight: 700;">2. Employment Verification:</p>
                    <p style="margin: 0 0 8px 0; font-size: 0.92rem; color: #334155;"><i>"{script_data['verification']}"</i></p>
                    <p style="margin: 0 0 6px 0; color: #1e3a8a; font-weight: 700;">3. Training & Certification:</p>
                    <p style="margin: 0 0 8px 0; font-size: 0.92rem; color: #334155;"><i>"{script_data['training_check']}"</i></p>
                    <p style="margin: 0 0 6px 0; color: #1e3a8a; font-weight: 700;">4. Satisfaction & NPS:</p>
                    <p style="margin: 0 0 8px 0; font-size: 0.92rem; color: #334155;"><i>"{script_data['feedback']}"</i></p>
                    <p style="margin: 0; font-size: 0.92rem; color: #334155;"><i>"{script_data['closing']}"</i></p>
                </div>
            """, unsafe_allow_html=True)

        with c_ai2:
            st.markdown("<b style='color: #0f4c81; font-size: 0.95rem;'>🧠 Local AI Notes Parser</b>", unsafe_allow_html=True)
            st.caption("Paste notes to auto-fill form (No API key needed):")
            ai_notes_inp = st.text_area(
                "Call Notes",
                placeholder="E.g. Spoke with Swetha. Working in same job at Engro as Intern. Salary 10000. Got cert and gave assessment. NPS 10. Satisfied.",
                height=100,
                key=f"plc_ai_note_inp_{current_student['row_num']}"
            )
            if st.button("✨ Auto-Fill Form from Call Notes", use_container_width=True, key=f"plc_ai_extract_btn_{current_student['row_num']}"):
                if ai_notes_inp.strip():
                    parsed_res = ai_parse_call_notes(ai_notes_inp, current_student)
                    st.session_state[f"plc_preset_{current_student['row_num']}"] = parsed_res
                    st.toast(f"Local AI extracted {len(parsed_res)} fields from notes!", icon="✨")
                    st.rerun()
                else:
                    st.warning("Please type or paste call notes first.")

            st.markdown("<hr style='margin: 8px 0;'>", unsafe_allow_html=True)
            st.markdown("<b style='color: #0f4c81; font-size: 0.9rem;'>⚡ 1-Click Speed Presets:</b>", unsafe_allow_html=True)

            c_p1, c_p2 = st.columns(2)
            with c_p1:
                if st.button("⚡ Same Job (Active)", key=f"plc_pre_same_{current_student['row_num']}", use_container_width=True):
                    st.session_state[f"plc_preset_{current_student['row_num']}"] = {
                        "contactable": "Yes",
                        "assessment_given": "YES",
                        "got_certificate": "YES",
                        "got_job_from_anudip": "YES",
                        "retention_status": "Working in same job",
                        "months": "3 Months",
                        "company": current_student["company_name"],
                        "salary": current_student["salary"],
                        "designation": current_student["designation"],
                        "doj": parse_date_safe(current_student["doj"]) or date.today(),
                        "need_further_job": "NO",
                        "nps": "10",
                        "satisfied": "Yes",
                        "left_remarks": "N/A - Currently Working",
                        "remarks_2": "Student verified actively continuing in placed company."
                    }
                    st.toast("Applied: Working in same job", icon="⚡")
                    st.rerun()

                if st.button("⚡ Switched Off", key=f"plc_pre_soff_{current_student['row_num']}", use_container_width=True):
                    st.session_state[f"plc_preset_{current_student['row_num']}"] = {
                        "contactable": "No",
                        "retention_status": "Unable_to_track",
                        "nocont_reason": "Switched off",
                        "remarks_2": "Phone switched off."
                    }
                    st.toast("Applied: Switched off", icon="⚡")
                    st.rerun()

            with c_p2:
                if st.button("⚡ Ringing No Ans", key=f"plc_pre_ring_{current_student['row_num']}", use_container_width=True):
                    st.session_state[f"plc_preset_{current_student['row_num']}"] = {
                        "contactable": "No",
                        "retention_status": "Unable_to_track",
                        "nocont_reason": "Did not respond to our call",
                        "remarks_2": "Ringing, no answer."
                    }
                    st.toast("Applied: Ringing no answer", icon="⚡")
                    st.rerun()

                if st.button("⚡ Wrong Number", key=f"plc_pre_wrong_{current_student['row_num']}", use_container_width=True):
                    st.session_state[f"plc_preset_{current_student['row_num']}"] = {
                        "contactable": "No",
                        "retention_status": "Unable_to_track",
                        "nocont_reason": "Wrong Number",
                        "remarks_2": "Wrong contact number."
                    }
                    st.toast("Applied: Wrong Number", icon="⚡")
                    st.rerun()

    # ==========================================================================
    # 📝 IMAGE 3 & 4: CALL VERIFICATION QUESTIONNAIRE (CONDITIONAL WORKFLOW)
    # ==========================================================================
    is_already_verified = bool(current_student["contactable"])
    is_edit_mode = st.session_state.get("placement_editing_row") == current_student["row_num"]

    status_badge_html = f"""
        <span style="background: #fef3c7; color: #92400e; border: 1.5px solid #fcd34d; padding: 4px 12px; border-radius: 6px; font-weight: 800; font-size: 0.88rem;">
            ✏️ EDIT & UPDATE MODE (Row #{current_student['row_num']})
        </span>
    """ if (is_edit_mode or is_already_verified) else f"""
        <span style="background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.85rem;">
            🆕 FRESH CALL VERIFICATION (Target #{current_q_idx + 1})
        </span>
    """

    st.markdown('<div class="profile-card-enhanced" style="border-top: 4px solid #f59e0b;">', unsafe_allow_html=True)
    st.markdown(f"""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.2rem; flex-wrap: wrap; gap: 8px;">
            <div style="font-size: 1.22rem; font-weight: 800; color: #0f4c81; display: flex; align-items: center; gap: 8px;">
                📋 Call Verification Questionnaire
            </div>
            <div>{status_badge_html}</div>
        </div>
    """, unsafe_allow_html=True)

    # Edit Mode Alert Banner (Loads previous values for update & insert per Item 1)
    if is_edit_mode or is_already_verified:
        st.markdown(f"""
            <div style="background: #fffbeb; border: 1.5px solid #fde68a; border-left: 6px solid #d97706; padding: 10px 14px; border-radius: 8px; margin-bottom: 14px;">
                <b style="color: #92400e; font-size: 0.98rem;">✏️ Reviewing & Updating Target #{current_q_idx + 1} — {current_student['student_name']} (Row #{current_student['row_num']}):</b>
                <div style="color: #b45309; font-size: 0.85rem; margin-top: 2px;">
                    Previously saved details are loaded below. Update any fields and click <b>Update & Insert Placement Verification</b> to save your changes to Google Sheets.
                </div>
            </div>
        """, unsafe_allow_html=True)

    row_preset = st.session_state.get(f"plc_preset_{current_student['row_num']}", {})

    # 1. Question 1: Is the student Contactable? (Call Status)
    if "contactable" in row_preset:
        def_cont_idx = 0 if row_preset["contactable"] == "Yes" else 1
    else:
        def_cont_idx = 0 if current_student["contactable"].strip().lower() != "no" else 1

    st.markdown("""
        <div class="question-pill-header" style="text-align: left; background: #eff6ff; border-color: #bfdbfe; color: #1e40af;">
            1. Is the student Contactable? (Call Status)
        </div>
    """, unsafe_allow_html=True)

    f_contactable = st.radio(
        "Is the student Contactable? (Call Status)",
        ["Yes", "No"],
        index=def_cont_idx,
        horizontal=True,
        label_visibility="collapsed",
        key=f"plc_rad_cont_{current_student['row_num']}"
    )

    # --------------------------------------------------------------------------
    # ❌ CONDITION: IF CONTACTABLE == NO -> Retention Status = Unable_to_track
    # --------------------------------------------------------------------------
    if f_contactable == "No":
        st.markdown("""
            <div style="background: #fff7ed; border: 1.5px solid #fed7aa; border-left: 5px solid #ea580c; padding: 12px 16px; border-radius: 8px; margin: 12px 0;">
                <b style="color: #9a3412; font-size: 0.98rem;">📞 Student Not Contactable:</b>
                <span style="color: #c2410c; font-size: 0.9rem; margin-left: 8px;">Retention Status will be automatically recorded as <b>Unable_to_track</b>. Please select the specific calling disposition below.</span>
            </div>
        """, unsafe_allow_html=True)

        existing_rem = row_preset.get("nocont_reason", current_student["left_not_working_remarks"].strip())
        def_nocont_idx = 0
        if existing_rem in PLACEMENT_UNABLE_TO_TRACK_OPTIONS:
            def_nocont_idx = PLACEMENT_UNABLE_TO_TRACK_OPTIONS.index(existing_rem)

        c_no1, c_no2 = st.columns(2)
        with c_no1:
            st.markdown('<div class="question-pill-header">Call Remarks / Unable To Track Reason (Picture 4 Col 2)</div>', unsafe_allow_html=True)
            f_nocont_reason = st.selectbox(
                "Call Remarks / Unable To Track Reason",
                PLACEMENT_UNABLE_TO_TRACK_OPTIONS,
                index=def_nocont_idx,
                label_visibility="collapsed",
                key=f"plc_sel_nocont_{current_student['row_num']}"
            )

        with c_no2:
            st.markdown('<div class="question-pill-header">Verification Date</div>', unsafe_allow_html=True)
            f_vdate_no = st.date_input(
                "Verification Date",
                value=parse_date_safe(row_preset.get("verification_date", current_student["verification_date"])) or date.today(),
                label_visibility="collapsed",
                key=f"plc_date_no_{current_student['row_num']}"
            )

        f_remarks_2_no = st.text_area(
            "Additional Calling Remarks (Optional / SPOC Notes)",
            value=row_preset.get("remarks_2", current_student["remarks_2"]),
            height=70,
            key=f"plc_ta_rem2_no_{current_student['row_num']}",
            placeholder="E.g. Called twice, ringing no response..."
        )

        st.markdown("<br>", unsafe_allow_html=True)
        btn_label_no = f"💾 Update & Insert Disposition (Row #{current_student['row_num']})" if (is_already_verified or is_edit_mode) else "💾 Submit Call Disposition (Not Contactable)"
        if st.button(btn_label_no, type="primary", use_container_width=True, key=f"plc_sub_no_{current_student['row_num']}"):
            with st.spinner("⚡ High Speed Sync to Google Sheets..."):
                payload = [
                    "No",                         # Q: Contactable
                    "",                           # R: Assessment Given
                    "",                           # S: Got Certificate
                    "",                           # T: Have_You_Got_This_Job_From_Anudip
                    "Unable_to_track",            # U: Retention Status
                    "",                           # V: How Many Months Working
                    "",                           # W: Current Company Name
                    "",                           # X: Current Salary
                    "",                           # Y: Current Designation
                    "",                           # Z: DOJ
                    "",                           # AA: Need any further job
                    "",                           # AB: Net Promoter Score
                    str(f_vdate_no),              # AC: Verification Date
                    f_nocont_reason,              # AD: Left The Job /Not Working/Not - Contactable Remarks
                    "N/A",                        # AE: Not Joined Remarks
                    "",                           # AF: Satisfied With Conversation
                    f_remarks_2_no.strip()        # AG: Remarks 2
                ]

                try:
                    placement_ws.update(values=[payload], range_name=f"Q{current_student['row_num']}:AG{current_student['row_num']}")
                    fetch_placement_master_data.clear()

                    st.session_state.placement_live_history.insert(0, (current_student['row_num'], list(payload)))
                    st.session_state.placement_live_history = st.session_state.placement_live_history[:20]
                    st.session_state.pop("placement_editing_row", None)

                    st.toast(f"✅ Saved Target #{current_q_idx + 1} ({current_student['student_name']}) as Not Contactable!", icon="✅")

                    if current_q_idx + 1 < total_assigned_queue:
                        st.session_state.placement_queue_index = current_q_idx + 1
                        next_s = active_queue_students[current_q_idx + 1]
                        save_placement_progress(current_spoc, current_q_idx + 1, next_s["contact_number"], active_call_index=st.session_state.get("placement_active_call_index", 0))

                    time.sleep(0.3)
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error saving to Google Sheets: {ex}")

    # --------------------------------------------------------------------------
    # ✅ CONDITION: IF CONTACTABLE == YES -> Retention Status Options (Picture 3 & 4)
    # --------------------------------------------------------------------------
    else:
        st.markdown("<div style='margin-top: 14px;'></div>", unsafe_allow_html=True)

        col_q1, col_q2, col_q3 = st.columns(3)

        with col_q1:
            st.markdown('<div class="question-pill-header">Assessment Given?</div>', unsafe_allow_html=True)
            def_ass_val = row_preset.get("assessment_given", current_student["assessment_given"]).upper()
            def_ass_idx = 0 if def_ass_val != "NO" else 1
            f_assessment = st.radio(
                "Assessment Given?",
                ["YES", "NO"],
                index=def_ass_idx,
                horizontal=False,
                label_visibility="collapsed",
                key=f"plc_rad_ass_{current_student['row_num']}"
            )

        with col_q2:
            st.markdown('<div class="question-pill-header">Got Certificate?</div>', unsafe_allow_html=True)
            def_cert_val = row_preset.get("got_certificate", current_student["got_certificate"]).upper()
            def_cert_idx = 0 if def_cert_val != "NO" else 1
            f_certificate = st.radio(
                "Got Certificate?",
                ["YES", "NO"],
                index=def_cert_idx,
                horizontal=False,
                label_visibility="collapsed",
                key=f"plc_rad_cert_{current_student['row_num']}"
            )

        with col_q3:
            st.markdown('<div class="question-pill-header">Got This Job From Anudip?</div>', unsafe_allow_html=True)
            def_job_val = row_preset.get("got_job_from_anudip", current_student["got_job_from_anudip"]).upper()
            def_got_job_idx = 0 if def_job_val != "NO" else 1
            f_got_job = st.radio(
                "Got This Job From Anudip?",
                ["YES", "NO"],
                index=def_got_job_idx,
                horizontal=False,
                label_visibility="collapsed",
                key=f"plc_rad_job_{current_student['row_num']}"
            )

        st.markdown("<hr style='margin: 18px 0;'>", unsafe_allow_html=True)

        # RETENTION STATUS (SPECIFIED EXACT 6 OPTIONS FOR CONTACTABLE == YES)
        st.markdown("""
            <div style="font-weight: 800; color: #0f4c81; font-size: 1.08rem; margin-bottom: 8px;">
                💼 Retention & Employment Status
            </div>
        """, unsafe_allow_html=True)

        existing_ret = row_preset.get("retention_status", current_student["retention_status"]).strip()
        def_ret_idx = 0
        if existing_ret in PLACEMENT_RETENTION_OPTIONS_YES:
            def_ret_idx = PLACEMENT_RETENTION_OPTIONS_YES.index(existing_ret)

        f_retention = st.selectbox(
            "5. Retention Status",
            PLACEMENT_RETENTION_OPTIONS_YES,
            index=def_ret_idx,
            key=f"plc_sel_ret_{current_student['row_num']}"
        )

        has_company_details = f_retention in [
            "Working in same job",
            "Working in different job",
            "Left_The_Job",
            "Will joined after some days"
        ]

        if f_retention == "Working in same job":
            st.markdown("""
                <div style="background: #f0fdf4; border: 1.5px solid #86efac; border-left: 5px solid #16a34a; padding: 10px 14px; border-radius: 8px; margin: 10px 0; color: #166534; font-size: 0.92rem; font-weight: 700;">
                    💼 Working in Same Job: Company details auto-filled from Placement Profile (Editable if needed):
                </div>
            """, unsafe_allow_html=True)

            c_emp1, c_emp2, c_emp3 = st.columns(3)
            with c_emp1:
                def_months_idx = 2
                existing_m = row_preset.get("months", current_student["how_many_months"])
                if existing_m in PLACEMENT_MONTHS_OPTIONS:
                    def_months_idx = PLACEMENT_MONTHS_OPTIONS.index(existing_m)
                f_months = st.selectbox(
                    "6. How Many Months Working?",
                    PLACEMENT_MONTHS_OPTIONS,
                    index=def_months_idx,
                    key=f"plc_sel_months_{current_student['row_num']}"
                )

            with c_emp2:
                def_comp = row_preset.get("company", current_student["current_company"] or current_student["company_name"])
                f_company = st.text_input(
                    "7. Current Company Name (Auto-filled)",
                    value=def_comp,
                    key=f"plc_txt_comp_{current_student['row_num']}"
                )

            with c_emp3:
                def_sal = row_preset.get("salary", current_student["current_salary"] or current_student["salary"])
                f_salary = st.text_input(
                    "8. Current Salary / Month (Auto-filled)",
                    value=str(def_sal),
                    key=f"plc_txt_sal_{current_student['row_num']}"
                )

            c_emp4, c_emp5, c_emp6 = st.columns(3)
            with c_emp4:
                def_desig = row_preset.get("designation", current_student["current_designation"] or current_student["designation"])
                f_designation = st.text_input(
                    "9. Current Designation (Auto-filled)",
                    value=def_desig,
                    key=f"plc_txt_desig_{current_student['row_num']}"
                )

            with c_emp5:
                def_doj = row_preset.get("doj", parse_date_safe(current_student["current_doj"]) or parse_date_safe(current_student["doj"]) or date.today())
                f_doj = st.date_input(
                    "10. DOJ (Current Job - Auto-filled)",
                    value=def_doj,
                    key=f"plc_date_doj_{current_student['row_num']}"
                )

            with c_emp6:
                def_further_val = row_preset.get("need_further_job", current_student["need_further_job"]).upper()
                def_further_idx = 1 if def_further_val != "YES" else 0
                f_further_job = st.radio(
                    "11. Need Any Further Job?",
                    ["YES", "NO"],
                    index=def_further_idx,
                    horizontal=True,
                    key=f"plc_rad_further_{current_student['row_num']}"
                )

            f_left_remarks = "N/A - Currently Working"
            f_not_joined_remarks = "N/A"

        elif f_retention == "Left_The_Job":
            st.markdown("""
                <div style="background: #fef2f2; border: 1.5px solid #fecaca; border-left: 5px solid #ef4444; padding: 10px 14px; border-radius: 8px; margin: 10px 0; color: #991b1b; font-size: 0.92rem; font-weight: 700;">
                    🚪 Left The Job: Placed company details auto-filled below. Please select the reason for leaving (Picture 4 Col 5):
                </div>
            """, unsafe_allow_html=True)

            c_lj1, c_lj2, c_lj3 = st.columns(3)
            with c_lj1:
                def_comp = row_preset.get("company", current_student["current_company"] or current_student["company_name"])
                f_company = st.text_input(
                    "Placed Company Left (Auto-filled)",
                    value=def_comp,
                    key=f"plc_txt_comp_{current_student['row_num']}"
                )
            with c_lj2:
                def_sal = row_preset.get("salary", current_student["current_salary"] or current_student["salary"])
                f_salary = st.text_input(
                    "Last Salary / Month (Auto-filled)",
                    value=str(def_sal),
                    key=f"plc_txt_sal_{current_student['row_num']}"
                )
            with c_lj3:
                def_desig = row_preset.get("designation", current_student["current_designation"] or current_student["designation"])
                f_designation = st.text_input(
                    "Designation Left (Auto-filled)",
                    value=def_desig,
                    key=f"plc_txt_desig_{current_student['row_num']}"
                )

            c_lj4, c_lj5 = st.columns(2)
            with c_lj4:
                def_doj = row_preset.get("doj", parse_date_safe(current_student["current_doj"]) or parse_date_safe(current_student["doj"]) or date.today())
                f_doj = st.date_input(
                    "Date of Joining (DOJ - Auto-filled)",
                    value=def_doj,
                    key=f"plc_date_doj_{current_student['row_num']}"
                )
            with c_lj5:
                def_further_val = row_preset.get("need_further_job", current_student["need_further_job"]).upper()
                def_further_idx = 1 if def_further_val == "NO" else 0
                f_further_job = st.radio(
                    "11. Need Any Further Job?",
                    ["YES", "NO"],
                    index=def_further_idx,
                    horizontal=True,
                    key=f"plc_rad_further_{current_student['row_num']}"
                )

            existing_left = row_preset.get("left_remarks", current_student["left_not_working_remarks"].strip())
            def_left_idx = 0
            if existing_left in PLACEMENT_LEFT_JOB_OPTIONS:
                def_left_idx = PLACEMENT_LEFT_JOB_OPTIONS.index(existing_left)

            f_left_remarks = st.selectbox(
                "12. Left The Job Reason (Picture 4 Col 5)",
                PLACEMENT_LEFT_JOB_OPTIONS,
                index=def_left_idx,
                key=f"plc_sel_left_rem_{current_student['row_num']}"
            )
            f_months = ""
            f_not_joined_remarks = "N/A"

        elif f_retention == "Working in different job":
            st.markdown("""
                <div style="background: #eff6ff; border: 1.5px solid #bfdbfe; border-left: 5px solid #2563eb; padding: 10px 14px; border-radius: 8px; margin: 10px 0; color: #1e40af; font-size: 0.92rem; font-weight: 700;">
                    🔄 Working in Different Job: Please update all new company details, designation, and salary below:
                </div>
            """, unsafe_allow_html=True)

            c_emp1, c_emp2, c_emp3 = st.columns(3)
            with c_emp1:
                def_months_idx = 0
                existing_m = row_preset.get("months", current_student["how_many_months"])
                if existing_m in PLACEMENT_MONTHS_OPTIONS:
                    def_months_idx = PLACEMENT_MONTHS_OPTIONS.index(existing_m)
                f_months = st.selectbox(
                    "6. How Many Months in New Job?",
                    PLACEMENT_MONTHS_OPTIONS,
                    index=def_months_idx,
                    key=f"plc_sel_months_{current_student['row_num']}"
                )

            with c_emp2:
                saved_comp = current_student["current_company"] if current_student["current_company"] != current_student["company_name"] else ""
                def_comp = row_preset.get("company", saved_comp)
                f_company = st.text_input(
                    "7. New Company Name (Enter Updates)",
                    value=def_comp,
                    placeholder="Enter new employer name...",
                    key=f"plc_txt_comp_{current_student['row_num']}"
                )

            with c_emp3:
                saved_sal = current_student["current_salary"] if current_student["current_salary"] != current_student["salary"] else ""
                def_sal = row_preset.get("salary", saved_sal)
                f_salary = st.text_input(
                    "8. New Salary / Month (Enter Updates)",
                    value=str(def_sal),
                    placeholder="E.g. 15000",
                    key=f"plc_txt_sal_{current_student['row_num']}"
                )

            c_emp4, c_emp5, c_emp6 = st.columns(3)
            with c_emp4:
                saved_desig = current_student["current_designation"] if current_student["current_designation"] != current_student["designation"] else ""
                def_desig = row_preset.get("designation", saved_desig)
                f_designation = st.text_input(
                    "9. New Designation (Enter Updates)",
                    value=def_desig,
                    placeholder="E.g. Associate / Executive",
                    key=f"plc_txt_desig_{current_student['row_num']}"
                )

            with c_emp5:
                def_doj = row_preset.get("doj", parse_date_safe(current_student["current_doj"]) or date.today())
                f_doj = st.date_input(
                    "10. DOJ (New Job)",
                    value=def_doj,
                    key=f"plc_date_doj_{current_student['row_num']}"
                )

            with c_emp6:
                def_further_val = row_preset.get("need_further_job", current_student["need_further_job"]).upper()
                def_further_idx = 1 if def_further_val != "YES" else 0
                f_further_job = st.radio(
                    "11. Need Any Further Job?",
                    ["YES", "NO"],
                    index=def_further_idx,
                    horizontal=True,
                    key=f"plc_rad_further_{current_student['row_num']}"
                )

            f_left_remarks = "N/A - Working in different job"
            f_not_joined_remarks = "N/A"

        elif f_retention == "Will joined after some days":
            st.markdown("""
                <div style="background: #fdf4ff; border: 1.5px solid #f0abfc; border-left: 5px solid #c026d3; padding: 10px 14px; border-radius: 8px; margin: 10px 0; color: #86198f; font-size: 0.92rem; font-weight: 700;">
                    📅 Will Join Upcoming Job: Enter or confirm joining company and onboarding details below:
                </div>
            """, unsafe_allow_html=True)

            c_wj1, c_wj2, c_wj3 = st.columns(3)
            with c_wj1:
                def_comp = row_preset.get("company", current_student["current_company"] or current_student["company_name"])
                f_company = st.text_input(
                    "Joining Company Name",
                    value=def_comp,
                    placeholder="Enter joining company...",
                    key=f"plc_txt_comp_{current_student['row_num']}"
                )

            with c_wj2:
                def_sal = row_preset.get("salary", current_student["current_salary"] or current_student["salary"])
                f_salary = st.text_input(
                    "Offered Salary / Month",
                    value=str(def_sal),
                    placeholder="E.g. 12000",
                    key=f"plc_txt_sal_{current_student['row_num']}"
                )

            with c_wj3:
                def_desig = row_preset.get("designation", current_student["current_designation"] or current_student["designation"])
                f_designation = st.text_input(
                    "Offered Designation",
                    value=def_desig,
                    placeholder="E.g. Trainee / Executive",
                    key=f"plc_txt_desig_{current_student['row_num']}"
                )

            c_wj4, c_wj5, c_wj6 = st.columns(3)
            with c_wj4:
                def_doj = row_preset.get("doj", parse_date_safe(current_student["current_doj"]) or date.today())
                f_doj = st.date_input(
                    "Expected Date of Joining (DOJ)",
                    value=def_doj,
                    key=f"plc_date_doj_{current_student['row_num']}"
                )

            with c_wj5:
                existing_left = row_preset.get("left_remarks", current_student["left_not_working_remarks"].strip())
                def_wj_idx = 0
                if existing_left in PLACEMENT_WILL_JOIN_OPTIONS:
                    def_wj_idx = PLACEMENT_WILL_JOIN_OPTIONS.index(existing_left)

                f_left_remarks = st.selectbox(
                    "Joining Status / Reason",
                    PLACEMENT_WILL_JOIN_OPTIONS,
                    index=def_wj_idx,
                    key=f"plc_sel_wj_rem_{current_student['row_num']}"
                )

            with c_wj6:
                def_further_val = row_preset.get("need_further_job", current_student["need_further_job"]).upper()
                def_further_idx = 0 if def_further_val == "YES" else 1
                f_further_job = st.radio(
                    "11. Need Any Further Job?",
                    ["YES", "NO"],
                    index=def_further_idx,
                    horizontal=True,
                    key=f"plc_rad_further_{current_student['row_num']}"
                )

            f_months = ""
            f_not_joined_remarks = "N/A"

        elif f_retention == "Not_working_at_all":
            st.markdown("""
                <div style="background: #fff7ed; border: 1px solid #fed7aa; padding: 10px 14px; border-radius: 8px; margin: 10px 0; color: #9a3412; font-size: 0.92rem; font-weight: 700;">
                    ⚠️ Student Not Working At All — Select Reasons from Picture 4:
                </div>
            """, unsafe_allow_html=True)

            c_nw1, c_nw2, c_nw3 = st.columns([1.4, 1.4, 1.1])
            with c_nw1:
                existing_left = row_preset.get("left_remarks", current_student["left_not_working_remarks"].strip())
                def_nw_idx = 0
                if existing_left in PLACEMENT_NOT_WORKING_OPTIONS:
                    def_nw_idx = PLACEMENT_NOT_WORKING_OPTIONS.index(existing_left)

                f_left_remarks = st.selectbox(
                    "12. Not Working Reason (Picture 4 Col 1)",
                    PLACEMENT_NOT_WORKING_OPTIONS,
                    index=def_nw_idx,
                    key=f"plc_sel_nw_rem_{current_student['row_num']}"
                )

            with c_nw2:
                if f_left_remarks == "Did_not_joined_job_due_to_personal_issue":
                    sub_options = PLACEMENT_NOT_JOINED_PERSONAL_OPTIONS
                    sub_lbl = "13. Personal Issue Detail (Picture 4 Col 3)"
                elif f_left_remarks == "Did_not_joined_job_due_to_profile_issue":
                    sub_options = PLACEMENT_NOT_JOINED_PROFILE_OPTIONS
                    sub_lbl = "13. Profile Issue Detail (Picture 4 Col 4)"
                else:
                    sub_options = ["N/A"]
                    sub_lbl = "13. Not Joined Detail"

                existing_nj = row_preset.get("not_joined_remarks", current_student["not_joined_remarks"].strip())
                def_nj_idx = 0
                if existing_nj in sub_options:
                    def_nj_idx = sub_options.index(existing_nj)

                f_not_joined_remarks = st.selectbox(
                    sub_lbl,
                    sub_options,
                    index=def_nj_idx,
                    key=f"plc_sel_sub_rem_{current_student['row_num']}"
                )

            with c_nw3:
                def_further_val = row_preset.get("need_further_job", current_student["need_further_job"]).upper()
                def_further_idx = 1 if def_further_val == "NO" else 0
                f_further_job = st.radio(
                    "11. Need Any Further Job?",
                    ["YES", "NO"],
                    index=def_further_idx,
                    horizontal=True,
                    key=f"plc_rad_further_{current_student['row_num']}"
                )

            f_company = ""
            f_salary = ""
            f_designation = ""
            f_doj = ""
            f_months = ""

        else:
            st.info("ℹ️ Student confirmed name but declined to disclose current employment or salary.")
            c_cn1, _ = st.columns([1.2, 2.0])
            with c_cn1:
                def_further_val = row_preset.get("need_further_job", current_student["need_further_job"]).upper()
                def_further_idx = 0 if def_further_val == "YES" else 1
                f_further_job = st.radio(
                    "11. Need Any Further Job?",
                    ["YES", "NO"],
                    index=def_further_idx,
                    horizontal=True,
                    key=f"plc_rad_further_{current_student['row_num']}"
                )
            f_left_remarks = "Confirmed Name But Didn't Share Any Information."
            f_not_joined_remarks = "N/A"
            f_company = ""
            f_salary = ""
            f_designation = ""
            f_doj = ""
            f_months = ""

        st.markdown("<hr style='margin: 16px 0;'>", unsafe_allow_html=True)
        st.markdown("<div style='font-weight: 700; color: #0f4c81; font-size: 1.02rem; margin-bottom: 8px;'>⭐ Feedback, NPS & SPOC Notes</div>", unsafe_allow_html=True)

        c_fb1, c_fb2, c_fb3 = st.columns(3)
        with c_fb1:
            def_nps_idx = 0
            existing_nps = str(row_preset.get("nps", current_student["nps"])).strip()
            if existing_nps in PLACEMENT_NPS_OPTIONS:
                def_nps_idx = PLACEMENT_NPS_OPTIONS.index(existing_nps)
            f_nps = st.selectbox(
                "14. Net Promoter Score (NPS)",
                PLACEMENT_NPS_OPTIONS,
                index=def_nps_idx,
                key=f"plc_sel_nps_{current_student['row_num']}"
            )

        with c_fb2:
            def_sat_idx = 0
            existing_sat = row_preset.get("satisfied", current_student["satisfied_with_conversation"]).strip()
            if existing_sat in PLACEMENT_SATISFIED_OPTIONS:
                def_sat_idx = PLACEMENT_SATISFIED_OPTIONS.index(existing_sat)
            f_satisfied = st.selectbox(
                "15. Satisfied With Conversation?",
                PLACEMENT_SATISFIED_OPTIONS,
                index=def_sat_idx,
                key=f"plc_sel_sat_{current_student['row_num']}"
            )

        with c_fb3:
            f_vdate = st.date_input(
                "16. Verification Date",
                value=parse_date_safe(row_preset.get("verification_date", current_student["verification_date"])) or date.today(),
                key=f"plc_date_vdate_{current_student['row_num']}"
            )

        f_remarks_2 = st.text_area(
            "17. Remarks 2 (Additional SPOC Notes)",
            value=row_preset.get("remarks_2", current_student["remarks_2"]),
            height=70,
            key=f"plc_ta_rem2_{current_student['row_num']}",
            placeholder="Type any specific comments or call observation..."
        )

        st.markdown("<br>", unsafe_allow_html=True)
        btn_submit_label = f"💾 Update & Insert Placement Verification (Row #{current_student['row_num']})" if (is_edit_mode or is_already_verified) else "💾 Submit Placement Verification"
        if st.button(btn_submit_label, type="primary", use_container_width=True, key=f"plc_btn_submit_{current_student['row_num']}"):
            with st.spinner("⚡ High Speed Sync to Google Sheets..."):
                payload = [
                    "Yes",                                                      # Q: Contactable
                    f_assessment,                                               # R: Assessment Given
                    f_certificate,                                              # S: Got Certificate
                    f_got_job,                                                  # T: Have_You_Got_This_Job_From_Anudip
                    f_retention,                                                # U: Retention Status
                    f_months if f_retention in ["Working in same job", "Working in different job"] else "",  # V: How Many Months Working
                    f_company if has_company_details else "",                   # W: Current Company Name
                    str(f_salary) if has_company_details else "",               # X: Current Salary
                    f_designation if has_company_details else "",               # Y: Current Designation
                    str(f_doj) if has_company_details else "",                  # Z: DOJ
                    f_further_job,                                              # AA: Need any further job
                    str(f_nps),                                                 # AB: Net Promoter Score
                    str(f_vdate),                                               # AC: Verification Date
                    f_left_remarks,                                             # AD: Left The Job /Not Working/Not - Contactable Remarks
                    f_not_joined_remarks,                                       # AE: Not Joined Remarks
                    f_satisfied,                                                # AF: Satisfied With Conversation
                    f_remarks_2.strip()                                         # AG: Remarks 2
                ]

                try:
                    placement_ws.update(values=[payload], range_name=f"Q{current_student['row_num']}:AG{current_student['row_num']}")
                    fetch_placement_master_data.clear()

                    st.session_state.placement_live_history.insert(0, (current_student['row_num'], list(payload)))
                    st.session_state.placement_live_history = st.session_state.placement_live_history[:20]
                    st.session_state.pop("placement_editing_row", None)

                    st.toast(f"✅ Target #{current_q_idx + 1} ({current_student['student_name']}) updated and inserted successfully in Google Sheets!", icon="🎯")

                    if current_q_idx + 1 < total_assigned_queue:
                        st.session_state.placement_queue_index = current_q_idx + 1
                        next_s = active_queue_students[current_q_idx + 1]
                        save_placement_progress(current_spoc, current_q_idx + 1, next_s["contact_number"], active_call_index=st.session_state.get("placement_active_call_index", 0))

                    time.sleep(0.3)
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error saving to Google Sheets: {ex}")

    st.markdown('</div>', unsafe_allow_html=True)

    # ==========================================================================
    # 📋 SECTION: SPOC WISE LATEST VERIFIED CALLS (Z-A)
    # ==========================================================================
    st.markdown("""
        <div class="profile-card-enhanced" style="margin-top: 1.2rem; border-top: 4px solid #1a73e8;">
            <div style="font-weight: 800; color: #0f4c81; font-size: 1.15rem; margin-bottom: 0.8rem;">
                📋 Recent Verified Calls ({spoc_name})
            </div>
    """.replace("{spoc_name}", display_scope_name), unsafe_allow_html=True)

    called_records = []
    live_map = {r_num: r_data for r_num, r_data in st.session_state.placement_live_history}

    for s in active_queue_students:
        r_num = s["row_num"]
        if r_num in live_map:
            l_data = live_map[r_num]
            called_records.append({
                "student_obj": s,
                "target_num": s["queue_index"] + 1,
                "row_num": r_num,
                "student_name": s["student_name"],
                "contact_number": s["contact_number"],
                "company_name": s["company_name"],
                "contactable": l_data[0] if len(l_data) > 0 else s["contactable"],
                "assessment_given": l_data[1] if len(l_data) > 1 else s["assessment_given"],
                "got_certificate": l_data[2] if len(l_data) > 2 else s["got_certificate"],
                "got_job_from_anudip": l_data[3] if len(l_data) > 3 else s["got_job_from_anudip"],
                "retention": l_data[4] if len(l_data) > 4 else s["retention_status"],
                "months": l_data[5] if len(l_data) > 5 else s["how_many_months"],
                "current_company": l_data[6] if len(l_data) > 6 else s["current_company"],
                "current_salary": l_data[7] if len(l_data) > 7 else s["current_salary"],
                "current_designation": l_data[8] if len(l_data) > 8 else s["current_designation"],
                "current_doj": l_data[9] if len(l_data) > 9 else s["current_doj"],
                "need_further_job": l_data[10] if len(l_data) > 10 else s["need_further_job"],
                "nps": l_data[11] if len(l_data) > 11 else s["nps"],
                "verification_date": l_data[12] if len(l_data) > 12 else s["verification_date"],
                "remarks": l_data[13] if len(l_data) > 13 else s["left_not_working_remarks"],
                "not_joined_remarks": l_data[14] if len(l_data) > 14 else s["not_joined_remarks"],
                "satisfied": l_data[15] if len(l_data) > 15 else s["satisfied_with_conversation"],
                "remarks_2": l_data[16] if len(l_data) > 16 else s["remarks_2"]
            })
        elif s["contactable"]:
            called_records.append({
                "student_obj": s,
                "target_num": s["queue_index"] + 1,
                "row_num": r_num,
                "student_name": s["student_name"],
                "contact_number": s["contact_number"],
                "company_name": s["company_name"],
                "contactable": s["contactable"],
                "assessment_given": s["assessment_given"],
                "got_certificate": s["got_certificate"],
                "got_job_from_anudip": s["got_job_from_anudip"],
                "retention": s["retention_status"],
                "months": s["how_many_months"],
                "current_company": s["current_company"],
                "current_salary": s["current_salary"],
                "current_designation": s["current_designation"],
                "current_doj": s["current_doj"],
                "need_further_job": s["need_further_job"],
                "nps": s["nps"],
                "verification_date": s["verification_date"],
                "remarks": s["left_not_working_remarks"],
                "not_joined_remarks": s["not_joined_remarks"],
                "satisfied": s["satisfied_with_conversation"],
                "remarks_2": s["remarks_2"]
            })

    latest_5 = list(reversed(called_records))[:5]
    if not latest_5:
        st.info("No verified calls completed yet in this session.")
    else:
        for it in latest_5:
            c_r1, c_r2, c_r3, c_r4 = st.columns([1, 3, 3, 1.2])
            with c_r1:
                st.markdown(f"**Target #{it['target_num']}**")
            with c_r2:
                badge = "🟢 Contacted (Yes)" if it["contactable"].lower() == "yes" else "🔴 Not Contactable (No)"
                st.markdown(f"**{it['student_name']}** (`{it['contact_number']}`)<br><small>{badge}</small>", unsafe_allow_html=True)
            with c_r3:
                st.markdown(f"*{it['company_name']}*<br><small style='color: #64748b;'>{it['retention'] or it['remarks'] or 'Verified'}</small>", unsafe_allow_html=True)
            with c_r4:
                # ✏️ Edit Button: Loads previous verification form so user can view, update and insert!
                if st.button("✏️ Edit", key=f"plc_edit_{it['row_num']}", use_container_width=True):
                    # Locate student index in active_queue_students
                    target_idx = None
                    for a_i, a_s in enumerate(active_queue_students):
                        if a_s["row_num"] == it["row_num"]:
                            target_idx = a_i
                            break

                    if target_idx is not None:
                        st.session_state.placement_queue_index = target_idx
                    else:
                        st.session_state.plc_perf_view = "🌟 All Team Combined (Portal Total)"
                        st.session_state.plc_perf_view_selector_box = "🌟 All Team Combined (Portal Total)"
                        global_idx = 0
                        for g_i, g_s in enumerate(all_placement_students):
                            if g_s["row_num"] == it["row_num"]:
                                global_idx = g_i
                                break
                        st.session_state.placement_queue_index = global_idx

                    row_k = it["row_num"]
                    # Store ALL previously verified values into preset for this row!
                    st.session_state[f"plc_preset_{row_k}"] = {
                        "contactable": "Yes" if str(it["contactable"]).strip().lower() == "yes" else "No",
                        "assessment_given": str(it.get("assessment_given", "YES")).upper(),
                        "got_certificate": str(it.get("got_certificate", "YES")).upper(),
                        "got_job_from_anudip": str(it.get("got_job_from_anudip", "YES")).upper(),
                        "retention_status": it["retention"] or "Working in same job",
                        "months": it.get("months", "3 Months"),
                        "company": it.get("current_company") or it["company_name"],
                        "salary": it.get("current_salary") or it["student_obj"].get("salary", ""),
                        "designation": it.get("current_designation") or it["student_obj"].get("designation", ""),
                        "doj": parse_date_safe(it.get("current_doj")) or parse_date_safe(it["student_obj"].get("doj")) or date.today(),
                        "need_further_job": str(it.get("need_further_job", "NO")).upper(),
                        "nps": str(it.get("nps", "10")),
                        "satisfied": it.get("satisfied", "Yes"),
                        "verification_date": parse_date_safe(it.get("verification_date")) or date.today(),
                        "left_remarks": it["remarks"],
                        "not_joined_remarks": it.get("not_joined_remarks", "N/A"),
                        "nocont_reason": it["remarks"] if str(it["contactable"]).lower() == "no" else "",
                        "remarks_2": it.get("remarks_2", "")
                    }

                    # Clear old widget state keys for this row so Streamlit forces re-read from preset
                    for k in list(st.session_state.keys()):
                        if f"_{row_k}" in k and k.startswith("plc_"):
                            st.session_state.pop(k, None)

                    st.session_state.placement_editing_row = it["row_num"]
                    save_placement_progress(current_spoc, st.session_state.placement_queue_index, it["contact_number"], active_call_index=st.session_state.get("placement_active_call_index", 0))
                    st.toast(f"Loaded previous record for {it['student_name']}! Ready for update & insert.", icon="✏️")
                    st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)
