import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date, datetime
import hashlib
import os

# ============================================
# ⚙️ PAGE CONFIG
# ============================================
st.set_page_config(page_title="Student Verification Entry Form", page_icon="✅", layout="wide")

# ============================================
# 🔐 PASSWORD UTILITIES (UNCHANGED)
# ============================================
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def verify_password(password, hashed):
    return hash_password(password) == hashed

# ============================================
# 🔐 GOOGLE AUTH
# ============================================
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

if "gcp_service_account" in st.secrets:
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=scope
    )
elif os.path.exists("service_account.json"):
    credentials = Credentials.from_service_account_file(
        "service_account.json", scopes=scope
    )
else:
    st.error("No credentials found")
    st.stop()

client = gspread.authorize(credentials)

# ============================================
# 📄 SHEETS
# ============================================
sheet = client.open("Test").sheet1
login_sheet = client.open("Test_Spoc_PassWord").sheet1

# 🔥 NEW SHEET (Test2)
test2_sheet = client.open("Test2").sheet1

# ============================================
# SESSION
# ============================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "spoc_name" not in st.session_state:
    st.session_state.spoc_name = ""

# ============================================
# MAIN FORM
# ============================================
def show_main_form():
    st.title("📋 Student Verification Entry Form")
    st.markdown("---")

    # 🔥 Fetch Test2 Data
    test2_data = test2_sheet.get_all_records()

    with st.form("entry_form"):
        col1, col2, col3 = st.columns(3)

        with col1:
            st.text_input("SPOC Name", st.session_state.spoc_name, disabled=True)
            student_touch = st.selectbox("Students Touch Method", ["Call", "WhatsApp", "SMS", "Email", "Other"])
            student_name = st.text_input("Student Name")

            contact_number = st.text_input("Contact Number")

            # 🔥 MATCH LOGIC
            matched_row = next(
                (r for r in test2_data if str(r.get("Contact Number", "")) == contact_number),
                None
            )

            # 🔥 AUTO FILL (Editable)
            if matched_row:
                cmisid_default = matched_row.get("CMIS ID", "")
                company_default = matched_row.get("Company Name", "")
                salary_default = matched_row.get("Salary", "")
                designation_default = matched_row.get("Deg", "")
                doj_default = matched_row.get("DOJ", "")
            else:
                cmisid_default = ""
                company_default = ""
                salary_default = ""
                designation_default = ""
                doj_default = ""

            cmisid = st.text_input("CMIS ID", value=cmisid_default)
            contactable = st.selectbox("Contactable", ["Yes", "No"])

        with col2:
            retention_status = st.selectbox("Retention Status", ["Working", "Not Working", "Unknown"])
            months_working = st.number_input("Months Working", min_value=0)

            current_company = st.text_input("Company", value=company_default)
            current_salary = st.text_input("Salary", value=salary_default)
            current_designation = st.text_input("Designation", value=designation_default)

            # DOJ convert safe
            try:
                doj_default_date = datetime.strptime(str(doj_default), "%Y-%m-%d").date()
            except:
                doj_default_date = date.today()

            doj = st.date_input("DOJ", value=doj_default_date)

        with col3:
            reason_leaving = st.text_area("Reason")
            need_job = st.selectbox("Need Job", ["Yes", "No"])
            nps = st.slider("NPS", 0, 10, 5)
            verification_date = st.date_input("Verification Date", value=date.today())
            remarks = st.text_area("Remarks")

        submitted = st.form_submit_button("Submit Data ✅")

    if submitted:
        data = [
            st.session_state.spoc_name, student_touch, student_name, cmisid,
            contact_number, contactable, retention_status, months_working,
            current_company, current_salary, current_designation, str(doj),
            reason_leaving, need_job, nps, str(verification_date), remarks
        ]
        sheet.append_row(data)
        st.success("✅ Data submitted!")

# ============================================
# SIMPLE LOGIN FLOW (UNCHANGED)
# ============================================
if not st.session_state.logged_in:
    if st.button("Login"):
        st.session_state.logged_in = True
        st.session_state.spoc_name = "DemoUser"
        st.rerun()
else:
    show_main_form()