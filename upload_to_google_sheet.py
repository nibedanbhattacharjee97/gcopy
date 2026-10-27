import gspread
from google.oauth2.service_account import Credentials
import csv
import os
import time

SPREADSHEET_ID = "1lNVa5ELW7GR7vg3iPAedO5Ysy9UjcJM7l0-2vyDR5J8"
WORKSHEET_NAME = "enrollment_Verification"
CSV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "enrollment_data.csv")
SERVICE_ACCOUNT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "service_account.json")

def main():
    print(f"Connecting to Google Spreadsheet {SPREADSHEET_ID}...")
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT, scopes=scope)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)

    # Check existing worksheets
    existing_ws = {ws.title.lower(): ws for ws in sh.worksheets()}
    target_ws = None
    for name in [WORKSHEET_NAME.lower(), "enrollment_verification"]:
        if name in existing_ws:
            target_ws = existing_ws[name]
            print(f"Found existing worksheet '{target_ws.title}'")
            break

    # Read CSV data
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        all_rows = list(reader)

    total_rows = len(all_rows)
    print(f"Read {total_rows} rows from {CSV_FILE}")

    if not target_ws:
        print(f"Creating new worksheet '{WORKSHEET_NAME}' with {max(total_rows + 50, 3800)} rows and 39 columns...")
        target_ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=max(total_rows + 50, 3800), cols=39)
    else:
        # Resize worksheet if needed
        curr_r = target_ws.row_count
        curr_c = target_ws.col_count
        if curr_r < total_rows + 10 or curr_c < 39:
            print(f"Resizing worksheet from ({curr_r}, {curr_c}) to ({max(curr_r, total_rows + 50)}, {max(curr_c, 39)})...")
            target_ws.resize(rows=max(curr_r, total_rows + 50), cols=max(curr_c, 39))

    # Upload in chunks of 500 rows to ensure fast and reliable upload
    CHUNK_SIZE = 500
    for start_idx in range(0, total_rows, CHUNK_SIZE):
        end_idx = min(start_idx + CHUNK_SIZE, total_rows)
        chunk = all_rows[start_idx:end_idx]
        start_row = start_idx + 1
        end_row = end_idx
        range_name = f"A{start_row}:AM{end_row}"
        print(f"Uploading rows {start_row} to {end_row} ({range_name})...")
        target_ws.update(values=chunk, range_name=range_name)
        time.sleep(0.5)

    print("Data upload complete! Applying header styling (Blue for static info, Yellow for verification)...")
    try:
        # Format headers: A1:Q1 Blue (#00B0F0), R1:AM1 Yellow (#FFFF00)
        target_ws.format("A1:Q1", {
            "backgroundColor": {"red": 0.0, "green": 0.69, "blue": 0.94},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}},
            "horizontalAlignment": "CENTER"
        })
        target_ws.format("R1:AM1", {
            "backgroundColor": {"red": 1.0, "green": 1.0, "blue": 0.0},
            "textFormat": {"bold": True, "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0}},
            "horizontalAlignment": "CENTER"
        })
        print("Header styling applied successfully!")
    except Exception as e:
        print(f"Note: Header formatting skipped or optional: {e}")

    print(f"SUCCESS! Worksheet '{target_ws.title}' is now ready in Google Sheets with {total_rows} rows!")

if __name__ == "__main__":
    main()
