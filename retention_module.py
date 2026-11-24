import streamlit as st
import streamlit.components.v1 as components
import urllib.parse
import gspread
from datetime import datetime, date
import time
import os
import json
import csv
import threading
from concurrent.futures import ThreadPoolExecutor

# ==============================================================================
# 🎯 RETENTION CONSTANTS & CONFIGURATION
# ==============================================================================
PROGRESS_RETENTION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spoc_retention_progress.json")
LOCAL_RETENTION_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "retention_data.csv")
DATA_CACHE_TTL = 900  # 15 minutes TTL

_CSV_FILE_LOCK = threading.Lock()
_RETENTION_BG_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ret_sync")

# Verification Outcome / Call Type (When Contactable == Yes)
RETENTION_OUTCOME_OPTIONS = [
    "Full Verification (Complete Survey)",
    "Disconnected,Did'nt Share All Info.",
    "Confirmed Name & Disconnected.",
    "Not a student of Anudip",
    "Language issue"
]

# Retention Status Options - Updated per requirements:
# Add "Left The Job" & Exclude "Unable to track"
RETENTION_STATUS_OPTIONS = [
    "Working in same job",
    "Working in different job",
    "Left The Job",
    "Not working at all"
]

# Survey reasons for 'Not working at all'
RETENTION_NOT_WORKING_OPTIONS = [
    "Did_not_joined_job_due_to_personal_issue",
    "Did_not_joined_job_due_to_profile_issue",
    "Did not get any information from the employer",
    "Did not get selected",
    "Did Not Attend Any Interview"
]

# Uncontactable Reasons (When Contactable == No)
RETENTION_UNABLE_TO_TRACK_OPTIONS = [
    "Did not respond to our call",
    "Switched off",
    "Incoming Call Is Not Available",
    "Network issue",
    "Wrong Number"
]

RETENTION_MONTHS_OPTIONS = [
    "Less than 1 Month", "1 Month", "2 Months", "3 Months", "4 Months", "5 Months", "6 Months",
    "7 Months", "8 Months", "9 Months", "10 Months", "11 Months", "12 Months", "More than 1 year",
    "Not Shared / Disconnected"
]

RETENTION_NPS_OPTIONS = [
    "10", "9", "8", "7", "6", "5", "4", "3", "2", "1", "0", "Don't Want To Share", "Call Disconnected / Not Shared"
]

RETENTION_REASON_LEFT_OPTIONS = [
    "Better salary / opportunity",
    "Distance / Relocation issue",
    "Health / Medical issue",
    "Higher studies / Exam preparation",
    "Family / Personal reasons",
    "Work environment / Timings",
    "Contract ended / Layoff",
    "Company closed",
    "Did not like job profile",
    "Other (Mention in remarks)"
]

# ==============================================================================
# 🛠️ HELPER UTILITIES
# ==============================================================================
def clean_phone(phone_val) -> str:
    if not phone_val:
        return ""
    digits = "".join(filter(str.isdigit, str(phone_val)))
    if len(digits) == 12 and digits.startswith("91"):
        return digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        return digits[1:]
    return digits

def parse_date_safe(d_val):
    if not d_val:
        return ""
    s = str(d_val).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return s

