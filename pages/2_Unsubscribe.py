import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

st.title("Unsubscribe")

st.write("Enter your email below to unsubscribe from the weekly PressWatch digest.")

email = st.text_input("Email")

if st.button("Unsubscribe"):
    if not email:
        st.error("Please enter an email.")
    else:
        try:
            # Google Sheets connection
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            creds = Credentials.from_service_account_info(
                st.secrets["google"], scopes=scopes
            )
            client = gspread.authorize(creds)

            sheet = client.open_by_key(st.secrets["google"]["sheet_id"]).sheet1
            records = sheet.get_all_records()

            # search for email
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
