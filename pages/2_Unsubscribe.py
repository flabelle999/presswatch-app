import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json

# ---------------------------------------------------------
# 1️⃣  Same configuration logic as registration.py
# ---------------------------------------------------------
SHEET_NAME = "PressWatch Subscribers"   # same sheet as registration

def _get_google_service_info() -> dict:
    google_secrets = st.secrets["google"]

    # If using local file path
    if "service_json_path" in google_secrets:
        with open(google_secrets["service_json_path"]) as f:
            return json.load(f)
    else:
        # Streamlit Cloud: full service-account JSON is already inside secrets
        return dict(google_secrets)


def get_sheet():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    service_info = _get_google_service_info()
    creds = Credentials.from_service_account_info(service_info, scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).sheet1
    return sheet


# ---------------------------------------------------------
# 2️⃣  Unsubscribe UI logic
# ---------------------------------------------------------
st.title("Unsubscribe")
st.write("Enter your email below to unsubscribe from the weekly PressWatch digest.")

email = st.text_input("Email")

if st.button("Unsubscribe"):
    if not email:
        st.error("Please enter an email.")
    else:
        try:
            sheet = get_sheet()
            records = sheet.get_all_records()

            row_index = None
            for i, row in enumerate(records, start=2):  # row 1 = header
                if row["email"].strip().lower() == email.strip().lower():
                    row_index = i
                    break

            if row_index:
                sheet.delete_rows(row_index)
                st.success("You have been unsubscribed successfully.")
            else:
                st.warning("This email is not in our subscription list.")

        except Exception as e:
            st.error(f"Error: {e}")