def load_all_retention_progress():
    try:
        if os.path.exists(PROGRESS_RETENTION_FILE):
            with open(PROGRESS_RETENTION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_retention_progress(spoc_name, queue_index, phone="", active_call_index=None):
    try:
        prog = load_all_retention_progress()
        s_key = (spoc_name or "").strip().lower()
        if not s_key:
            return
        if s_key not in prog:
            prog[s_key] = {}
        prog[s_key]["saved_queue_index"] = max(0, queue_index)
        if active_call_index is not None:
            prog[s_key]["saved_active_call_index"] = max(0, active_call_index)
        prog[s_key]["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(PROGRESS_RETENTION_FILE, "w", encoding="utf-8") as f:
            json.dump(prog, f, indent=2)
    except Exception:
        pass

def get_saved_retention_index(spoc_name, student_list):
    if not student_list:
        return 0, 0
    s_key = (spoc_name or "").strip().lower()
    prog = load_all_retention_progress()
    user_prog = prog.get(s_key, {})
    saved_q = user_prog.get("saved_queue_index", 0)
    saved_act = user_prog.get("saved_active_call_index", saved_q)
    return min(saved_q, len(student_list) - 1), min(saved_act, len(student_list) - 1)

# ==============================================================================
# 💾 DATA CACHING & BACKGROUND SHEET SYNC (COLUMNS Q:AI)
# ==============================================================================
def update_in_memory_retention_row(row_num, payload, call_status="Done", call_id="Call 1", concat=""):
    try:
        if "retention_master_rows" in st.session_state and st.session_state.retention_master_rows:
            m_rows = st.session_state.retention_master_rows
            if 0 < row_num <= len(m_rows):
                idx = row_num - 1
                curr = list(m_rows[idx])
                if len(curr) < 35:
                    curr.extend([""] * (35 - len(curr)))
                for i, val in enumerate(payload):
                    curr[16 + i] = str(val)
                curr[32] = str(call_status)
                curr[33] = str(call_id)
                curr[34] = str(concat)
                m_rows[idx] = curr
                st.session_state.retention_master_rows = m_rows
    except Exception:
        pass

def update_local_retention_csv(row_num, payload, call_status="Done", call_id="Call 1", concat=""):
    try:
        with _CSV_FILE_LOCK:
            if os.path.exists(LOCAL_RETENTION_CSV):
                with open(LOCAL_RETENTION_CSV, "r", encoding="utf-8") as f:
                    rows = list(csv.reader(f))
                if 0 < row_num <= len(rows):
                    idx = row_num - 1
                    curr = list(rows[idx])
                    if len(curr) < 35:
                        curr.extend([""] * (35 - len(curr)))
                    for i, val in enumerate(payload):
                        curr[16 + i] = str(val)
                    curr[32] = str(call_status)
                    curr[33] = str(call_id)
                    curr[34] = str(concat)
                    rows[idx] = curr
                    with open(LOCAL_RETENTION_CSV, "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerows(rows)
    except Exception:
        pass

def _bg_retention_sync_worker(ws, row_num, payload, call_status="Done", call_id="Call 1", concat=""):
    try:
        update_local_retention_csv(row_num, payload, call_status, call_id, concat)
        if ws:
            full_row_vals = list(payload) + [str(call_status), str(call_id), str(concat)]
            range_name = f"Q{row_num}:AI{row_num}"
            ws.update(values=[full_row_vals], range_name=range_name)
    except Exception as e:
        print(f"[Retention Sync Warning] Row {row_num}: {e}")

def dispatch_retention_sync(ws, row_num, payload, call_status="Done", call_id="Call 1", concat=""):
    _RETENTION_BG_EXECUTOR.submit(_bg_retention_sync_worker, ws, row_num, payload, call_status, call_id, concat)

@st.cache_data(ttl=DATA_CACHE_TTL)
def fetch_retention_master_data(_retention_ws):
    if _retention_ws is not None:
        try:
            vals = _retention_ws.get_all_values()
            if vals and len(vals) > 1:
                # Also refresh local CSV file cache
                try:
                    with _CSV_FILE_LOCK:
                        with open(LOCAL_RETENTION_CSV, "w", newline="", encoding="utf-8") as f:
                            csv.writer(f).writerows(vals)
                except Exception:
                    pass
                return vals
        except Exception:
            pass
    if os.path.exists(LOCAL_RETENTION_CSV):
        try:
            with open(LOCAL_RETENTION_CSV, "r", encoding="utf-8") as f:
                return list(csv.reader(f))
        except Exception:
            pass
    return []

# ==============================================================================
# 👥 BULLETPROOF DYNAMIC STUDENT RECORD PARSER (MAPPED BY EXACT HEADER NAME)
# ==============================================================================
def parse_all_retention_students(all_rows):
    if not all_rows or len(all_rows) <= 1:
        return []
    
    headers_raw = [str(h).strip() for h in all_rows[0]]
    headers_lower = [h.lower() for h in headers_raw]

    def find_col(name_patterns, default_idx=-1):
        for pat in name_patterns:
            p = pat.lower()
            # 1. Exact match
            for idx, h in enumerate(headers_lower):
                if h == p:
                    return idx
            # 2. Substring match
            for idx, h in enumerate(headers_lower):
                if p in h:
                    return idx
        return default_idx

    c_called_by    = find_col(["called by", "spoc", "called_by"], default_idx=0)
    c_cmis         = find_col(["cmisid", "cmis_id", "cmis id", "student code"], default_idx=1)
    c_name         = find_col(["student name", "student_name", "candidate name"], default_idx=2)
    c_phone        = find_col(["contact number", "mobile no", "mobile number", "phone"], default_idx=3)
    c_alt_phone    = find_col(["alt contact number", "alt phone", "alt mobile"], default_idx=4)
    c_gender       = find_col(["gender"], default_idx=5)
    c_center       = find_col(["center name", "center_name", "centre name", "centre"], default_idx=6)
    c_state        = find_col(["state"], default_idx=7)
    c_course       = find_col(["course", "course name"], default_idx=8)
    c_donor        = find_col(["donor name", "funder name", "donor"], default_idx=9)
    c_company      = find_col(["placed company", "company name"], default_idx=10)
    c_designation  = find_col(["designation"], default_idx=11)
    c_salary       = find_col(["salary"], default_idx=12)
    c_doj          = find_col(["date of joining"], default_idx=13)
    c_round        = find_col(["calling round"], default_idx=14)
    c_exiting_nps  = find_col(["exiting nps", "existing nps"], default_idx=15)

    c_contactable  = find_col(["contactable"], default_idx=16)
    c_outcome      = find_col(["verification outcome"], default_idx=17)
    c_ret_status   = find_col(["retention status"], default_idx=18)
    c_months       = find_col(["how many months"], default_idx=19)
    c_cur_comp     = find_col(["current company"], default_idx=20)
    c_nps          = find_col(["net promoter score"], default_idx=21)
    c_cur_sal      = find_col(["current salary"], default_idx=22)
    c_cur_des      = find_col(["current designation"], default_idx=23)
    c_cur_doj      = find_col(["doj", "current doj"], default_idx=24)
    c_reason_left  = find_col(["reason behind leaving"], default_idx=25)
    c_need_job     = find_col(["need any further job"], default_idx=26)
    c_vdate        = find_col(["verification date"], default_idx=27)
    c_remarks      = find_col(["remarks"], default_idx=28)
    c_profile_rem  = find_col(["personal/profile issue remarks", "profile issue remarks"], default_idx=29)
    c_remarks_2    = find_col(["remarks 2"], default_idx=30)
    c_remarks_3    = find_col(["remarks 3"], default_idx=31)
    c_status       = find_col(["call_status"], default_idx=32)
    c_call_id      = find_col(["call_id"], default_idx=33)
    c_concat       = find_col(["concat"], default_idx=34)

    def get_val(p, idx):
        return p[idx].strip() if (0 <= idx < len(p)) else ""

    students = []
    q_idx = 0
    for r_idx, row in enumerate(all_rows[1:], start=2):
        if not any(row):
            continue
        padded = list(row) + [""] * max(0, 36 - len(row))

        assigned_spoc = get_val(padded, c_called_by)
        cmis_id       = get_val(padded, c_cmis)
        student_name  = get_val(padded, c_name)
        contact_number= get_val(padded, c_phone)
        alt_contact   = get_val(padded, c_alt_phone)
        gender        = get_val(padded, c_gender)
        center_name   = get_val(padded, c_center)
        state         = get_val(padded, c_state)
        course        = get_val(padded, c_course)
        donor_name    = get_val(padded, c_donor)
        placed_company= get_val(padded, c_company)
        designation   = get_val(padded, c_designation)
        salary        = get_val(padded, c_salary)
        doj           = get_val(padded, c_doj)
        calling_round = get_val(padded, c_round) or "Call 1"
        exiting_nps   = get_val(padded, c_exiting_nps)

        contactable   = get_val(padded, c_contactable)
        outcome       = get_val(padded, c_outcome)
        ret_status    = get_val(padded, c_ret_status)
        how_months    = get_val(padded, c_months)
        cur_comp      = get_val(padded, c_cur_comp)
        nps           = get_val(padded, c_nps)
        cur_sal       = get_val(padded, c_cur_sal)
        cur_des       = get_val(padded, c_cur_des)
        cur_doj       = get_val(padded, c_cur_doj)
        reason_left   = get_val(padded, c_reason_left)
        need_job      = get_val(padded, c_need_job)
        vdate         = get_val(padded, c_vdate)
        remarks       = get_val(padded, c_remarks)
        profile_rem   = get_val(padded, c_profile_rem)
        remarks_2     = get_val(padded, c_remarks_2)
        remarks_3     = get_val(padded, c_remarks_3)
        call_status   = get_val(padded, c_status)
        call_id       = get_val(padded, c_call_id) or calling_round
        concat        = get_val(padded, c_concat)

        students.append({
            "row_num": r_idx,
            "queue_index": q_idx,
            "called_by": assigned_spoc,
            "cmis_id": cmis_id,
            "student_name": student_name,
            "contact_number": contact_number,
            "alt_contact_number": alt_contact,
            "gender": gender,
            "center_name": center_name,
            "state": state,
            "course": course,
            "donor_name": donor_name,
            "placed_company": placed_company,
            "designation": designation,
            "salary": salary,
            "doj": doj,
            "calling_round": calling_round,
            "exiting_nps": exiting_nps,
            "contactable": contactable,
            "verification_outcome": outcome,
            "retention_status": ret_status,
            "how_many_months": how_months,
            "current_company": cur_comp,
            "nps": nps,
            "current_salary": cur_sal,
            "current_designation": cur_des,
            "current_doj": cur_doj,
            "reason_leaving": reason_left,
            "need_further_job": need_job,
            "verification_date": vdate,
            "remarks": remarks,
            "personal_profile_remarks": profile_rem,
            "remarks_2": remarks_2,
            "remarks_3": remarks_3,
            "call_status": call_status,
            "call_id": call_id,
            "concat": concat
        })
        q_idx += 1
    return students

def get_retention_students_for_spoc(all_rows, spoc_name):
    if len(all_rows) <= 1:
        return []
    all_students = parse_all_retention_students(all_rows)
    spoc_clean = (spoc_name or "").strip().lower()
    ADMIN_USERS = {"nibedan", "pritam", "kalpana", "koushik"}
    is_admin = spoc_clean in ADMIN_USERS
    
    if is_admin:
        return all_students
    
    spoc_matches = [s for s in all_students if s.get("called_by", "").strip().lower() == spoc_clean]
    if spoc_matches:
        return spoc_matches
    
    unassigned = [s for s in all_students if not s.get("called_by", "").strip()]
    return unassigned if unassigned else all_students

def compute_retention_stats(students, live_history=None):
    live_map = {}
    if live_history:
        for item in live_history:
            r_num = item[0]
            p = item[1]
            if len(p) > 0:
                live_map[r_num] = str(p[0]).strip().lower()

    total_assigned = len(students)
    yes_cnt = 0
    no_cnt = 0
    fresh_list = []
    no_list = []
    yes_list = []

    for s in students:
        r_num = s["row_num"]
        cont = live_map.get(r_num, s.get("contactable", "").strip().lower())
        if cont == "yes":
            yes_cnt += 1
            yes_list.append(s)
        elif cont == "no":
            no_cnt += 1
            no_list.append(s)
        else:
            fresh_list.append(s)

    total_called = yes_cnt + no_cnt
    fresh_pending = len(fresh_list)
    pct = (yes_cnt / total_called * 100.0) if total_called > 0 else 0.0

    just_nums_text = "\n".join([clean_phone(s.get("contact_number", "")) for s in fresh_list if clean_phone(s.get("contact_number", ""))])
    no_nums_text = "\n".join([clean_phone(s.get("contact_number", "")) for s in no_list if clean_phone(s.get("contact_number", ""))])

    return {
        "total_assigned": total_assigned,
        "total_called": total_called,
        "yes_count": yes_cnt,
        "no_count": no_cnt,
        "fresh_pending": fresh_pending,
        "contactable_pct": pct,
        "fresh_list": fresh_list,
        "no_list": no_list,
        "yes_list": yes_list,
        "just_numbers_text": just_nums_text,
        "no_numbers_text": no_nums_text
    }

# ==============================================================================
# 📌 RETENTION PIN CONTROLS & POPUP QUEUE LISTS
# ==============================================================================
def toggle_pin_retention_fresh():
    st.session_state.pin_retention_fresh_call_list = not st.session_state.get("pin_retention_fresh_call_list", False)
    if st.session_state.pin_retention_fresh_call_list:
        st.session_state.pin_retention_no_call_list = False
        st.session_state.retention_fresh_queue_index = 0
        st.session_state.pop("retention_editing_row", None)
        st.session_state.pop("retention_active_recall", None)

def toggle_pin_retention_no():
    st.session_state.pin_retention_no_call_list = not st.session_state.get("pin_retention_no_call_list", False)
    if st.session_state.pin_retention_no_call_list:
        st.session_state.pin_retention_fresh_call_list = False
        if "retention_no_queue_index" not in st.session_state:
            st.session_state.retention_no_queue_index = 0

def unpin_retention_fresh():
    st.session_state.pin_retention_fresh_call_list = False
    st.session_state.pop("retention_editing_row", None)
    st.session_state.pop("retention_active_recall", None)

def unpin_retention_no():
    st.session_state.pin_retention_no_call_list = False
    st.session_state.pop("retention_editing_row", None)
    st.session_state.pop("retention_active_recall", None)

def render_retention_fresh_call_list(fresh_stats, current_spoc, all_retention_students=None, active_queue_students=None, is_admin=False, selected_perf_view=None, key_prefix="pop"):
    f_spoc = (current_spoc or "All Team").title()
    v_pending = fresh_stats.get("fresh_pending", 0)
    v_assigned = fresh_stats.get("total_assigned", 0)
    v_called = fresh_stats.get("total_called", 0)
    v_yes = fresh_stats.get("yes_count", 0)
    v_no = fresh_stats.get("no_count", 0)
    just_nums_text = fresh_stats.get("just_numbers_text", "")
    fresh_items = fresh_stats.get("fresh_list", [])

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
        st.success(f"🎉 Outstanding work! All {v_assigned} assigned retention calls for {f_spoc} have been completed.")
        return

    tab_nums, tab_queue = st.tabs(["📱 Just Numbers (Raw List)", "📞 Interactive Call List"])

    with tab_nums:
        st.caption(f"📋 Pending uncalled phone numbers ({v_pending} remaining). Copy or download below:")
        st.text_area(
            "Just Numbers",
            value=just_nums_text,
            height=160,
            key=f"ret_ta_just_nums_{f_spoc}_{key_prefix}",
            help="Click inside and press Ctrl+A / Ctrl+C to copy all pending numbers directly into your dialer."
        )

        c_dl1, c_dl2 = st.columns(2)
        with c_dl1:
            st.download_button(
                label=f"📥 Download Just Numbers ({v_pending})",
                data=just_nums_text,
                file_name=f"Retention_Fresh_Numbers_{f_spoc}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                mime="text/plain",
                use_container_width=True,
                key=f"ret_dl_txt_{f_spoc}_{key_prefix}"
            )
        with c_dl2:
            csv_lines = ["Target_Num,Phone_Number,Student_Name,Placed_Company,Designation,Salary"]
            for item in fresh_items:
                csv_lines.append(f"Target #{item.get('queue_index', 0)+1},{item['contact_number']},{item['student_name']},{item.get('placed_company','')},{item.get('designation','')},{item.get('salary','')}")
            st.download_button(
                label="📊 Download CSV Details",
                data="\n".join(csv_lines),
                file_name=f"Retention_Fresh_List_{f_spoc}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True,
                key=f"ret_dl_csv_{f_spoc}_{key_prefix}"
            )

    with tab_queue:
        q_search = st.text_input(
            "Search phone or student name",
            placeholder="Type 10-digit number or name...",
            key=f"ret_q_search_{f_spoc}_{key_prefix}",
            label_visibility="collapsed"
        )
        filtered = fresh_items
        if q_search.strip():
            clean_q = clean_phone(q_search.strip())
            name_q = q_search.strip().lower()
            filtered = [
                x for x in fresh_items
                if (clean_q and (clean_q in clean_phone(x["contact_number"]) or clean_q in clean_phone(x.get("alt_contact_number", ""))))
                or (name_q in x["student_name"].lower())
                or (f"#{x.get('queue_index', 0)+1}" == q_search.strip())
                or (f"#{x.get('row_num', 0)}" == q_search.strip())
            ]

        st.caption(f"Showing **{min(len(filtered), 50)}** of **{len(filtered)}** pending calls:")
        for f_idx, it in enumerate(filtered[:50]):
            col_i1, col_i2 = st.columns([3, 1.2])
            with col_i1:
                st.markdown(f"**Target #{it.get('queue_index', 0)+1}**: `{it['contact_number']}` &nbsp;·&nbsp; *{it['student_name']}* ({it.get('placed_company', '')})")
            with col_i2:
                if st.button("📞 Load", key=f"ret_btn_ld_{f_idx}_{it['row_num']}_{key_prefix}", use_container_width=True):
                    st.session_state.pin_retention_no_call_list = False
                    st.session_state.pin_retention_fresh_call_list = True
                    target_fr_idx = 0
                    for fr_i, fr_s in enumerate(fresh_items):
                        if fr_s["row_num"] == it["row_num"]:
                            target_fr_idx = fr_i
                            break
                    st.session_state.retention_fresh_queue_index = target_fr_idx

                    target_idx = None
                    if active_queue_students:
                        for a_i, a_s in enumerate(active_queue_students):
                            if a_s["row_num"] == it["row_num"]:
                                target_idx = a_i
                                break
                    if target_idx is not None:
                        st.session_state.retention_queue_index = target_idx
                    else:
                        st.session_state.retention_queue_index = it.get("queue_index", 0)

                    st.session_state.pop("retention_editing_row", None)
                    st.session_state.pop("retention_active_recall", None)
                    save_retention_progress(
                        current_spoc or it.get("called_by", ""),
                        st.session_state.retention_queue_index,
                        it["contact_number"],
                        active_call_index=st.session_state.retention_queue_index
                    )
                    st.toast(f"Loaded Target #{target_idx + 1 if target_idx is not None else 1} ({it['student_name']})!", icon="🎯")
                    st.rerun()

def render_retention_not_contactable_list(fresh_stats, current_spoc, all_retention_students=None, active_queue_students=None, is_admin=False, selected_perf_view=None, key_prefix="pop"):
    f_spoc = (current_spoc or "All Team").title()
    no_items = fresh_stats.get("no_list", [])
    no_count = len(no_items)
    no_nums_text = fresh_stats.get("no_numbers_text", "\n".join([clean_phone(s["contact_number"]) for s in no_items if clean_phone(s.get("contact_number"))]))

    st.markdown(f"""
        <div style="background: linear-gradient(135deg, #fff7ed 0%, #ffffff 100%); border: 1.5px solid #fed7aa; border-left: 5px solid #ea580c; border-radius: 8px; padding: 10px 14px; margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                <span style="font-weight: 800; color: #9a3412; font-size: 1.05rem;">📞 Not Contactable ("No" Calls): {f_spoc}</span>
                <span style="background: #ffedd5; color: #c2410c; border: 1px solid #fed7aa; padding: 2px 8px; border-radius: 12px; font-weight: 700; font-size: 0.82rem;">{no_count} Calls</span>
            </div>
            <div style="margin-top: 6px; font-size: 0.82rem; color: #7c2d12;">
                💡 <b>High Speed Dynamic Re-call:</b> Click <b>🔁 Re-Call</b> on any student to instantly load their profile and form. If reached, change to <b>'Yes'</b> to verify!
            </div>
        </div>
    """, unsafe_allow_html=True)

    if not no_items:
        st.info("👍 No 'Not Contactable' calls recorded yet.")
        return

    tab_nums, tab_queue = st.tabs(["📱 Just Numbers (Raw List)", "📞 Interactive Re-Call List"])

    with tab_nums:
        st.caption(f"📋 Unreached 'No' contact numbers ({no_count} calls). Copy or download below:")
        st.text_area(
            "Just Numbers",
            value=no_nums_text,
            height=160,
            key=f"ret_ta_no_nums_{f_spoc}_{key_prefix}",
            help="Click inside and press Ctrl+A / Ctrl+C to copy all unreached numbers directly into your dialer."
        )

        c_dl1, c_dl2 = st.columns(2)
        with c_dl1:
            st.download_button(
                label=f"📥 Download Just Numbers ({no_count})",
                data=no_nums_text,
                file_name=f"Retention_No_Numbers_{f_spoc}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                mime="text/plain",
                use_container_width=True,
                key=f"ret_dl_no_txt_{f_spoc}_{key_prefix}"
            )
        with c_dl2:
            csv_lines = ["Target_Num,Phone_Number,Student_Name,Placed_Company,Designation,Reason"]
            for item in no_items:
                csv_lines.append(f"Target #{item.get('queue_index', 0)+1},{item['contact_number']},{item['student_name']},{item.get('placed_company','')},{item.get('designation','')},{item.get('remarks','')}")
            st.download_button(
                label="📊 Download CSV Details",
                data="\n".join(csv_lines),
                file_name=f"Retention_Not_Contactable_List_{f_spoc}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True,
                key=f"ret_dl_no_csv_{f_spoc}_{key_prefix}"
            )

    with tab_queue:
        q_search = st.text_input(
            "Search phone or student name",
            placeholder="Type 10-digit number or name...",
            key=f"ret_q_no_search_{f_spoc}_{key_prefix}",
            label_visibility="collapsed"
        )
        filtered = no_items
        if q_search.strip():
            clean_q = clean_phone(q_search.strip())
            name_q = q_search.strip().lower()
            filtered = [
                x for x in no_items
                if (clean_q and (clean_q in clean_phone(x["contact_number"]) or clean_q in clean_phone(x.get("alt_contact_number", ""))))
                or (name_q in x["student_name"].lower())
                or (f"#{x.get('queue_index', 0)+1}" == q_search.strip())
                or (f"#{x.get('row_num', 0)}" == q_search.strip())
            ]

        st.caption(f"Showing **{min(len(filtered), 50)}** of **{len(filtered)}** 'No' calls:")
        for no_idx, it in enumerate(filtered[:50]):
            col_i1, col_i2 = st.columns([3, 1.2])
            with col_i1:
                st.markdown(f"**Target #{it.get('queue_index', 0)+1}**: `{it['contact_number']}` &nbsp;·&nbsp; *{it['student_name']}* ({it.get('remarks', 'Not Contactable')})")
            with col_i2:
                if st.button("🔁 Re-Call", key=f"ret_btn_rc_{no_idx}_{it['row_num']}_{key_prefix}", use_container_width=True):
                    st.session_state.pin_retention_fresh_call_list = False
                    st.session_state.pin_retention_no_call_list = True
                    target_no_idx = 0
                    for no_i, no_s in enumerate(no_items):
                        if no_s["row_num"] == it["row_num"]:
                            target_no_idx = no_i
                            break
                    st.session_state.retention_no_queue_index = target_no_idx

                    target_idx = None
                    if active_queue_students:
                        for a_i, a_s in enumerate(active_queue_students):
                            if a_s["row_num"] == it["row_num"]:
                                target_idx = a_i
                                break
                    if target_idx is not None:
                        st.session_state.retention_queue_index = target_idx
                    else:
                        st.session_state.retention_queue_index = it.get("queue_index", 0)

                    st.session_state.retention_active_recall = it["row_num"]
                    save_retention_progress(
                        current_spoc or it.get("called_by", ""),
                        st.session_state.retention_queue_index,
                        it["contact_number"],
                        active_call_index=st.session_state.retention_queue_index
                    )
                    st.toast(f"Re-Calling Target #{target_idx + 1 if target_idx is not None else 1} ({it['student_name']})!", icon="🔁")
                    st.rerun()

# ==============================================================================
# 📊 UI DASHBOARD RENDERER (RESPECTIVE SPOC WISE - NO ROUND/CENTER FILTER)
# ==============================================================================
def render_retention_dashboard(retention_ws, current_spoc, is_admin=False):
    # Auto Cache Busting: If in-memory rows are stale or missing 'Called By', reload fresh data
    needs_refresh = False
    if "retention_master_rows" not in st.session_state or not st.session_state.retention_master_rows:
        needs_refresh = True
    else:
        first_h = [str(x).strip().lower() for x in st.session_state.retention_master_rows[0]]
        if "called by" not in first_h:
            needs_refresh = True

    if needs_refresh:
        fetch_retention_master_data.clear()
        st.session_state.retention_master_rows = fetch_retention_master_data(retention_ws)

    if "retention_live_history" not in st.session_state:
        st.session_state.retention_live_history = []
    if "retention_queue_index" not in st.session_state:
        st.session_state.retention_queue_index = 0

    all_rows = st.session_state.retention_master_rows
    if len(all_rows) <= 1:
        st.warning("⚠️ No student records found in Retention Verification Sheet.")
        return

    all_students = parse_all_retention_students(all_rows)
    spoc_clean = (current_spoc or "").strip().lower()

    # Header section
    admin_tag = "(Admin View)" if is_admin else ""
    st.markdown(f"""
        <div style="background: linear-gradient(135deg, #059669 0%, #047857 100%); padding: 18px 24px; border-radius: 12px; margin-bottom: 16px; color: white; box-shadow: 0 4px 14px rgba(5,150,105,0.2);">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
                <div>
                    <h2 style="margin: 0; font-size: 1.6rem; font-weight: 800; color: white;">🎯 Retention Calling & Verification Portal</h2>
                    <p style="margin: 4px 0 0 0; font-size: 0.95rem; opacity: 0.92;">Post-Placement Retention, Job Verification & Respective SPOC Calling Engine</p>
                </div>
                <div style="background: rgba(255,255,255,0.2); padding: 8px 16px; border-radius: 20px; font-weight: 700; font-size: 0.9rem;">
                    👤 Caller: {current_spoc.title()} {admin_tag}
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # SPOC-Wise Called By Selector
    all_spocs = sorted(list({s["called_by"].strip().title() for s in all_students if s.get("called_by", "").strip()}))
    
    if is_admin:
        perf_options = ["🌟 All Team Combined (Portal Total)"] + all_spocs
        def_p_idx = 0
        if current_spoc.title() in perf_options:
            def_p_idx = perf_options.index(current_spoc.title())
        selected_spoc_view = st.selectbox(
            "Called By",
            perf_options,
            index=def_p_idx,
            key="ret_sel_spoc_view"
        )
        
        if selected_spoc_view == "🌟 All Team Combined (Portal Total)":
            active_students = all_students
            display_scope = "All Team Combined"
        else:
            active_students = [s for s in all_students if s.get("called_by", "").strip().lower() == selected_spoc_view.strip().lower()]
            display_scope = selected_spoc_view
    else:
        # Non-admin SPOC: Locked strictly to their own assigned calls
        active_students = [s for s in all_students if s.get("called_by", "").strip().lower() == spoc_clean]
        display_scope = current_spoc.title()

    for idx, s in enumerate(active_students):
        s["queue_index"] = idx

    if not active_students:
        st.info(f"ℹ️ No candidates found for **{display_scope}**.")
        return

    # Metrics Boards
    stats = compute_retention_stats(active_students, st.session_state.retention_live_history)
    b_col1, b_col2 = st.columns(2)
    with b_col1:
        st.markdown(f"""
            <div style="background: #f0fdf4; border: 1.5px solid #86efac; border-left: 6px solid #16a34a; border-radius: 12px; padding: 14px 18px; min-height: 140px;">
                <div style="font-size: 0.82rem; font-weight: 700; color: #166534; text-transform: uppercase;">📋 Calling Pipeline ({display_scope})</div>
                <div style="display: flex; align-items: baseline; gap: 12px; margin-top: 4px;">
                    <span style="font-size: 2.2rem; font-weight: 900; color: #15803d;">{stats['fresh_pending']}</span>
                    <span style="font-size: 1.05rem; font-weight: 800; color: #166534;">Fresh Calls Pending</span>
                </div>
                <div style="margin-top: 10px; padding-top: 8px; border-top: 1px dashed #bbf7d0; display: flex; justify-content: space-between; font-size: 0.88rem;">
                    <span>Assigned: <b>{stats['total_assigned']}</b></span>
                    <span>Called: <b>{stats['total_called']}</b></span>
                    <span style="color: #16a34a;">Contacted: <b>{stats['yes_count']}</b></span>
                    <span style="color: #dc2626;">Unreached: <b>{stats['no_count']}</b></span>
                </div>
            </div>
        """, unsafe_allow_html=True)
    with b_col2:
        st.markdown(f"""
            <div style="background: #eff6ff; border: 1.5px solid #93c5fd; border-left: 6px solid #2563eb; border-radius: 12px; padding: 14px 18px; min-height: 140px;">
                <div style="font-size: 0.82rem; font-weight: 700; color: #1e40af; text-transform: uppercase;">🎯 Contactability Rate ({display_scope})</div>
                <div style="display: flex; align-items: baseline; gap: 12px; margin-top: 4px;">
                    <span style="font-size: 2.2rem; font-weight: 900; color: #1d4ed8;">{stats['contactable_pct']:.1f}%</span>
                    <span style="font-size: 1.05rem; font-weight: 800; color: #1e40af;">Contactable Yes</span>
                </div>
                <div style="margin-top: 10px; padding-top: 8px; border-top: 1px dashed #bfdbfe; display: flex; justify-content: space-between; font-size: 0.88rem;">
                    <span style="color: #16a34a;">Yes: <b>{stats['yes_count']}</b></span>
                    <span>Attempted: <b>{stats['total_called']}</b></span>
                    <span style="color: #dc2626;">No: <b>{stats['no_count']}</b></span>
                </div>
            </div>
        """, unsafe_allow_html=True)

    v_pending = stats.get("fresh_pending", 0)
    v_no = stats.get("no_count", 0)
    display_scope_name = display_scope

    # Popover buttons for Fresh Calls and Not Contactable (User Picture 1)
    col_pop1, col_pop2 = st.columns(2)
    with col_pop1:
        st.markdown('<div class="fresh-call-header-btn">', unsafe_allow_html=True)
        with st.popover(f"🟢 Fresh Calls ({v_pending} Pending) ⌄", use_container_width=True):
            render_retention_fresh_call_list(
                stats,
                display_scope_name,
                all_retention_students=all_students,
                active_queue_students=active_students,
                is_admin=is_admin,
                selected_perf_view=display_scope_name,
                key_prefix="pop"
            )
            st.markdown("---")
            chk_pin_fresh = st.checkbox(
                "📌 Keep Fresh List pinned above form",
                value=st.session_state.get("pin_retention_fresh_call_list", False),
                key=f"ret_chk_pin_fresh_{display_scope_name}"
            )
            if chk_pin_fresh != st.session_state.get("pin_retention_fresh_call_list", False):
                st.session_state.pin_retention_fresh_call_list = chk_pin_fresh
                if chk_pin_fresh:
                    st.session_state.pin_retention_no_call_list = False
                    st.session_state.retention_fresh_queue_index = 0
                    st.session_state.pop("retention_editing_row", None)
                    st.session_state.pop("retention_active_recall", None)
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    with col_pop2:
        st.markdown('<div class="nocontact-header-btn">', unsafe_allow_html=True)
        with st.popover(f"📞 Not Contactable ({v_no}) ⌄", use_container_width=True):
            render_retention_not_contactable_list(
                stats,
                display_scope_name,
                all_retention_students=all_students,
                active_queue_students=active_students,
                is_admin=is_admin,
                selected_perf_view=display_scope_name,
                key_prefix="pop"
            )
            st.markdown("---")
            chk_pin_no = st.checkbox(
                "📌 Keep 'No' List pinned above form",
                value=st.session_state.get("pin_retention_no_call_list", False),
                key=f"ret_chk_pin_no_{display_scope_name}"
            )
            if chk_pin_no != st.session_state.get("pin_retention_no_call_list", False):
                st.session_state.pin_retention_no_call_list = chk_pin_no
                if chk_pin_no:
                    st.session_state.pin_retention_fresh_call_list = False
                    if "retention_no_queue_index" not in st.session_state:
                        st.session_state.retention_no_queue_index = 0
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # 1-Click Pin / Unpin Quick Controls Bar
    col_tgl1, col_tgl2 = st.columns(2)
    with col_tgl1:
        if v_pending > 0:
            is_f_pinned = bool(st.session_state.get("pin_retention_fresh_call_list", False))
            btn_lbl_f = "📌 Unpin Fresh List" if is_f_pinned else "📌 Pin Fresh List above form"
            st.button(
                btn_lbl_f,
                key=f"ret_tgl_btn_fresh_{display_scope_name}",
                on_click=toggle_pin_retention_fresh,
                use_container_width=True
            )
    with col_tgl2:
        if v_no > 0:
            is_no_pinned = bool(st.session_state.get("pin_retention_no_call_list", False))
            btn_lbl_no = "📌 Unpin 'No' List" if is_no_pinned else "📌 Pin 'No' List above form"
            st.button(
                btn_lbl_no,
                key=f"ret_tgl_btn_no_{display_scope_name}",
                on_click=toggle_pin_retention_no,
                use_container_width=True
            )

    # Pinned Cards (if active)
    if st.session_state.get("pin_retention_fresh_call_list") and v_pending > 0:
        st.markdown('<div class="fresh-pinned-card">', unsafe_allow_html=True)
        col_pf1, col_pf2 = st.columns([5, 1])
        with col_pf1:
            st.markdown(f"<div style='font-weight: 800; color: #166534; font-size: 1.05rem;'>🟢 Pinned Fresh Calling Queue ({display_scope_name}) — {v_pending} Pending</div>", unsafe_allow_html=True)
        with col_pf2:
            st.button("✖ Unpin List", key=f"ret_btn_unpin_fresh_{display_scope_name}", on_click=unpin_retention_fresh, use_container_width=True)
        render_retention_fresh_call_list(
            stats,
            display_scope_name,
            all_retention_students=all_students,
            active_queue_students=active_students,
            is_admin=is_admin,
            selected_perf_view=display_scope_name,
            key_prefix="pin"
        )
        st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state.get("pin_retention_no_call_list") and v_no > 0:
        st.markdown('<div class="nocontact-pinned-card">', unsafe_allow_html=True)
        col_pn1, col_pn2 = st.columns([5, 1])
        with col_pn1:
            st.markdown(f"<div style='font-weight: 800; color: #9a3412; font-size: 1.05rem;'>📞 Pinned Not Contactable Queue ('No' Calls) ({display_scope_name}) — {v_no} Calls</div>", unsafe_allow_html=True)
        with col_pn2:
            st.button("✖ Unpin List", key=f"ret_btn_unpin_no_{display_scope_name}", on_click=unpin_retention_no, use_container_width=True)
        render_retention_not_contactable_list(
            stats,
            display_scope_name,
            all_retention_students=all_students,
            active_queue_students=active_students,
            is_admin=is_admin,
            selected_perf_view=display_scope_name,
            key_prefix="pin"
        )
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

    # Determine Queue Mode
    no_queue_students = stats.get("no_list", [])
    fresh_queue_students = stats.get("fresh_list", [])
    is_no_mode = bool(st.session_state.get("pin_retention_no_call_list") and len(no_queue_students) > 0)
    is_fresh_mode = bool(not is_no_mode and st.session_state.get("pin_retention_fresh_call_list") and len(fresh_queue_students) > 0)

    if is_no_mode:
        working_queue = no_queue_students
        total_assigned_queue = len(working_queue)
        if "retention_no_queue_index" not in st.session_state:
            st.session_state.retention_no_queue_index = 0
        current_q_idx = min(st.session_state.retention_no_queue_index, total_assigned_queue - 1)
        current_q_idx = max(0, current_q_idx)
        st.session_state.retention_no_queue_index = current_q_idx
        curr_student = working_queue[current_q_idx]
    elif is_fresh_mode:
        working_queue = fresh_queue_students
        total_assigned_queue = len(working_queue)
        if "retention_fresh_queue_index" not in st.session_state:
            st.session_state.retention_fresh_queue_index = 0
        current_q_idx = min(st.session_state.retention_fresh_queue_index, total_assigned_queue - 1)
        current_q_idx = max(0, current_q_idx)
        st.session_state.retention_fresh_queue_index = current_q_idx
        curr_student = working_queue[current_q_idx]
    else:
        working_queue = active_students
        total_assigned_queue = len(working_queue)
        if "retention_queue_index" not in st.session_state:
            st.session_state.retention_queue_index = 0
        current_q_idx = min(st.session_state.retention_queue_index, total_assigned_queue - 1)
        current_q_idx = max(0, current_q_idx)
        st.session_state.retention_queue_index = current_q_idx
        curr_student = working_queue[current_q_idx]

    cur_idx = current_q_idx
    total_q = total_assigned_queue

    # Quick Search Bar + 5 Navigation Buttons (Exact Image Match)
    c_search, c_fetch, c_start, c_prev, c_next, c_clear, c_refresh = st.columns([2.6, 1.3, 0.85, 0.85, 0.85, 1.05, 1.05])

    search_inp = c_search.text_input(
        "Search or Target",
        placeholder="Search phone or enter Target # (e.g. 71, 302)...",
        label_visibility="collapsed",
        key="ret_quick_search_input"
    )

    if c_fetch.button("⚡ Fetch Details", use_container_width=True, type="primary", key="ret_btn_fetch_details"):
        target = search_inp.strip()
        if target:
            clean_num = target.lstrip("#").strip()
            found_target = None
            target_idx = None

            if clean_num.isdigit():
                t_num = int(clean_num)
                if 1 <= t_num <= len(working_queue):
                    target_idx = t_num - 1
                    found_target = working_queue[target_idx]
                else:
                    for s in all_students:
                        if s["queue_index"] + 1 == t_num or s["row_num"] == t_num:
                            found_target = s
                            for a_idx, a_s in enumerate(working_queue):
                                if a_s["row_num"] == s["row_num"]:
                                    target_idx = a_idx
                                    break
                            break

            if not found_target:
                c_phone = clean_phone(target)
                if c_phone:
                    for idx, s in enumerate(working_queue):
                        if c_phone in clean_phone(s["contact_number"]) or c_phone in clean_phone(s.get("alt_contact_number", "")):
                            target_idx = idx
                            found_target = s
                            break
                    if not found_target:
                        for s in all_students:
                            if c_phone in clean_phone(s["contact_number"]) or c_phone in clean_phone(s.get("alt_contact_number", "")):
                                found_target = s
                                break

            if not found_target:
                t_lower = target.lower()
                for idx, s in enumerate(working_queue):
                    if t_lower in s["student_name"].lower():
                        target_idx = idx
                        found_target = s
                        break
                if not found_target:
                    for s in all_students:
                        if t_lower in s["student_name"].lower():
                            found_target = s
                            break

            if found_target:
                if target_idx is not None:
                    if is_no_mode:
                        st.session_state.retention_no_queue_index = target_idx
                    elif is_fresh_mode:
                        st.session_state.retention_fresh_queue_index = target_idx
                    else:
                        st.session_state.retention_queue_index = target_idx
                else:
                    st.session_state.retention_queue_index = found_target.get("queue_index", 0)

                row_k = found_target["row_num"]
                for k in list(st.session_state.keys()):
                    if f"_{row_k}" in k and k.startswith("ret_"):
                        st.session_state.pop(k, None)

                st.toast(f"Loaded Target #{found_target.get('queue_index', 0)+1} ({found_target['student_name']})!", icon="⚡")
                st.rerun()
            else:
                st.warning(f"No candidate record found matching '{target}'.")

    # 1. ⏮ #1 Button
    if c_start.button("⏮ #1", use_container_width=True, help="Jump to Target #1", disabled=(current_q_idx == 0 or total_assigned_queue == 0)):
        if is_no_mode:
            st.session_state.retention_no_queue_index = 0
        elif is_fresh_mode:
            st.session_state.retention_fresh_queue_index = 0
        else:
            st.session_state.retention_queue_index = 0
        st.session_state.pop("retention_editing_row", None)
        st.session_state.pop("retention_active_recall", None)
        st.toast("Jumped to Target #1!", icon="⏮️")
        st.rerun()

    # 2. ⬅ Prev Button
    if c_prev.button("⬅ Prev", use_container_width=True, disabled=(current_q_idx <= 0 or total_assigned_queue == 0)):
        if is_no_mode:
            st.session_state.retention_no_queue_index = max(0, current_q_idx - 1)
        elif is_fresh_mode:
            st.session_state.retention_fresh_queue_index = max(0, current_q_idx - 1)
        else:
            st.session_state.retention_queue_index = max(0, current_q_idx - 1)
        st.session_state.pop("retention_editing_row", None)
        st.session_state.pop("retention_active_recall", None)
        st.rerun()

    # 3. Next ➡ Button
    if c_next.button("Next ➡", use_container_width=True, disabled=(current_q_idx >= total_assigned_queue - 1 or total_assigned_queue == 0)):
        if is_no_mode:
            st.session_state.retention_no_queue_index = min(total_assigned_queue - 1, current_q_idx + 1)
        elif is_fresh_mode:
            st.session_state.retention_fresh_queue_index = min(total_assigned_queue - 1, current_q_idx + 1)
        else:
            st.session_state.retention_queue_index = min(total_assigned_queue - 1, current_q_idx + 1)
        st.session_state.pop("retention_editing_row", None)
        st.session_state.pop("retention_active_recall", None)
        st.rerun()

    # 4. 🧹 Clear Form Button
    if c_clear.button("🧹 Clear Form", use_container_width=True):
        row_k = curr_student["row_num"]
        st.session_state.pop("retention_editing_row", None)
        st.session_state.pop("retention_active_recall", None)
        keys_to_remove = [k for k in st.session_state.keys() if f"_{row_k}" in k and k.startswith("ret_")]
        for k in keys_to_remove:
            st.session_state.pop(k, None)
        st.toast("Form cleared for current candidate!", icon="🧹")
        st.rerun()

    # 5. 🔄 Refresh DB Button
    if c_refresh.button("🔄 Refresh DB", use_container_width=True):
        st.session_state.pop("retention_master_rows", None)
        if hasattr(fetch_retention_master_data, "clear"):
            fetch_retention_master_data.clear()
        st.cache_data.clear()
        st.toast("Database cache refreshed from Google Sheets!", icon="🔄")
        st.rerun()

    # Progress bar
    prog_pct = min((current_q_idx + 1) / total_assigned_queue, 1.0) if total_assigned_queue > 0 else 0
    st.progress(prog_pct)

    # Calling Target Banner + Copy Phone + Skip
    col_t1, col_t2 = st.columns([5, 1.1])
    phone_clean = clean_phone(curr_student.get("contact_number", ""))

    if is_no_mode:
        banner_bg = "linear-gradient(135deg, #fff7ed 0%, #ffedd5 100%)"
        banner_border = "#ea580c"
        banner_text_col = "#9a3412"
        banner_title_html = f"📞 Calling Not Contactable Target <b>#{current_q_idx + 1} of {total_assigned_queue}</b> (Row #{curr_student['row_num']})"
    elif is_fresh_mode:
        banner_bg = "linear-gradient(135deg, #f0fdf4 0%, #e0f2fe 100%)"
        banner_border = "#16a34a"
        banner_text_col = "#15803d"
        banner_title_html = f"🟢 Calling Fresh Target <b>#{current_q_idx + 1} of {total_assigned_queue}</b> (Row #{curr_student['row_num']})"
    else:
        banner_bg = "linear-gradient(135deg, #e8f0fe 0%, #f0f7ff 100%)"
        banner_border = "#1a73e8"
        banner_text_col = "#1e3a8a"
        banner_title_html = f"🎯 Calling Target <b>#{current_q_idx + 1} of {total_assigned_queue}</b>"

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
                background: {banner_bg};
                padding: 8px 16px;
                border-radius: 8px;
                border-left: 5px solid {banner_border};
                display: flex;
                justify-content: space-between;
                align-items: center;
                height: 48px;
            }}
            .banner-left {{
                font-size: 1.0rem;
                color: {banner_text_col};
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
                <span>{banner_title_html}</span>
                <span>·</span>
                <span style="color: #0f172a;">{curr_student['student_name']}</span>
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
        if st.button("⏭️ Skip", use_container_width=True, key=f"ret_skip_btn_{curr_student['row_num']}"):
            st.session_state.pop("retention_editing_row", None)
            st.session_state.pop("retention_active_recall", None)
            if is_no_mode:
                st.session_state.retention_no_queue_index = min(total_assigned_queue - 1, current_q_idx + 1)
            elif is_fresh_mode:
                st.session_state.retention_fresh_queue_index = min(total_assigned_queue - 1, current_q_idx + 1)
            else:
                st.session_state.retention_queue_index = min(total_assigned_queue - 1, current_q_idx + 1)
            st.toast("Skipped to next target", icon="⏭️")
            st.rerun()

    # Candidate Profile Header Card
    p_phone = clean_phone(curr_student.get("contact_number", ""))
    alt_phone = clean_phone(curr_student.get("alt_contact_number", ""))
    wa_url = f"https://wa.me/91{p_phone}" if p_phone else "#"
    call_url = f"tel:{p_phone}" if p_phone else "#"
    assigned_display = curr_student.get("called_by", "Unassigned")

    st.markdown(f"""
        <div style="background: white; border-radius: 12px; border: 1.5px solid #e2e8f0; padding: 18px; margin: 12px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 10px;">
                <div>
                    <span style="font-size: 1.4rem; font-weight: 800; color: #0f172a;">{curr_student['student_name']}</span>
                    <span style="margin-left: 10px; background: #e0f2fe; color: #0369a1; padding: 3px 10px; border-radius: 12px; font-size: 0.82rem; font-weight: 700;">CMIS: {curr_student['cmis_id']}</span>
                    <span style="margin-left: 6px; background: #f1f5f9; color: #475569; padding: 3px 10px; border-radius: 12px; font-size: 0.82rem; font-weight: 600;">{curr_student['gender'].title()}</span>
                    <span style="margin-left: 6px; background: #dcfce7; color: #166534; padding: 3px 10px; border-radius: 12px; font-size: 0.82rem; font-weight: 700;">Assigned SPOC: {assigned_display}</span>
                </div>
                <div style="display: flex; gap: 10px;">
                    <a href="{call_url}" style="text-decoration: none; background: #2563eb; color: white; padding: 6px 14px; border-radius: 8px; font-weight: 700; font-size: 0.9rem;">📞 Call: {p_phone}</a>
                    <a href="{wa_url}" target="_blank" style="text-decoration: none; background: #16a34a; color: white; padding: 6px 14px; border-radius: 8px; font-weight: 700; font-size: 0.9rem;">💬 WhatsApp</a>
                </div>
            </div>
            <div style="margin-top: 14px; display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; font-size: 0.9rem; background: #f8fafc; padding: 12px; border-radius: 8px;">
                <div>🏢 <b>Placed Company:</b> <span style="color: #0369a1; font-weight: 700;">{curr_student['placed_company']}</span></div>
                <div>💼 <b>Designation:</b> {curr_student['designation']}</div>
                <div>💰 <b>Placed Salary:</b> {curr_student['salary']}</div>
                <div>📅 <b>DOJ:</b> {curr_student['doj']}</div>
                <div>🏫 <b>Center:</b> {curr_student['center_name']}</div>
                <div>📍 <b>State:</b> {curr_student['state']}</div>
                <div>🎓 <b>Course:</b> {curr_student['course']}</div>
                <div>🤝 <b>Donor:</b> {curr_student['donor_name']}</div>
                <div>📞 <b>Alt Phone:</b> {alt_phone or 'N/A'}</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Verification Form
    st.markdown("<h3 style='margin-top: 18px; color: #047857;'>📝 Retention Verification Questionnaire</h3>", unsafe_allow_html=True)

    was_previously_yes = curr_student.get("contactable", "").strip().lower() == "yes"
    was_previously_no = curr_student.get("contactable", "").strip().lower() == "no"

    if was_previously_yes:
        st.markdown("""
            <div style="background: #f0fdf4; border: 1.5px solid #86efac; border-left: 5px solid #16a34a; padding: 10px 14px; border-radius: 8px; margin: 10px 0 14px 0;">
                <span style="font-weight: 800; color: #166534; font-size: 0.95rem;">🔒 Previously Contacted & Verified (Contactable = Yes)</span>
                <div style="font-size: 0.85rem; color: #15803d; margin-top: 3px;">
                    Per telecalling policy, this contact was already verified reachable and cannot be downgraded to 'No'. You can review, edit, or update all answers and retention details below.
                </div>
            </div>
        """, unsafe_allow_html=True)
        f_contactable = "Yes"
    else:
        # If previously No, caller can update to Yes ("Then Yes (Contactable)")!
        # If fresh, caller can choose Yes or No.
        cont_idx = 1 if was_previously_no else 0
        f_contactable = st.radio(
            "1. Is the Student Contactable?",
            ["Yes", "No"],
            index=cont_idx,
            horizontal=True,
            key=f"ret_rad_cont_{curr_student['row_num']}"
        )

    # Case 1: Uncontactable (Contactable == No)
    if f_contactable == "No":
        st.markdown("<div style='background: #fef2f2; border: 1.5px solid #fecaca; border-left: 5px solid #ef4444; padding: 12px; border-radius: 8px; margin: 12px 0;'>⚠️ <b>Call Unsuccessful:</b> Please select the uncontactable reason.</div>", unsafe_allow_html=True)
        no_c1, no_c2 = st.columns(2)
        with no_c1:
            def_no_idx = 0
            if curr_student.get("remarks") in RETENTION_UNABLE_TO_TRACK_OPTIONS:
                def_no_idx = RETENTION_UNABLE_TO_TRACK_OPTIONS.index(curr_student.get("remarks"))
            f_no_reason = st.selectbox("Reason for Not Contactable", RETENTION_UNABLE_TO_TRACK_OPTIONS, index=def_no_idx, key=f"ret_sel_no_{curr_student['row_num']}")
        with no_c2:
            st.date_input("Verification Date", value=date.today(), disabled=True, key=f"ret_dt_no_{curr_student['row_num']}")
        
        f_no_remarks = st.text_area("Optional Calling Remarks", value=curr_student.get("remarks_2", ""), placeholder="E.g. Switched off, tried 2 times...", key=f"ret_ta_no_{curr_student['row_num']}")

        if st.button("💾 Submit Call Disposition (Not Contactable)", type="primary", use_container_width=True, key=f"ret_btn_sub_no_{curr_student['row_num']}"):
            payload = [
                "No",               # Q: Contactable
                "N/A",              # R: Verification Outcome
                "Unable_to_track",  # S: Retention Status
                "",                 # T: How many months
                "",                 # U: Current Company Name
                "",                 # V: Net Promoter Score
                "",                 # W: Current Salary
                "",                 # X: Current Designation
                "",                 # Y: DOJ
                f_no_reason,        # Z: Reason Behind leaving the Job
                "No",               # AA: Need any further job
                str(date.today()),  # AB: Verification Date
                f_no_reason,        # AC: Remarks
                "N/A",              # AD: Personal/Profile issue Remarks
                f_no_remarks.strip(),# AE: Remarks 2
                ""                  # AF: Remarks 3
            ]
            r_num = curr_student["row_num"]
            c_round = curr_student.get("calling_round", "Call 1")
            concat_val = f"{current_spoc}{c_round}"
            update_in_memory_retention_row(r_num, payload, call_status="Done", call_id=c_round, concat=concat_val)
            dispatch_retention_sync(retention_ws, r_num, payload, call_status="Done", call_id=c_round, concat=concat_val)
            save_retention_progress(current_spoc, cur_idx + 1, curr_student["contact_number"], active_call_index=cur_idx)
            
            st.session_state.retention_live_history = [item for item in st.session_state.retention_live_history if item[0] != r_num]
            st.session_state.retention_live_history.insert(0, (r_num, list(payload)))
            
            st.toast(f"✅ Saved #{cur_idx + 1} ({curr_student['student_name']}) as Not Contactable!", icon="🚫")
            if is_no_mode:
                if current_q_idx + 1 < total_assigned_queue:
                    st.session_state.retention_no_queue_index = current_q_idx + 1
            elif is_fresh_mode:
                if current_q_idx + 1 < total_assigned_queue:
                    st.session_state.retention_fresh_queue_index = current_q_idx + 1
            else:
                if current_q_idx + 1 < total_assigned_queue:
                    st.session_state.retention_queue_index = current_q_idx + 1
            time.sleep(0.1)
            st.rerun()

    # Case 2: Contactable == Yes
    else:
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        st.markdown("""
            <div style="font-weight: 700; color: #166534; margin-bottom: 6px;">
                📞 Verification Outcome / Call Type (Contactable = Yes)
            </div>
        """, unsafe_allow_html=True)
        def_out_idx = 0
        if curr_student.get("verification_outcome") in RETENTION_OUTCOME_OPTIONS:
            def_out_idx = RETENTION_OUTCOME_OPTIONS.index(curr_student.get("verification_outcome"))
        
        f_outcome = st.radio(
            "Verification Outcome / Call Type",
            RETENTION_OUTCOME_OPTIONS,
            index=def_out_idx,
            horizontal=True,
            label_visibility="collapsed",
            key=f"ret_rad_out_{curr_student['row_num']}"
        )

        if f_outcome in ["Full Verification (Complete Survey)", "Disconnected,Did'nt Share All Info."]:
            if f_outcome == "Disconnected,Did'nt Share All Info.":
                st.markdown("""
                    <div style="background: #fffbeb; border: 1.5px solid #fde68a; border-left: 5px solid #f59e0b; padding: 10px 14px; border-radius: 8px; margin: 10px 0; color: #92400e; font-weight: 700;">
                        ⚠️ <b>Call Cut / Partial Info Shared:</b> Candidate disconnected before completing the survey. Enter whatever questions they answered below — all partial details will be updated and saved!
                    </div>
                """, unsafe_allow_html=True)
            st.markdown("<hr style='margin: 14px 0;'>", unsafe_allow_html=True)
            st.markdown("""
                <div style="font-weight: 700; color: #047857; margin-bottom: 6px;">
                    💼 Retention Status
                </div>
            """, unsafe_allow_html=True)
            def_stat_idx = 0
            if curr_student.get("retention_status") in RETENTION_STATUS_OPTIONS:
                def_stat_idx = RETENTION_STATUS_OPTIONS.index(curr_student.get("retention_status"))
            
            f_ret_status = st.selectbox(
                "Retention Status",
                RETENTION_STATUS_OPTIONS,
                index=def_stat_idx,
                label_visibility="collapsed",
                key=f"ret_sel_stat_{curr_student['row_num']}"
            )

            is_working = f_ret_status in ["Working in same job", "Working in different job"]

            if is_working:
                st.markdown("""
                    <div style="background: #f0fdf4; border: 1.5px solid #86efac; border-left: 5px solid #16a34a; padding: 10px 14px; border-radius: 8px; margin: 10px 0; color: #166534; font-weight: 700;">
                        ✅ Candidate is currently working! Please verify employment details:
                    </div>
                """, unsafe_allow_html=True)

                col_w1, col_w2, col_w3 = st.columns(3)
                with col_w1:
                    def_m_idx = 1
                    if curr_student.get("how_many_months") in RETENTION_MONTHS_OPTIONS:
                        def_m_idx = RETENTION_MONTHS_OPTIONS.index(curr_student.get("how_many_months"))
                    f_months = st.selectbox("How Many Months Working?", RETENTION_MONTHS_OPTIONS, index=def_m_idx, key=f"ret_sel_m_{curr_student['row_num']}")
                with col_w2:
                    default_comp = curr_student.get("current_company") or (curr_student.get("placed_company") if f_ret_status == "Working in same job" else "")
                    f_cur_comp = st.text_input("Current Company Name", value=default_comp, key=f"ret_txt_comp_{curr_student['row_num']}")
                with col_w3:
                    default_sal = curr_student.get("current_salary") or (curr_student.get("salary") if f_ret_status == "Working in same job" else "")
                    f_cur_sal = st.text_input("Current Salary", value=default_sal, key=f"ret_txt_sal_{curr_student['row_num']}")

                col_w4, col_w5, col_w6 = st.columns(3)
                with col_w4:
                    default_desig = curr_student.get("current_designation") or (curr_student.get("designation") if f_ret_status == "Working in same job" else "")
                    f_cur_desig = st.text_input("Current Designation", value=default_desig, key=f"ret_txt_des_{curr_student['row_num']}")
                with col_w5:
                    default_doj = curr_student.get("current_doj") or (curr_student.get("doj") if f_ret_status == "Working in same job" else "")
                    f_cur_doj = st.text_input("DOJ (Current Job)", value=default_doj, key=f"ret_txt_doj_{curr_student['row_num']}")
                with col_w6:
                    def_nps_idx = 0
                    if curr_student.get("nps") in RETENTION_NPS_OPTIONS:
                        def_nps_idx = RETENTION_NPS_OPTIONS.index(curr_student.get("nps"))
                    f_nps = st.selectbox("⭐ Net Promoter Score (NPS 0-10)", RETENTION_NPS_OPTIONS, index=def_nps_idx, key=f"ret_sel_nps_{curr_student['row_num']}")

                col_w7, col_w8 = st.columns(2)
                with col_w7:
                    f_need_job = st.radio("Need any further job?", ["No", "Yes"], index=0, horizontal=True, key=f"ret_rad_job_{curr_student['row_num']}")
                with col_w8:
                    st.date_input("Verification Date", value=date.today(), disabled=True, key=f"ret_dt_v_{curr_student['row_num']}")

                f_reason_left = "N/A - Still Working"
                f_profile_remarks = "N/A"

            elif f_ret_status == "Left The Job":
                st.markdown("""
                    <div style="background: #fffbeb; border: 1.5px solid #fde68a; border-left: 5px solid #f59e0b; padding: 10px 14px; border-radius: 8px; margin: 10px 0; color: #92400e; font-weight: 700;">
                        🚪 Candidate has Left The Job: Verify employment details, duration worked, and reason for leaving:
                    </div>
                """, unsafe_allow_html=True)

                col_lj1, col_lj2, col_lj3 = st.columns(3)
                with col_lj1:
                    def_m_left_idx = 1
                    if curr_student.get("how_many_months") in RETENTION_MONTHS_OPTIONS:
                        def_m_left_idx = RETENTION_MONTHS_OPTIONS.index(curr_student.get("how_many_months"))
                    f_months = st.selectbox(
                        "How Many Months Worked (if left)?",
                        RETENTION_MONTHS_OPTIONS,
                        index=def_m_left_idx,
                        key=f"ret_sel_lj_m_{curr_student['row_num']}"
                    )
                with col_lj2:
                    default_comp = curr_student.get("current_company") or curr_student.get("placed_company", "")
                    f_cur_comp = st.text_input("Current Company Name", value=default_comp, key=f"ret_txt_lj_comp_{curr_student['row_num']}")
                with col_lj3:
                    default_sal = curr_student.get("current_salary") or curr_student.get("salary", "")
                    f_cur_sal = st.text_input("Current Salary", value=default_sal, key=f"ret_txt_lj_sal_{curr_student['row_num']}")

                col_lj4, col_lj5, col_lj6 = st.columns(3)
                with col_lj4:
                    default_desig = curr_student.get("current_designation") or curr_student.get("designation", "")
                    f_cur_desig = st.text_input("Current Designation", value=default_desig, key=f"ret_txt_lj_des_{curr_student['row_num']}")
                with col_lj5:
                    default_doj = curr_student.get("current_doj") or curr_student.get("doj", "")
                    f_cur_doj = st.text_input("DOJ (Current Job)", value=default_doj, key=f"ret_txt_lj_doj_{curr_student['row_num']}")
                with col_lj6:
                    def_nps_idx = 0
                    if curr_student.get("nps") in RETENTION_NPS_OPTIONS:
                        def_nps_idx = RETENTION_NPS_OPTIONS.index(curr_student.get("nps"))
                    f_nps = st.selectbox(
                        "⭐ Net Promoter Score (NPS 0-10)",
                        RETENTION_NPS_OPTIONS,
                        index=def_nps_idx,
                        key=f"ret_sel_lj_nps_{curr_student['row_num']}"
                    )

                col_lj7, col_lj8 = st.columns(2)
                with col_lj7:
                    def_rs_idx = 0
                    if curr_student.get("reason_leaving") in RETENTION_REASON_LEFT_OPTIONS:
                        def_rs_idx = RETENTION_REASON_LEFT_OPTIONS.index(curr_student.get("reason_leaving"))
                    f_reason_left = st.selectbox(
                        "Reason Behind leaving the Job (if left)",
                        RETENTION_REASON_LEFT_OPTIONS,
                        index=def_rs_idx,
                        key=f"ret_sel_rs_{curr_student['row_num']}"
                    )
                with col_lj8:
                    f_need_job = st.radio(
                        "Need any further job?",
                        ["Yes", "No"],
                        index=0,
                        horizontal=True,
                        key=f"ret_rad_lj_job_{curr_student['row_num']}"
                    )

                col_lj9, col_lj10 = st.columns(2)
                with col_lj9:
                    f_profile_remarks = st.text_input(
                        "Personal/Profile issue Remarks",
                        value=curr_student.get("personal_profile_remarks", ""),
                        placeholder="E.g. Relocated to hometown, health issues, exam prep...",
                        key=f"ret_txt_lj_prof_{curr_student['row_num']}"
                    )
                with col_lj10:
                    st.date_input("Verification Date", value=date.today(), disabled=True, key=f"ret_dt_lj_{curr_student['row_num']}")

            else:  # Not working at all
                st.markdown("""
                    <div style="background: #fef2f2; border: 1.5px solid #fecaca; border-left: 5px solid #ef4444; padding: 10px 14px; border-radius: 8px; margin: 10px 0; color: #991b1b; font-weight: 700;">
                        🛑 Candidate is Not working at all: Please capture the specific reason / remarks:
                    </div>
                """, unsafe_allow_html=True)

                col_nw1, col_nw2 = st.columns(2)
                with col_nw1:
                    def_nw_idx = 0
                    if curr_student.get("personal_profile_remarks") in RETENTION_NOT_WORKING_OPTIONS:
                        def_nw_idx = RETENTION_NOT_WORKING_OPTIONS.index(curr_student.get("personal_profile_remarks"))
                    elif curr_student.get("reason_leaving") in RETENTION_NOT_WORKING_OPTIONS:
                        def_nw_idx = RETENTION_NOT_WORKING_OPTIONS.index(curr_student.get("reason_leaving"))
                    f_not_working_opt = st.selectbox(
                        "Not Working Reason / Remarks (Survey Options)",
                        RETENTION_NOT_WORKING_OPTIONS,
                        index=def_nw_idx,
                        key=f"ret_sel_nw_opt_{curr_student['row_num']}"
                    )
                with col_nw2:
                    f_extra_profile_notes = st.text_input(
                        "Personal/Profile issue Remarks (Additional Details)",
                        value=curr_student.get("personal_profile_remarks", "") if curr_student.get("personal_profile_remarks") not in RETENTION_NOT_WORKING_OPTIONS else "",
                        placeholder="E.g. Specific details about personal/profile issue...",
                        key=f"ret_txt_nw_prof_{curr_student['row_num']}"
                    )

                col_nw3, col_nw4, col_nw5 = st.columns(3)
                with col_nw3:
                    def_nps_idx = 0
                    if curr_student.get("nps") in RETENTION_NPS_OPTIONS:
                        def_nps_idx = RETENTION_NPS_OPTIONS.index(curr_student.get("nps"))
                    f_nps = st.selectbox(
                        "⭐ Net Promoter Score (NPS 0-10)",
                        RETENTION_NPS_OPTIONS,
                        index=def_nps_idx,
                        key=f"ret_sel_nw_nps_{curr_student['row_num']}"
                    )
                with col_nw4:
                    f_need_job = st.radio(
                        "Need any further job?",
                        ["Yes", "No"],
                        index=0,
                        horizontal=True,
                        key=f"ret_rad_nw_job_{curr_student['row_num']}"
                    )
                with col_nw5:
                    st.date_input("Verification Date", value=date.today(), disabled=True, key=f"ret_dt_nw_{curr_student['row_num']}")

                # Months worked is NOT appeared per user instruction
                f_months = ""
                f_cur_comp = ""
                f_cur_sal = ""
                f_cur_desig = ""
                f_cur_doj = ""
                f_reason_left = f_not_working_opt
                if f_extra_profile_notes.strip():
                    f_profile_remarks = f"{f_not_working_opt} - {f_extra_profile_notes.strip()}"
                else:
                    f_profile_remarks = f_not_working_opt

            # Additional Remarks fields
            col_rem1, col_rem2, col_rem3 = st.columns(3)
            with col_rem1:
                f_remarks = st.text_input("General Remarks", value=curr_student.get("remarks", ""), placeholder="Caller notes...", key=f"ret_txt_rem1_{curr_student['row_num']}")
            with col_rem2:
                f_remarks_2 = st.text_input("Remarks 2", value=curr_student.get("remarks_2", ""), placeholder="Secondary notes...", key=f"ret_txt_rem2_{curr_student['row_num']}")
            with col_rem3:
                f_remarks_3 = st.text_input("Remarks 3", value=curr_student.get("remarks_3", ""), placeholder="Follow-up notes...", key=f"ret_txt_rem3_{curr_student['row_num']}")

            st.markdown("<br>", unsafe_allow_html=True)
            if f_outcome == "Disconnected,Did'nt Share All Info.":
                btn_yes_label = "💾 Submit Partial Information (Call Cut)"
            elif was_previously_yes:
                btn_yes_label = "💾 Update & Save Retention Verification"
            else:
                btn_yes_label = "💾 Submit Call Disposition (Verified & Retained)"

            if st.button(btn_yes_label, type="primary", use_container_width=True, key=f"ret_btn_sub_yes_{curr_student['row_num']}"):
                gen_rem = f_remarks.strip() if f_remarks.strip() else (f_not_working_opt if f_ret_status == "Not working at all" else "")
                payload = [
                    "Yes",                      # Q: Contactable
                    f_outcome,                  # R: Verification Outcome
                    f_ret_status,               # S: Retention Status
                    f_months,                   # T: How many months
                    f_cur_comp.strip(),         # U: Current Company Name
                    f_nps,                      # V: Net Promoter Score
                    f_cur_sal.strip(),          # W: Current Salary
                    f_cur_desig.strip(),        # X: Current Designation
                    f_cur_doj.strip(),          # Y: DOJ
                    f_reason_left,              # Z: Reason Behind leaving the Job
                    f_need_job,                 # AA: Need any further job
                    str(date.today()),          # AB: Verification Date
                    gen_rem,                    # AC: Remarks
                    f_profile_remarks.strip(),  # AD: Personal/Profile issue Remarks
                    f_remarks_2.strip(),        # AE: Remarks 2
                    f_remarks_3.strip()         # AF: Remarks 3
                ]
                r_num = curr_student["row_num"]
                c_round = curr_student.get("calling_round", "Call 1")
                concat_val = f"{current_spoc}{c_round}"
                update_in_memory_retention_row(r_num, payload, call_status="Done", call_id=c_round, concat=concat_val)
                dispatch_retention_sync(retention_ws, r_num, payload, call_status="Done", call_id=c_round, concat=concat_val)
                save_retention_progress(current_spoc, cur_idx + 1, curr_student["contact_number"], active_call_index=cur_idx)

                st.session_state.retention_live_history = [item for item in st.session_state.retention_live_history if item[0] != r_num]
                st.session_state.retention_live_history.insert(0, (r_num, list(payload)))

                if f_outcome == "Disconnected,Did'nt Share All Info.":
                    st.toast(f"✅ Partial info updated for #{cur_idx + 1} ({curr_student['student_name']})!", icon="⚠️")
                elif was_previously_yes:
                    st.toast(f"✅ Updated record for #{cur_idx + 1} ({curr_student['student_name']})!", icon="🔄")
                else:
                    st.toast(f"✅ Verified Target #{cur_idx + 1} ({curr_student['student_name']}) successfully!", icon="🎉")
                if is_no_mode:
                    if current_q_idx + 1 < total_assigned_queue:
                        st.session_state.retention_no_queue_index = current_q_idx + 1
                elif is_fresh_mode:
                    if current_q_idx + 1 < total_assigned_queue:
                        st.session_state.retention_fresh_queue_index = current_q_idx + 1
                else:
                    if current_q_idx + 1 < total_assigned_queue:
                        st.session_state.retention_queue_index = current_q_idx + 1
                time.sleep(0.1)
                st.rerun()

        else:
            st.info(f"ℹ️ Selected Outcome: **{f_outcome}**")
            f_disc_remarks = st.text_area("Observations / Call Notes", value=curr_student.get("remarks_2", ""), placeholder="E.g. Disconnected after confirming name...", key=f"ret_ta_disc_{curr_student['row_num']}")
            if st.button(f"💾 Submit Disposition ({f_outcome})", type="primary", use_container_width=True, key=f"ret_btn_sub_disc_{curr_student['row_num']}"):
                payload = [
                    "Yes",                      # Q: Contactable
                    f_outcome,                  # R: Verification Outcome
                    f_outcome,                  # S: Retention Status
                    "",                         # T: How many months
                    "",                         # U: Current Company Name
                    "",                         # V: Net Promoter Score
                    "",                         # W: Current Salary
                    "",                         # X: Current Designation
                    "",                         # Y: DOJ
                    f_outcome,                  # Z: Reason Behind leaving
                    "No",                       # AA: Need any further job
                    str(date.today()),          # AB: Verification Date
                    f_outcome,                  # AC: Remarks
                    "N/A",                      # AD: Personal/Profile issue Remarks
                    f_disc_remarks.strip(),     # AE: Remarks 2
                    ""                          # AF: Remarks 3
                ]
                r_num = curr_student["row_num"]
                c_round = curr_student.get("calling_round", "Call 1")
                concat_val = f"{current_spoc}{c_round}"
                update_in_memory_retention_row(r_num, payload, call_status="Done", call_id=c_round, concat=concat_val)
                dispatch_retention_sync(retention_ws, r_num, payload, call_status="Done", call_id=c_round, concat=concat_val)
                save_retention_progress(current_spoc, cur_idx + 1, curr_student["contact_number"], active_call_index=cur_idx)

                st.session_state.retention_live_history = [item for item in st.session_state.retention_live_history if item[0] != r_num]
                st.session_state.retention_live_history.insert(0, (r_num, list(payload)))

                st.toast(f"✅ Saved Target #{cur_idx + 1} ({f_outcome})!", icon="📞")
                if is_no_mode:
                    if current_q_idx + 1 < total_assigned_queue:
                        st.session_state.retention_no_queue_index = current_q_idx + 1
                elif is_fresh_mode:
                    if current_q_idx + 1 < total_assigned_queue:
                        st.session_state.retention_fresh_queue_index = current_q_idx + 1
                else:
                    if current_q_idx + 1 < total_assigned_queue:
                        st.session_state.retention_queue_index = current_q_idx + 1
                time.sleep(0.1)
                st.rerun()

    # ==========================================================================
    # 🕒 RECENT RETENTION VERIFICATIONS & UPDATES (WITH 1-CLICK EDIT/UPDATE)
    # ==========================================================================
    st.markdown("<hr style='margin: 24px 0 16px 0;'>", unsafe_allow_html=True)
    st.markdown("""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">
            <h4 style="margin: 0; color: #047857;">🕒 Recent Verifications & Updates in this Session</h4>
            <span style="font-size: 0.85rem; color: #64748b;">Click <b>✏️ Edit</b> on any record to view, update answers, or add partial call details!</span>
        </div>
    """, unsafe_allow_html=True)

    # Collect called records from active_students
    called_records = []
    for s in active_students:
        c_stat = s.get("call_status", "").strip().lower()
        cont = s.get("contactable", "").strip()
        if c_stat == "done" or cont:
            called_records.append(s)

    latest_called = list(reversed(called_records))[:10]
    if not latest_called:
        st.info("ℹ️ No calls updated or completed yet in this session.")
    else:
        for p_idx, it in enumerate(latest_called):
            c_r1, c_r2, c_r3, c_r4 = st.columns([1.2, 3, 3, 1.2])
            with c_r1:
                st.markdown(f"**Target #{it.get('queue_index', 0) + 1}**")
            with c_r2:
                is_c_yes = it.get("contactable", "").strip().lower() == "yes"
                badge = "🟢 Contactable (Yes)" if is_c_yes else "🔴 Not Contactable (No)"
                st.markdown(f"**{it['student_name']}** (`{it['contact_number']}`)<br><small>{badge}</small>", unsafe_allow_html=True)
            with c_r3:
                comp_txt = it.get('current_company') or it.get('placed_company', '')
                status_txt = it.get('retention_status') or it.get('verification_outcome') or it.get('remarks') or 'Verified'
                st.markdown(f"*{comp_txt}*<br><small style='color: #64748b;'>{status_txt}</small>", unsafe_allow_html=True)
            with c_r4:
                if st.button("✏️ Edit", key=f"ret_btn_edit_{p_idx}_{it['row_num']}", use_container_width=True):
                    target_idx = None
                    for a_i, a_s in enumerate(active_students):
                        if a_s["row_num"] == it["row_num"]:
                            target_idx = a_i
                            break
                    if target_idx is not None:
                        st.session_state.retention_queue_index = target_idx
                    else:
                        st.session_state.retention_queue_index = it.get("queue_index", 0)

                    row_k = it["row_num"]
                    for k in list(st.session_state.keys()):
                        if f"_{row_k}" in k and k.startswith("ret_"):
                            st.session_state.pop(k, None)

                    st.toast(f"Loaded Target #{it.get('queue_index', 0) + 1} ({it['student_name']}) for editing!", icon="✏️")
                    st.rerun()

    # Sidebar: Live Progress & Export
    with st.sidebar:
        st.markdown("### 📊 Retention Call Progress")
        pct_done = ((stats['total_called']) / max(1, stats['total_assigned']))
        st.progress(pct_done)
        st.markdown(f"**{stats['total_called']} / {stats['total_assigned']}** calls completed ({pct_done*100:.1f}%)")

        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown("### 📥 Download Retention Data")
        if st.button("🔄 Refresh Data From Sheet", use_container_width=True, key="ret_btn_ref"):
            fetch_retention_master_data.clear()
            st.session_state.retention_master_rows = fetch_retention_master_data(retention_ws)
            st.rerun()

        if os.path.exists(LOCAL_RETENTION_CSV):
            with open(LOCAL_RETENTION_CSV, "rb") as f:
                csv_bytes = f.read()
            st.download_button(
                "⬇️ Download Retention CSV",
                data=csv_bytes,
                file_name=f"Retention_Verification_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True,
                key="ret_dl_csv"
            )
