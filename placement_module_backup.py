import streamlit as st
from datetime import date, datetime
import json
import os
import re
import time

PROGRESS_PLACEMENT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spoc_placement_progress.json")
DATA_CACHE_TTL = 900  # 15 minutes TTL for zero API rate limit and lightning speed

# ==============================================================================
# 🎯 DROPDOWN CONSTANTS (MATCHING PLACEMENT EXCEL & USER SPECIFICATION)
# ==============================================================================
PLACEMENT_RETENTION_OPTIONS = [
    "Working in same job",
    "Working in different job",
    "Unable_to_track",
    "Not_working_at_all",
    "Confirmed Name But Didn't Share Any Information.",
    "Left_The_Job",
    "Will joined after some days"
]

PLACEMENT_MONTHS_OPTIONS = [
    "1 Month", "2 Months", "3 Months", "4 Months", "5 Months", "6 Months",
    "7 Months", "8 Months", "9 Months", "10 Months", "11 Months", "12 Months",
    "Less than 1 Months", "More than 12 months"
]

PLACEMENT_UNABLE_TO_TRACK_OPTIONS = [
    "Did not respond to our call",
    "Network issue",
    "Not a student of Anudip",
    "Language issue",
    "Switched off",
    "Incoming Call Is Not Avialable",
    "Wrong Number",
    "Call Disconnected / Busy",
    "Others"
]

PLACEMENT_NOT_WORKING_OPTIONS = [
    "Did_not_joined_job_due_to_personal_issue",
    "Did_not_joined_job_due_to_profile_issue",
    "Did not get any information from the employer",
    "Did not get selected",
    "Did Not Attend Any Interview"
]

PLACEMENT_NOT_JOINED_PERSONAL_OPTIONS = [
    "Distance Issue",
    "As The Student Is Pursuing 1st Year",
    "As The Student Is Pursuing 2nd Year",
    "As The Student Is Pursuing 3rd Year",
    "Medical Issue"
]

PLACEMENT_NOT_JOINED_PROFILE_OPTIONS = [
    "Issue Regarding Job Role",
    "Issue Regarding Salary"
]

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
    "Company Closed",
    "Others…"
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
    if not spoc_name or not student_list:
        return 0, 0
    data = load_all_placement_progress()
    saved = data.get(spoc_name.strip().lower())
    if not saved:
        return 0, 0
    saved_active = saved.get("active_call_index", saved.get("queue_index", 0))
    if not isinstance(saved_active, int) or saved_active < 0 or saved_active >= len(student_list):
        saved_active = 0

    saved_phone = clean_phone(saved.get("phone", ""))
    if saved_phone:
        for idx, item in enumerate(student_list):
            if clean_phone(item.get("contact_number", "")) == saved_phone:
                return idx, max(idx, saved_active)

    saved_idx = saved.get("queue_index", 0)
    if isinstance(saved_idx, int) and 0 <= saved_idx < len(student_list):
        return saved_idx, max(saved_idx, saved_active)
    return 0, saved_active

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

