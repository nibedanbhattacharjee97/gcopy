# ============================================
# 🚀 FINAL ENTERPRISE STUDENT VERIFICATION SYSTEM
# ============================================

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date
import hashlib
import pandas as pd

# ============================================
# ⚙️ CONFIG
# ============================================
st.set_page_config(page_title="Enterprise Verification System", layout="wide")

# ============================================
# 🔐 AUTH HELPERS
# ============================================
def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

# ============================================
# 📡 GOOGLE CONNECT
# ============================================
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

credentials = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"], scopes=scope
)
client = gspread.authorize(credentials)

main_sheet = client.open("Test").sheet1
login_sheet = client.open("Test_Spoc_PassWord").sheet1
test2_sheet = client.open("Test2").sheet1

# ============================================
# 🔑 SESSION
# ============================================
if "login" not in st.session_state:
    st.session_state.login = False
if "user" not in st.session_state:
    st.session_state.user = ""

# ============================================
# 🔐 LOGIN / REGISTER
# ============================================
def login_page():
    st.title("🔐 Login")
    u = st.text_input("User")
    p = st.text_input("Password", type="password")

    if st.button("Login"):
        users = login_sheet.get_all_records()
        for row in users:
            if row["spoc_name"] == u and row["password"] == hash_password(p):
                st.session_state.login = True
                st.session_state.user = u
                st.rerun()
        st.error("Invalid")

    st.markdown("---")
    st.subheader("Register")
    ru = st.text_input("New User")
    rp = st.text_input("New Password", type="password")

    if st.button("Register"):
        login_sheet.append_row([ru, hash_password(rp), str(datetime.now())])
        st.success("Registered")

# ============================================
# 📊 DASHBOARD
# ============================================
def dashboard(df):
    st.subheader("📊 Analytics Dashboard")

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Total Records", len(df))

    with col2:
        working = len(df[df["Retention Status"] == "Working"])
        st.metric("Working", working)

    st.bar_chart(df["Retention Status"].value_counts())

# ============================================
# 📥 EXPORT
# ============================================
def export_data(df):
    st.download_button("📥 Download CSV", df.to_csv(index=False), "data.csv")

# ============================================
# 🔍 SEARCH
# ============================================
def search(df):
    query = st.text_input("Search")
    if query:
        df = df[df.astype(str).apply(lambda x: x.str.contains(query)).any(axis=1)]
    return df

# ============================================
# ✏️ UPDATE SYSTEM
# ============================================
def update_record(df):
    st.subheader("✏️ Update Record")
    if len(df) == 0:
        return

    idx = st.selectbox("Select Row", df.index)
    row = df.loc[idx]

    name = st.text_input("Student", row["Student Name"])

    if st.button("Update"):
        cell = main_sheet.find(row["Student Name"])
        main_sheet.update_cell(cell.row, 3, name)
        st.success("Updated")

# ============================================
# 🧠 FETCH TEST2
# ============================================
def fetch_test2(number):
    data = test2_sheet.get_all_records()
    for r in data:
        if str(r.get("Contact Number")) == str(number):
            return r
    return None

# ============================================
# 📋 MAIN FORM
# ============================================
def main_app():
    st.sidebar.success(st.session_state.user)

    if st.sidebar.button("Logout"):
        st.session_state.login = False
        st.rerun()

    data = main_sheet.get_all_records()
    df = pd.DataFrame(data)

    tab1, tab2, tab3 = st.tabs(["Form", "Dashboard", "Manage"])

    # FORM
    with tab1:
        st.subheader("📋 Entry Form")

        number = st.text_input("Contact")
        if st.button("Fetch"):
            result = fetch_test2(number)
            if result:
                st.success("Fetched")
                st.write(result)

        with st.form("form"):
            name = st.text_input("Student Name")
            status = st.selectbox("Retention Status", ["Working", "Not Working"])
            reason = st.text_area("Reason")

            submit = st.form_submit_button("Submit")

        if submit:
            main_sheet.append_row([
                st.session_state.user,
                name,
                number,
                status,
                reason,
                str(date.today())
            ])
            st.success("Saved")

    # DASHBOARD
    with tab2:
        if not df.empty:
            dashboard(df)
            export_data(df)

    # MANAGE
    with tab3:
        df = search(df)
        st.dataframe(df)
        update_record(df)

# ============================================
# 🚀 ROUTING
# ============================================
if not st.session_state.login:
    login_page()
else:
    main_app()
