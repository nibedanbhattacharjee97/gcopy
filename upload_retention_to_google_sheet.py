import gspread
from google.oauth2.service_account import Credentials
import sys
import os

SERVICE_ACCOUNT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "service_account.json")
DEFAULT_SPREADSHEET_ID = "11mQnQfQmRBWUglDMQ8O5pUkz1jv4FwGAEw7crPXi4Qc"

HEADERS = [
    'CMISID', 'Student Name', 'Contact Number', 'Alt Contact Number', 'Gender',
    'Center Name', 'State', 'Course', 'Donor Name', 'Placed Company',
    'Designation', 'Salary', 'Date Of Joining', 'Calling Round', 'Exiting NPS',
    'Contactable (Yes/No)', 'Verification Outcome / Call Type (Contactable = Yes)',
    'Retention Status (Working in same job/ working in different job/ Unable to track/ Not working at all)',
    'How many months working', 'Current Company Name', 'Net Promoter Score',
    'Current Salary', 'Current Designation', 'DOJ', 'Reason Behind leaving the Job (if left)',
    'Need any further job (Yes/No)', 'Verification Date', 'Remarks',
    'Personal/Profile issue Remarks', 'Remarks 2', 'Remarks 3',
    'Call_Status', 'Call_id', 'Concat'
]

def format_retention_sheet(target_id=DEFAULT_SPREADSHEET_ID):
    print(f"Connecting to Google Spreadsheet {target_id}...")
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT, scopes=scope)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(target_id)
    ws = sh.sheet1

    if ws.col_count < len(HEADERS) + 5:
        ws.resize(rows=max(ws.row_count, 1000), cols=len(HEADERS) + 5)

    ws.update(values=[HEADERS], range_name=f"A1:{gspread.utils.rowcol_to_a1(1, len(HEADERS))}")

    # Format Pre-call (A1:O1) - Blue
    ws.format('A1:O1', {
        'backgroundColor': {'red': 0.0, 'green': 0.69, 'blue': 0.94},
        'textFormat': {'bold': True, 'foregroundColor': {'red': 1.0, 'green': 1.0, 'blue': 1.0}},
        'horizontalAlignment': 'CENTER',
        'wrapStrategy': 'WRAP'
    })

    # Format Verification (P1:AE1) - Light Green
    ws.format('P1:AE1', {
        'backgroundColor': {'red': 0.663, 'green': 0.816, 'blue': 0.557},
        'textFormat': {'bold': True, 'foregroundColor': {'red': 0.0, 'green': 0.0, 'blue': 0.0}},
        'horizontalAlignment': 'CENTER',
        'wrapStrategy': 'WRAP'
    })

    # Net Promoter Score (U1) - Solid Black with White text
    ws.format('U1', {
        'backgroundColor': {'red': 0.0, 'green': 0.0, 'blue': 0.0},
        'textFormat': {'bold': True, 'foregroundColor': {'red': 1.0, 'green': 1.0, 'blue': 1.0}},
        'horizontalAlignment': 'CENTER',
        'wrapStrategy': 'WRAP'
    })

    # System Tracking (AF1:AH1) - Slate Blue
    ws.format('AF1:AH1', {
        'backgroundColor': {'red': 0.35, 'green': 0.45, 'blue': 0.55},
        'textFormat': {'bold': True, 'foregroundColor': {'red': 1.0, 'green': 1.0, 'blue': 1.0}},
        'horizontalAlignment': 'CENTER',
        'wrapStrategy': 'WRAP'
    })

    print(f"Successfully formatted '{ws.title}' in spreadsheet {target_id}!")

if __name__ == "__main__":
    sid = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SPREADSHEET_ID
    format_retention_sheet(sid)
