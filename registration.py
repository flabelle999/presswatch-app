import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import requests
import uuid
import json
from datetime import datetime

# ---------------------------------------------------------------------
# 1️⃣  Load configuration from Streamlit secrets
# ---------------------------------------------------------------------

SHEET_NAME = "PressWatch Subscribers"   # your private Google Sheet name

# Microsoft Graph / Azure AD settings
MS_TENANT_ID = st.secrets["microsoft"]["tenant_id"]
MS_CLIENT_ID = st.secrets["microsoft"]["client_id"]
MS_CLIENT_SECRET = st.secrets["microsoft"]["client_secret"]
# This should be the UPN or mailbox that will send the email (e.g. "you@company.com")
MS_FROM_USER = st.secrets["microsoft"]["from_user"]


# ---------------------------------------------------------------------
# 2️⃣  Google Sheet connection helpers
# ---------------------------------------------------------------------
def _get_google_service_info() -> dict:
    """
    Returns the service-account JSON as a dict.

    - In Streamlit Cloud, you typically store the full JSON directly
      under [google] in secrets.toml.
    - Locally, you *may* still use a path via google.service_json_path.
    """
    google_secrets = st.secrets["google"]

    # Optional backward-compatible path usage
    if "service_json_path" in google_secrets:
        with open(google_secrets["service_json_path"]) as f:
            return json.load(f)
    else:
        # Streamlit Cloud: secrets["google"] already contains the JSON fields
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


# ---------------------------------------------------------------------
# 3️⃣  Microsoft Graph helpers (replace Mailgun)
# ---------------------------------------------------------------------
def _get_ms_access_token() -> str:
    """
    Get an OAuth2 access token using client_credentials for Microsoft Graph.
    Requires:
      - tenant_id
      - client_id
      - client_secret
    with Mail.Send application permission granted in Azure.
    """
    token_url = f"https://login.microsoftonline.com/{MS_TENANT_ID}/oauth2/v2.0/token"

    data = {
        "client_id": MS_CLIENT_ID,
        "client_secret": MS_CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }

    resp = requests.post(token_url, data=data)
    try:
        resp.raise_for_status()
    except Exception as e:
        st.error(f"Microsoft Graph token error: {resp.text}")
        raise e

    token_json = resp.json()
    return token_json["access_token"]


def send_ms_html_email(to_email: str, subject: str, html_body: str):
    """
    Sends an HTML email via Microsoft Graph using app-only permissions.

    MS_FROM_USER should be the UPN/mailbox that is allowed to send mail,
    for example: "presswatch-notify@yourcompany.com".
    """
    access_token = _get_ms_access_token()

    send_url = f"https://graph.microsoft.com/v1.0/users/{MS_FROM_USER}/sendMail"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": html_body,
            },
            "toRecipients": [
                {"emailAddress": {"address": to_email}}
            ],
        },
        "saveToSentItems": "false",
    }

    resp = requests.post(send_url, headers=headers, json=payload)
    if resp.status_code not in (200, 202):
        st.error(f"Microsoft Graph sendMail error ({resp.status_code}): {resp.text}")
    return resp


# ---------------------------------------------------------------------
# 4️⃣  HTML template for thank-you email
# ---------------------------------------------------------------------
def build_thankyou_email(name: str):
    return f"""
    <html>
    <body style="margin:0;padding:0;background:#f4f4f7;font-family:Arial,Helvetica,sans-serif;">
        <table align="center" width="100%" cellpadding="0" cellspacing="0" border="0" style="padding:30px 0;">
        <tr>
            <td align="center">

            <!-- Outer container -->
            <table width="600" cellpadding="0" cellspacing="0" border="0" 
                    style="background:#ffffff;border-radius:10px;overflow:hidden;
                            box-shadow:0 4px 20px rgba(0,0,0,0.08);">

                <!-- Header -->
                <tr>
                <td align="center" style="background:#ff8c00;padding:25px 20px;">
                    <h1 style="margin:0;font-size:26px;font-weight:bold;color:white;">
                    Welcome to PressWatch
                    </h1>
                </td>
                </tr>

                <!-- Body -->
                <tr>
                <td style="padding:35px 40px;color:#333333;font-size:16px;line-height:1.6;">

                    <p style="font-size:18px;font-weight:bold;margin-top:0;">
                    Hello {{name}},
                    </p>

                    <p>
                    Thank you for joining the PressWatch distribution list!
                    </p>

                    <p>
                    You’ll now receive a clean, curated weekly summary of the
                    most important telecom press releases — along with a short
                    analysis of what they mean for Zhone.
                    </p>

                    <p>
                    Our goal is to save you time, help you stay informed,
                    and bring clarity to an ever-changing competitive landscape.
                    </p>

                    <!-- CTA Button -->
                    <div style="text-align:center;margin:40px 0 25px 0;">
                    <a href="https://presswatch.streamlit.app"
                        style="background:#ff8c00;color:white;padding:14px 28px;
                                border-radius:6px;text-decoration:none;font-weight:bold;
                                font-size:16px;display:inline-block;">
                        Visit PressWatch
                    </a>
                    </div>

                    <p style="font-size:13px;color:#777;text-align:center;margin-top:30px;">
                    You can unsubscribe anytime using the link provided in our emails.
                    </p>

                </td>
                </tr>

            </table>

            <!-- Footer -->
            <table width="600" cellpadding="0" cellspacing="0" border="0" style="margin-top:20px;">
                <tr>
                <td style="text-align:center;font-size:11px;color:#999;">
                    © 2025 PressWatch · Competitive Intelligence Automation
                </td>
                </tr>
            </table>

            </td>
        </tr>
        </table>
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

        # Check if already registered
        sheet = get_sheet()
        existing = sheet.findall(email)
        if existing:
            st.info("You are already registered.")
            return

        # Append new registration row
        token = str(uuid.uuid4())
        row = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name, email, token, "active"]
        sheet.append_row(row)

        st.success("Registration successful! Check your inbox for a confirmation email.")

        # Send confirmation email via Microsoft Graph
        html = build_thankyou_email(name)
        send_ms_html_email(email, "Welcome to PressWatch!", html)


# ---------------------------------------------------------------------
# 6️⃣  Main entry point (for local testing)
# ---------------------------------------------------------------------
if __name__ == "__main__":
    registration_form()