def get_placement_students_for_spoc(all_rows, spoc_name):
    """
    Parses and returns structured student records for the specified SPOC.
    If spoc_name is in ADMIN_USERS, returns all records with ability to filter.
    """
    if len(all_rows) <= 1:
        return []

    spoc_clean = (spoc_name or "").strip().lower()
    ADMIN_USERS = {"nibedan", "pritam", "kalpana", "koushik"}
    is_admin = spoc_clean in ADMIN_USERS

    students = []
    q_idx = 0
    for r_idx, r in enumerate(all_rows[1:], start=2): # 1-based row index in Google Sheet
        if len(r) > 0 and str(r[0]).strip():
            assigned_spoc = str(r[0]).strip()
            if is_admin or assigned_spoc.lower() == spoc_clean:
                # Pad row to at least 34 columns
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
                    # Yellow verified columns (Q to AF)
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
            live_map[r_num] = row_data[0].strip().lower() # contactable is at idx 0 of payload

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
        st.caption(f"📋 Respective SPOC uncalled phone numbers ({v_pending} remaining). Copy or download below:")
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
# 🖥️ MAIN PLACEMENT DASHBOARD RENDERER
# ==============================================================================
def render_placement_dashboard(placement_ws, current_spoc, is_admin=False):
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

    # 1. Fetch all placement rows (cached)
    all_rows = fetch_placement_master_data(placement_ws)
    if not all_rows:
        st.error("⚠️ Could not load data from Google Sheet 'Placement_Verification'. Please check permissions or connection.")
        return

    # 2. Get students allocated to current SPOC
    students = get_placement_students_for_spoc(all_rows, current_spoc)
    if not students:
        st.warning(f"No students allocated for SPOC '{current_spoc}' in Placement_Verification sheet.")
        return

    # 3. Live session buffer initialization
    if "placement_live_history" not in st.session_state:
        st.session_state.placement_live_history = []

    # 4. Compute real-time stats
    stats = compute_placement_stats(students, st.session_state.placement_live_history)

    # 5. Queue Index initialization & restore
    if "placement_queue_index" not in st.session_state:
        saved_q, saved_act = get_saved_placement_index(current_spoc, students)
        st.session_state.placement_queue_index = saved_q
        st.session_state.placement_active_call_index = saved_act

    current_q_idx = st.session_state.placement_queue_index
    if current_q_idx >= len(students):
        current_q_idx = max(0, len(students) - 1)
        st.session_state.placement_queue_index = current_q_idx

    current_student = students[current_q_idx]

    # --------------------------------------------------------------------------
    # 📊 TOP METRIC CARDS & POPUP ACTIONS
    # --------------------------------------------------------------------------
    col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
    with col_m1:
        st.metric("🎯 Total Assigned", stats["total_assigned"])
    with col_m2:
        st.metric("⏳ Fresh Pending", stats["fresh_pending"], delta=f"-{stats['total_called']} called", delta_color="inverse")
    with col_m3:
        st.metric("📞 Contactable %", f"{stats['contactable_pct']:.1f}%")
    with col_m4:
        st.metric("✅ Contacted (Yes)", stats["yes_count"])
    with col_m5:
        st.metric("❌ Not Contactable (No)", stats["no_count"])

    # Fresh Call & Not Contactable Header Popover Buttons
    c_btn1, c_btn2, c_btn3 = st.columns([2, 2, 3])
    with c_btn1:
        st.markdown('<div class="fresh-call-header-btn">', unsafe_allow_html=True)
        with st.popover(f"🟢 Fresh Calls ({stats['fresh_pending']} Pending) ⌄", use_container_width=True):
            render_placement_fresh_call_list(stats, current_spoc)
        st.markdown('</div>', unsafe_allow_html=True)

    with c_btn2:
        st.markdown('<div class="nocontact-header-btn">', unsafe_allow_html=True)
        with st.popover(f"📞 Not Contactable ({stats['no_count']}) ⌄", use_container_width=True):
            render_placement_not_contactable_list(stats, current_spoc)
        st.markdown('</div>', unsafe_allow_html=True)

    with c_btn3:
        # Quick Search / Direct Jump
        with st.expander("🔍 Search Student / Direct Jump", expanded=False):
            search_inp = st.text_input("Enter 10-digit Phone or Student Name", key="plc_quick_search", placeholder="Type phone / name...")
            if search_inp.strip():
                clean_s = clean_phone(search_inp.strip())
                name_s = search_inp.strip().lower()
                found_match = None
                for s in students:
                    if (clean_s and clean_s in clean_phone(s["contact_number"])) or (name_s in s["student_name"].lower()):
                        found_match = s
                        break
                if found_match:
                    st.success(f"Found: **{found_match['student_name']}** ({found_match['contact_number']}) — Target #{found_match['queue_index']+1}")
                    if st.button("Load Student Now", key="btn_load_search", type="primary"):
                        st.session_state.placement_queue_index = found_match["queue_index"]
                        save_placement_progress(current_spoc, found_match["queue_index"], found_match["contact_number"], active_call_index=st.session_state.get("placement_active_call_index", 0))
                        st.rerun()
                else:
                    st.info("No matching student in your allocated list.")

    st.markdown("---")

    # --------------------------------------------------------------------------
    # 📌 QUEUE CONTROLS & NAVIGATION BAR
    # --------------------------------------------------------------------------
    prog_pct = min((current_q_idx + 1) / stats["total_assigned"], 1.0) if stats["total_assigned"] > 0 else 0
    st.progress(prog_pct)

    col_nav1, col_nav2, col_nav3, col_nav4 = st.columns([1.2, 1.2, 3, 1.2])
    with col_nav1:
        if st.button("◀️ Previous", disabled=(current_q_idx == 0), use_container_width=True):
            st.session_state.placement_queue_index = max(0, current_q_idx - 1)
            prev_s = students[st.session_state.placement_queue_index]
            save_placement_progress(current_spoc, st.session_state.placement_queue_index, prev_s["contact_number"], active_call_index=st.session_state.get("placement_active_call_index", 0))
            st.rerun()

    with col_nav2:
        if st.button("Next ▶️", disabled=(current_q_idx >= stats["total_assigned"] - 1), use_container_width=True):
            st.session_state.placement_queue_index = min(stats["total_assigned"] - 1, current_q_idx + 1)
            next_s = students[st.session_state.placement_queue_index]
            save_placement_progress(current_spoc, st.session_state.placement_queue_index, next_s["contact_number"], active_call_index=st.session_state.get("placement_active_call_index", 0))
            st.rerun()

    with col_nav3:
        st.markdown(f"""
            <div class="queue-box" style="margin-bottom: 0; text-align: center; padding: 0.55rem 1rem;">
                🎯 Calling Target <b>#{current_q_idx + 1}</b> of <b>{stats['total_assigned']}</b> &nbsp;·&nbsp;
                <span>{current_student['student_name']}</span> &nbsp;·&nbsp;
                <a href="tel:{current_student['contact_number']}" style="color: #1a73e8; text-decoration: underline; font-weight: 800;">📞 {current_student['contact_number']}</a>
            </div>
        """, unsafe_allow_html=True)

    with col_nav4:
        if st.button("⏭️ Skip", use_container_width=True):
            st.session_state.placement_queue_index = min(stats["total_assigned"] - 1, current_q_idx + 1)
            next_s = students[st.session_state.placement_queue_index]
            save_placement_progress(current_spoc, st.session_state.placement_queue_index, next_s["contact_number"], active_call_index=st.session_state.get("placement_active_call_index", 0))
            st.toast("Skipped to next target", icon="⏭️")
            st.rerun()

    # --------------------------------------------------------------------------
    # 🪪 STUDENT INFORMATION CARD (COLUMNS A to P)
    # --------------------------------------------------------------------------
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="form-title">👤 Student Placement Profile Details</div>', unsafe_allow_html=True)

    p_col1, p_col2, p_col3, p_col4 = st.columns(4)
    with p_col1:
        st.markdown(f"<div class='profile-label'>Student Name</div><div class='profile-val'>{current_student['student_name']}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label' style='margin-top:8px;'>CMIS ID</div><div class='profile-val'>{current_student['cmis_id'] or 'N/A'}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label' style='margin-top:8px;'>Gender</div><div class='profile-val'>{current_student['gender'] or 'N/A'}</div>", unsafe_allow_html=True)

    with p_col2:
        st.markdown(f"<div class='profile-label'>Contact Number</div><div class='profile-val'><a href='tel:{current_student['contact_number']}' style='color:#1a73e8; font-weight:800; font-size:1.15rem;'>📞 {current_student['contact_number']}</a></div>", unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label' style='margin-top:8px;'>Alt. Contact</div><div class='profile-val'>{current_student['alt_contact_number'] if current_student['alt_contact_number'] != '0' else 'None'}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label' style='margin-top:8px;'>Donor Name</div><div class='profile-val'>{current_student['donor_name'] or 'N/A'}</div>", unsafe_allow_html=True)

    with p_col3:
        st.markdown(f"<div class='profile-label'>Centre Name</div><div class='profile-val'>{current_student['centre_name']} ({current_student['centre_code']})</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label' style='margin-top:8px;'>Course / State</div><div class='profile-val'>{current_student['course']} &nbsp;·&nbsp; {current_student['state']}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label' style='margin-top:8px;'>Date of Joining (DOJ)</div><div class='profile-val'>{current_student['doj'] or 'N/A'}</div>", unsafe_allow_html=True)

    with p_col4:
        st.markdown(f"<div class='profile-label'>Placed Company</div><div class='profile-val' style='color:#0f4c81;'>🏢 {current_student['company_name']}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label' style='margin-top:8px;'>Designation</div><div class='profile-val'>{current_student['designation']}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='profile-label' style='margin-top:8px;'>Salary / Location</div><div class='profile-val'>💰 ₹{current_student['salary']} &nbsp;·&nbsp; {current_student['job_location']}</div>", unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # 📝 PLACEMENT VERIFICATION FORM (COLUMNS Q to AF - YELLOW AREA)
    # --------------------------------------------------------------------------
    is_already_verified = bool(current_student["contactable"])
    status_badge_html = """
        <span style="background: #fef3c7; color: #92400e; border: 1px solid #fcd34d; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.85rem; margin-left: 10px;">
            ✏️ RECORD PREVIOUSLY VERIFIED — UPDATE MODE (Row #{row})
        </span>
    """.replace("{row}", str(current_student["row_num"])) if is_already_verified else """
        <span style="background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.85rem; margin-left: 10px;">
            🆕 FRESH CALL VERIFICATION (Target #{t})
        </span>
    """.replace("{t}", str(current_q_idx + 1))

    st.markdown('<div class="section-card" style="border-top: 4px solid #f59e0b;">', unsafe_allow_html=True)
    st.markdown(f"""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
            <div class="form-title" style="margin-bottom: 0;">
                📋 Call Verification Questionnaire
            </div>
            <div>{status_badge_html}</div>
        </div>
    """, unsafe_allow_html=True)

    # Question 1: Contactable (Yes / No)
    def_cont_idx = 0 if current_student["contactable"].strip().lower() != "no" else 1
    f_contactable = st.radio(
        "1. Is the student Contactable? (Call Status)",
        ["Yes", "No"],
        index=def_cont_idx,
        horizontal=True,
        key=f"plc_rad_cont_{current_student['row_num']}"
    )

    if f_contactable == "No":
        # NOT CONTACTABLE WORKFLOW
        st.markdown("""
            <div style="background: #fff7ed; border: 1px solid #fed7aa; border-left: 4px solid #ea580c; padding: 12px; border-radius: 6px; margin: 10px 0;">
                <b style="color: #9a3412;">📞 Student Not Contactable:</b> Please select the call disposition / reason below.
            </div>
        """, unsafe_allow_html=True)

        existing_rem = current_student["left_not_working_remarks"].strip()
        def_nocont_idx = 0
        if existing_rem in PLACEMENT_UNABLE_TO_TRACK_OPTIONS:
            def_nocont_idx = PLACEMENT_UNABLE_TO_TRACK_OPTIONS.index(existing_rem)

        f_nocont_reason = st.selectbox(
            "Call Remarks / Not Contactable Reason",
            PLACEMENT_UNABLE_TO_TRACK_OPTIONS,
            index=def_nocont_idx,
            key=f"plc_sel_nocont_{current_student['row_num']}"
        )

        f_remarks_2_no = st.text_area(
            "Additional Calling Remarks (Optional)",
            value=current_student["remarks_2"],
            height=70,
            key=f"plc_ta_rem2_no_{current_student['row_num']}",
            placeholder="E.g. Called twice, ringing no response..."
        )

        f_vdate_no = st.date_input(
            "Verification Date",
            value=parse_date_safe(current_student["verification_date"]) or date.today(),
            key=f"plc_date_no_{current_student['row_num']}"
        )

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("💾 Submit Call Disposition (Not Contactable)", type="primary", use_container_width=True, key=f"plc_sub_no_{current_student['row_num']}"):
            with st.spinner("⚡ High Speed Sync to Google Sheets..."):
                # Payload: Q to AG (17 columns)
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

                    # 0ms live history update
                    st.session_state.placement_live_history.insert(0, (current_student['row_num'], list(payload)))
                    st.session_state.placement_live_history = st.session_state.placement_live_history[:15]

                    st.toast(f"Saved Target #{current_q_idx + 1} ({current_student['student_name']}) as Not Contactable!", icon="✅")

                    # Advance queue
                    if current_q_idx + 1 < len(students):
                        st.session_state.placement_queue_index = current_q_idx + 1
                        next_s = students[current_q_idx + 1]
                        save_placement_progress(current_spoc, current_q_idx + 1, next_s["contact_number"], active_call_index=st.session_state.get("placement_active_call_index", 0))

                    time.sleep(0.3)
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error saving to Google Sheets: {ex}")

    else:
        # CONTACTABLE == YES WORKFLOW
        st.markdown("<br>", unsafe_allow_html=True)
        col_q1, col_q2, col_q3 = st.columns(3)
        with col_q1:
            def_ass_idx = 0 if current_student["assessment_given"].upper() != "NO" else 1
            f_assessment = st.radio(
                "2. Assessment Given?",
                ["YES", "NO"],
                index=def_ass_idx,
                horizontal=True,
                key=f"plc_rad_ass_{current_student['row_num']}"
            )

        with col_q2:
            def_cert_idx = 0 if current_student["got_certificate"].upper() != "NO" else 1
            f_certificate = st.radio(
                "3. Got Certificate?",
                ["YES", "NO"],
                index=def_cert_idx,
                horizontal=True,
                key=f"plc_rad_cert_{current_student['row_num']}"
            )

        with col_q3:
            def_got_job_idx = 0 if current_student["got_job_from_anudip"].upper() != "NO" else 1
            f_got_job = st.radio(
                "4. Got This Job From Anudip?",
                ["YES", "NO"],
                index=def_got_job_idx,
                horizontal=True,
                key=f"plc_rad_job_{current_student['row_num']}"
            )

        st.markdown("---")
        st.markdown("<div style='font-weight:700; color:#0f4c81; font-size:1.05rem; margin-bottom:10px;'>💼 Retention & Employment Status</div>", unsafe_allow_html=True)

        existing_ret = current_student["retention_status"].strip()
        def_ret_idx = 0
        if existing_ret in PLACEMENT_RETENTION_OPTIONS:
            def_ret_idx = PLACEMENT_RETENTION_OPTIONS.index(existing_ret)

        f_retention = st.selectbox(
            "5. Retention Status",
            PLACEMENT_RETENTION_OPTIONS,
            index=def_ret_idx,
            key=f"plc_sel_ret_{current_student['row_num']}"
        )

        # Dynamic employment fields if working
        is_working = f_retention in ["Working in same job", "Working in different job"]

        c_emp1, c_emp2, c_emp3 = st.columns(3)
        with c_emp1:
            def_months_idx = 2  # default 3 Months
            if current_student["how_many_months"] in PLACEMENT_MONTHS_OPTIONS:
                def_months_idx = PLACEMENT_MONTHS_OPTIONS.index(current_student["how_many_months"])
            f_months = st.selectbox(
                "6. How Many Months Working?",
                PLACEMENT_MONTHS_OPTIONS,
                index=def_months_idx,
                disabled=not is_working,
                key=f"plc_sel_months_{current_student['row_num']}"
            )

        with c_emp2:
            # Default company name: placed company if working in same job
            def_comp = current_student["current_company"] or (current_student["company_name"] if f_retention == "Working in same job" else "")
            f_company = st.text_input(
                "7. Current Company Name",
                value=def_comp,
                disabled=not is_working,
                key=f"plc_txt_comp_{current_student['row_num']}"
            )

        with c_emp3:
            # Default salary: placed salary if working in same job
            def_sal = current_student["current_salary"] or (current_student["salary"] if f_retention == "Working in same job" else "")
            f_salary = st.text_input(
                "8. Current Salary (Per Month)",
                value=str(def_sal),
                disabled=not is_working,
                key=f"plc_txt_sal_{current_student['row_num']}"
            )

        c_emp4, c_emp5, c_emp6 = st.columns(3)
        with c_emp4:
            def_desig = current_student["current_designation"] or (current_student["designation"] if f_retention == "Working in same job" else "")
            f_designation = st.text_input(
                "9. Current Designation",
                value=def_desig,
                disabled=not is_working,
                key=f"plc_txt_desig_{current_student['row_num']}"
            )

        with c_emp5:
            def_doj = parse_date_safe(current_student["current_doj"]) or parse_date_safe(current_student["doj"]) or date.today()
            f_doj = st.date_input(
                "10. DOJ (Current Job)",
                value=def_doj,
                disabled=not is_working,
                key=f"plc_date_doj_{current_student['row_num']}"
            )

        with c_emp6:
            def_further_idx = 1 if current_student["need_further_job"].upper() != "YES" else 0
            f_further_job = st.radio(
                "11. Need Any Further Job?",
                ["YES", "NO"],
                index=def_further_idx,
                horizontal=True,
                key=f"plc_rad_further_{current_student['row_num']}"
            )

        st.markdown("---")
        st.markdown("<div style='font-weight:700; color:#0f4c81; font-size:1.05rem; margin-bottom:10px;'>🔍 Reason & Feedback Categorization</div>", unsafe_allow_html=True)

        # Dynamic Dependent Remarks based on Retention Status (Column 30 / AD)
        if f_retention == "Unable_to_track":
            target_options = PLACEMENT_UNABLE_TO_TRACK_OPTIONS
            lbl_rem = "12. Unable To Track Reason"
        elif f_retention == "Not_working_at_all":
            target_options = PLACEMENT_NOT_WORKING_OPTIONS
            lbl_rem = "12. Not Working Reason"
        elif f_retention == "Left_The_Job":
            target_options = PLACEMENT_LEFT_JOB_OPTIONS
            lbl_rem = "12. Left The Job Reason"
        elif f_retention in ["Working in same job", "Working in different job"]:
            target_options = ["N/A - Currently Working", "Working Satisfactorily", "Looking for Better Opportunity"]
            lbl_rem = "12. Current Work Remarks"
        elif f_retention == "Confirmed Name But Didn't Share Any Information.":
            target_options = ["Confirmed Name But Withheld Information", "Student Busy / Call Later"]
            lbl_rem = "12. Non-Disclosure Remarks"
        else: # Will joined after some days
            target_options = ["Will join upcoming date", "Offer letter received, awaiting onboarding", "Medical / Personal delay"]
            lbl_rem = "12. Joining Status Remarks"

        existing_left_rem = current_student["left_not_working_remarks"].strip()
        def_left_idx = 0
        if existing_left_rem in target_options:
            def_left_idx = target_options.index(existing_left_rem)

        c_rem1, c_rem2 = st.columns(2)
        with c_rem1:
            f_left_remarks = st.selectbox(
                lbl_rem,
                target_options,
                index=def_left_idx,
                key=f"plc_sel_left_rem_{current_student['row_num']}"
            )

        with c_rem2:
            # Dynamic Not Joined Remarks (Column 31 / AE) based on Column 30
            if f_left_remarks == "Did_not_joined_job_due_to_personal_issue":
                nj_options = PLACEMENT_NOT_JOINED_PERSONAL_OPTIONS
                lbl_nj = "13. Not Joined Details (Personal Issue)"
            elif f_left_remarks == "Did_not_joined_job_due_to_profile_issue":
                nj_options = PLACEMENT_NOT_JOINED_PROFILE_OPTIONS
                lbl_nj = "13. Not Joined Details (Profile Issue)"
            else:
                nj_options = ["N/A"]
                lbl_nj = "13. Not Joined Details"

            existing_nj = current_student["not_joined_remarks"].strip()
            def_nj_idx = 0
            if existing_nj in nj_options:
                def_nj_idx = nj_options.index(existing_nj)

            f_not_joined_remarks = st.selectbox(
                lbl_nj,
                nj_options,
                index=def_nj_idx,
                key=f"plc_sel_nj_rem_{current_student['row_num']}"
            )

        c_fb1, c_fb2, c_fb3 = st.columns(3)
        with c_fb1:
            def_nps_idx = 0
            existing_nps = str(current_student["nps"]).strip()
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
            existing_sat = current_student["satisfied_with_conversation"].strip()
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
                value=parse_date_safe(current_student["verification_date"]) or date.today(),
                key=f"plc_date_vdate_{current_student['row_num']}"
            )

        f_remarks_2 = st.text_area(
            "17. Remarks 2 (Additional SPOC Notes)",
            value=current_student["remarks_2"],
            height=70,
            key=f"plc_ta_rem2_{current_student['row_num']}",
            placeholder="Type any specific comments or call observation..."
        )

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("💾 Submit Placement Verification", type="primary", use_container_width=True, key=f"plc_btn_submit_{current_student['row_num']}"):
            with st.spinner("⚡ High Speed Sync to Google Sheets..."):
                # Payload: Columns Q to AG (17 columns)
                payload = [
                    "Yes",                                    # Q: Contactable
                    f_assessment,                             # R: Assessment Given
                    f_certificate,                            # S: Got Certificate
                    f_got_job,                                # T: Have_You_Got_This_Job_From_Anudip
                    f_retention,                              # U: Retention Status
                    f_months if is_working else "",           # V: How Many Months Working
                    f_company if is_working else "",          # W: Current Company Name
                    str(f_salary) if is_working else "",      # X: Current Salary
                    f_designation if is_working else "",      # Y: Current Designation
                    str(f_doj) if is_working else "",         # Z: DOJ
                    f_further_job,                            # AA: Need any further job
                    str(f_nps),                               # AB: Net Promoter Score
                    str(f_vdate),                             # AC: Verification Date
                    f_left_remarks,                           # AD: Left The Job /Not Working/Not - Contactable Remarks
                    f_not_joined_remarks,                     # AE: Not Joined Remarks
                    f_satisfied,                              # AF: Satisfied With Conversation
                    f_remarks_2.strip()                       # AG: Remarks 2
                ]

                try:
                    placement_ws.update(values=[payload], range_name=f"Q{current_student['row_num']}:AG{current_student['row_num']}")
                    fetch_placement_master_data.clear()

                    # 0ms live history update
                    st.session_state.placement_live_history.insert(0, (current_student['row_num'], list(payload)))
                    st.session_state.placement_live_history = st.session_state.placement_live_history[:15]

                    st.toast(f"✅ Target #{current_q_idx + 1} ({current_student['student_name']}) saved successfully to Google Sheets!", icon="🎯")

                    # Advance queue
                    if current_q_idx + 1 < len(students):
                        st.session_state.placement_queue_index = current_q_idx + 1
                        next_s = students[current_q_idx + 1]
                        save_placement_progress(current_spoc, current_q_idx + 1, next_s["contact_number"], active_call_index=st.session_state.get("placement_active_call_index", 0))

                    time.sleep(0.3)
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error saving to Google Sheets: {ex}")

    st.markdown('</div>', unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # 📋 SECTION: SPOC WISE LATEST VERIFIED CALLS (Z-A)
    # --------------------------------------------------------------------------
    st.markdown("""
        <div class="section-card" style="margin-top: 1.2rem; border-top: 4px solid #1a73e8;">
            <div class="form-title" style="margin-bottom: 0.6rem;">
                📋 Recent Verified Calls ({spoc_name})
            </div>
    """.replace("{spoc_name}", current_spoc.title()), unsafe_allow_html=True)

    # Collect all called students for this SPOC
    called_records = []
    live_map = {r_num: r_data for r_num, r_data in st.session_state.placement_live_history}

    for s in students:
        r_num = s["row_num"]
        if r_num in live_map:
            l_data = live_map[r_num]
            called_records.append({
                "target_num": s["queue_index"] + 1,
                "row_num": r_num,
                "student_name": s["student_name"],
                "contact_number": s["contact_number"],
                "company_name": s["company_name"],
                "contactable": l_data[0],
                "retention": l_data[4] if len(l_data) > 4 else "",
                "remarks": l_data[13] if len(l_data) > 13 else ""
            })
        elif s["contactable"]:
            called_records.append({
                "target_num": s["queue_index"] + 1,
                "row_num": r_num,
                "student_name": s["student_name"],
                "contact_number": s["contact_number"],
                "company_name": s["company_name"],
                "contactable": s["contactable"],
                "retention": s["retention_status"],
                "remarks": s["left_not_working_remarks"]
            })

    # Show latest 5 in reverse order (Z to A)
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
                if st.button("✏️ Edit", key=f"plc_edit_{it['row_num']}", use_container_width=True):
                    st.session_state.placement_queue_index = it["target_num"] - 1
                    save_placement_progress(current_spoc, it["target_num"] - 1, it["contact_number"], active_call_index=st.session_state.get("placement_active_call_index", 0))
                    st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)
