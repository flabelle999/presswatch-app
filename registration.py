import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import uuid
import os
import json
from datetime import datetime

# ---------------------------------------------------------------------
# 1️⃣  Load secrets
# ---------------------------------------------------------------------

with open(st.secrets["google"]["service_json_path"]) as f:
    GOOGLE_SERVICE_JSON = json.load(f)
#GOOGLE_SERVICE_JSON = json.loads(st.secrets["google"]["service_json"])
#GOOGLE_SERVICE_JSON = st.secrets["google"]["service_json"]
MAILGUN_API_KEY = st.secrets["mailgun"]["api_key"]
MAILGUN_DOMAIN = st.secrets["mailgun"]["domain"]
MAILGUN_FROM = st.secrets["mailgun"]["from_email"]

SHEET_NAME = "PressWatch Subscribers"   # your private Google Sheet name

# ---------------------------------------------------------------------
# 2️⃣  Google Sheet connection
# ---------------------------------------------------------------------
def get_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(GOOGLE_SERVICE_JSON, scope)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).sheet1
    return sheet

# ---------------------------------------------------------------------
# 3️⃣  Mailgun send function
# ---------------------------------------------------------------------
def send_mailgun_html(to_email: str, subject: str, html_body: str):
    url = f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages"
    data = {
        "from": MAILGUN_FROM,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    }
    resp = requests.post(url, auth=("api", MAILGUN_API_KEY), data=data)
    if resp.status_code != 200:
        st.error(f"Mailgun error: {resp.text}")
    return resp

# ---------------------------------------------------------------------
# 4️⃣  HTML template for thank-you email
# ---------------------------------------------------------------------
def build_thankyou_email(name: str):
    return f"""
    <html>
      <body style="font-family:Arial, sans-serif; background-color:#f7f7f7; padding:20px;">
        <div style="max-width:600px;margin:auto;background-color:#ffffff;border-radius:10px;padding:25px;">
          <h2 style="color:#ff8c00;text-align:center;">Welcome to PressWatch, {name}!</h2>
          <p>Thank you for registering to receive weekly insights about the telecom industry.</p>
          <p>You’ll now get a concise weekly summary of key press releases and what they mean for Zhone.</p>
          <div style="text-align:center;margin-top:25px;">
            <a href="https://presswatch.streamlit.app"
               style="background-color:#ff8c00;color:#fff;padding:10px 20px;
                      border-radius:6px;text-decoration:none;font-weight:bold;">
               Visit PressWatch
            </a>
          </div>
          <p style="font-size:12px;color:#888;margin-top:40px;text-align:center;">
            You can unsubscribe anytime via the link in our emails.
          </p>
        </div>
      </body>
    </html>
    """

# ---------------------------------------------------------------------
# 5️⃣  Streamlit registration form
# ---------------------------------------------------------------------
def registration_form():
    st.header("📧 Join the PressWatch Distribution List")

    with st.form("registration_form"):
        name = st.text_input("Your name")
        email = st.text_input("Email address")
        submitted = st.form_submit_button("Register")

    if submitted:
        if not name or not email:
            st.warning("Please fill in both your name and email.")
            return

        sheet = get_sheet()
        existing = sheet.findall(email)
        if existing:
            st.info("You are already registered.")
            return

        token = str(uuid.uuid4())
        row = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name, email, token, "active"]
        sheet.append_row(row)
        st.success("Registration successful! Check your inbox for a confirmation email.")

        html = build_thankyou_email(name)
        send_mailgun_html(email, "Welcome to PressWatch!", html)

# ---------------------------------------------------------------------
# 6️⃣  Main entry point
# ---------------------------------------------------------------------
if __name__ == "__main__":
    registration_form()
