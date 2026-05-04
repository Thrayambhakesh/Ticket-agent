import os.path
import base64
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
import streamlit as st
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send"
]

def authenticate_user():
    flow = Flow.from_client_secrets_file(
        st.secrets["GOOGLE_CLIENT_SECRETS_FILE"],
        scopes=SCOPES,
        redirect_uri=st.secrets["REDIRECT_URI"]
    )

    auth_url, _ = flow.authorization_url(
        prompt="consent",
        access_type="offline"
    )

    return auth_url

def get_user_credentials(auth_code):
    flow = Flow.from_client_secrets_file(
        st.secrets["GOOGLE_CLIENT_SECRETS_FILE"],
        scopes=SCOPES,
        redirect_uri=st.secrets["REDIRECT_URI"]
    )

    flow.fetch_token(code=auth_code)
    return flow.credentials

"""def get_gmail_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(
                port=8080,
                access_type="offline",
                prompt="consent"
            )

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)"""

def get_gmail_service(credentials=None):
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    return build("gmail", "v1", credentials=credentials)

def fetch_unread_emails(credentials):
    service = get_gmail_service(credentials)
    results = service.users().messages().list(
        userId="me",
        labelIds=["INBOX"],
        q="is:unread",
        maxResults=10
    ).execute()

    messages = results.get("messages", [])[:10]
    
    emails = []

    for msg in messages:
        message = service.users().messages().get(
            userId="me", id=msg["id"], format="full"
        ).execute()

        headers = message["payload"]["headers"]
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "")
        sender = next((h["value"] for h in headers if h["name"] == "From"), "")

        body = ""
        if "parts" in message["payload"]:
            for part in message["payload"]["parts"]:
                if part["mimeType"] == "text/plain":
                    data = part["body"].get("data")
                    if data:
                        body = base64.urlsafe_b64decode(data).decode("utf-8")
                        break

        emails.append({
            "id": msg["id"],
            "sender": sender,
            "subject": subject,
            "body": body
        })
        mark_email_as_read(service, msg["id"])

    return emails

def send_email(credentials, to, subject, body):
    service = get_gmail_service(credentials)

    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    send_message = (
        service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
    )

    return send_message

def mark_email_as_read(service, msg_id):
    service.users().messages().modify(
        userId="me",
        id=msg_id,
        body={"removeLabelIds": ["UNREAD"]}
    ).execute()


def archive_email(service, msg_id):
    service.users().messages().modify(
        userId="me",
        id=msg_id,
        body={"removeLabelIds": ["INBOX"]}
    ).execute()


def delete_email(service, msg_id):
    service.users().messages().trash(
        userId="me",
        id=msg_id
    ).execute()