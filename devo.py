import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date, datetime
import hashlib
import os

# =========================================================
# ⚙️ CONFIG
# =========================================================
st.set_page_config(page_title="Student Verification", layout="wide")

# =========================================================
# 🎨 UI STYLE
# =========================================================
st.markdown("""
<style>
.main {
    background: linear-gradient(135deg, #00aaff, #00ffaa);
}
.section-card {
    background: white;
    padding: 15px;
    border-radius: 12px;
    margin-bottom: 10px;
}
.stButton>button {
    background-color:#007bff;
    color:white;
}
</style>
""", unsafe_allow_html=True)

# =========================================================
# 🔐 PASSWORD
# =========================================================
def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def verify_password(p, h):
    return hash_password(p) == h

# =========================================================
# 🔌 GOOGLE SHEET
# =========================================================
scope = ["https://www.googleapis.com/auth/spreadsheets"]

if "gcp_service_account" in st.secrets:
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=scope)
else:
    credentials = Credentials.from_service_account_file(
        "service_account.json", scopes=scope)

client = gspread.authorize(credentials)

sheet = client.open("Test").sheet1
login_sheet = client.open("Test_Spoc_PassWord").sheet1
test2_sheet = client.open("Test2").sheet1

# =========================================================
# 🧠 SESSION
# =========================================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    st.session_state.user = ""

# =========================================================
# 🔐 LOGIN
# =========================================================
def login():
    st.subheader("Login")

    user = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        records = login_sheet.get_all_records()

        for r in records:
            if r["spoc_name"] == user and verify_password(password, r["password"]):
                st.session_state.logged_in = True
                st.session_state.user = user
                st.rerun()

        st.error("Invalid Credentials")

# =========================================================
# 🆕 REGISTER
# =========================================================
def register():
    st.subheader("Register")

    user = st.text_input("New Username")
    password = st.text_input("New Password", type="password")

    if st.button("Register"):
        records = login_sheet.get_all_records()
        users = [r["spoc_name"] for r in records]

        if user in users:
            st.error("User already exists")
        else:
            login_sheet.append_row([user, hash_password(password)])
            st.success("Registered Successfully")

# =========================================================
# 🔎 FETCH TEST2
# =========================================================
def fetch_test2(contact):
    records = test2_sheet.get_all_records()

    for r in records:
        if str(r["Contact Number"]) == str(contact):
            return r
    return None

# =========================================================
# 🧠 PIC LOGIC
# =========================================================
def pic_options(contactable, retention):
    if contactable == "Yes" and retention == "Yes":
        return [
            "Working Same Job",
            "Working Different Job",
            "Left Job",
            "Language Issue"
        ]
    elif contactable == "Yes" and retention == "No":
        return [
            "Not Working",
            "Did Not Join"
        ]
    else:
        return [
            "Unable To Track",
            "Not Working"
        ]

def sub_reason(pic):
    mapping = {
        "Left Job": [
            "Salary Issue",
            "Higher Study",
            "Family Issue",
            "Environment"
        ],
        "Did Not Join": [
            "No Interview",
            "Personal Issue"
        ],
        "Unable To Track": [
            "Switched Off",
            "Wrong Number",
            "No Response"
        ]
    }
    return mapping.get(pic, ["NA"])

# =========================================================
# 📋 MAIN FORM
# =========================================================
def main_form():

    st.title("Student Verification Form")

    # FETCH
    contact_fetch = st.text_input("Enter Contact to Fetch")

    if st.button("Fetch Data"):
        row = fetch_test2(contact_fetch)
        if row:
            st.session_state.prefill = row
            st.success("Data Loaded")
        else:
            st.warning("No Match Found")

    data = st.session_state.get("prefill", {})

    with st.form("form"):
        c1, c2, c3 = st.columns(3)

        # ========================
        # BASIC
        # ========================
        with c1:
            st.subheader("Basic")

            student = st.text_input("Student", data.get("Student Name", ""))
            cmis = st.text_input("CMIS", data.get("CMIS ID", ""))
            contact = st.text_input("Contact", data.get("Contact Number", ""))
            contactable = st.selectbox("Contactable", ["Yes", "No"])

        # ========================
        # JOB
        # ========================
        with c2:
            st.subheader("Job")

            retention = st.selectbox("Retention", ["Yes", "No"])
            company = st.text_input("Company", data.get("Company Name", ""))
            salary = st.text_input("Salary", data.get("salary", ""))
            doj = st.date_input("DOJ", date.today())

        # ========================
        # PIC
        # ========================
        with c3:
            st.subheader("PIC Logic")

            pic = st.selectbox("PIC Category", pic_options(contactable, retention))
            reason = st.selectbox("Sub Reason", sub_reason(pic))

            remarks1 = st.text_area("Remarks_1")
            remarks2 = st.text_area("Remarks_2")

        submit = st.form_submit_button("Submit")

        if submit:
            sheet.append_row([
                st.session_state.user,
                student,
                cmis,
                contact,
                contactable,
                retention,
                company,
                salary,
                str(doj),
                pic,
                reason,
                remarks1,
                remarks2
            ])

            st.success("Submitted Successfully")

# =========================================================
# 🔁 ROUTING
# =========================================================
menu = ["Login", "Register"]

if not st.session_state.logged_in:
    choice = st.sidebar.selectbox("Menu", menu)

    if choice == "Login":
        login()
    else:
        register()

else:
    st.sidebar.write(f"Logged in: {st.session_state.user}")

    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    main_form()

# =========================================================
# FOOTER
# =========================================================
st.markdown("© 2025 Student Verification System")