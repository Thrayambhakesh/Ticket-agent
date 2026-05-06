import base64
import hashlib
import os
import secrets
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import streamlit as st

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly"
]

def _generate_pkce_pair():
    """Generate a PKCE code_verifier and code_challenge."""
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge

def authenticate_user():
    code_verifier, code_challenge = _generate_pkce_pair()

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": st.secrets["GOOGLE_CLIENT_ID"],
                "client_secret": st.secrets["GOOGLE_CLIENT_SECRET"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [st.secrets["REDIRECT_URI"]],
            }
        },
        scopes=SCOPES,
        redirect_uri=st.secrets["REDIRECT_URI"]
    )

    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )

    # ✅ Append code_verifier and state to the auth URL as custom params
    # so they come back to us in the redirect alongside ?code=...
    # We encode them into the `state` param instead (safest approach)
    import json, urllib.parse
    state_payload = json.dumps({"state": state, "cv": code_verifier})
    encoded_state = urllib.parse.quote(state_payload)

    # Rebuild auth_url replacing the state param with our encoded payload
    auth_url = auth_url.replace(
        f"state={urllib.parse.quote(state)}",
        f"state={encoded_state}"
    )

    return auth_url


def get_user_credentials(auth_code, raw_state):
    """raw_state is the full state query param returned by Google."""
    import json, urllib.parse

    try:
        state_payload = json.loads(urllib.parse.unquote(raw_state))
        code_verifier = state_payload["cv"]
        original_state = state_payload["state"]
    except Exception:
        raise ValueError("Invalid state parameter — possible CSRF or session loss.")

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": st.secrets["GOOGLE_CLIENT_ID"],
                "client_secret": st.secrets["GOOGLE_CLIENT_SECRET"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [st.secrets["REDIRECT_URI"]],
            }
        },
        scopes=SCOPES,
        state=original_state,
        redirect_uri=st.secrets["REDIRECT_URI"]
    )

    flow.fetch_token(
        code=auth_code,
        code_verifier=code_verifier,
    )

    return flow.credentials


# ---- rest of the file stays exactly the same ----

def get_gmail_service(credentials=None):
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    return build("gmail", "v1", credentials=credentials)


def fetch_unread_emails(credentials):
    service = get_gmail_service(credentials)
    results = service.users().messages().list(
        userId="me", labelIds=["INBOX"], q="is:unread", maxResults=10
    ).execute()
    messages = results.get("messages", [])
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
                        import base64
                        body = base64.urlsafe_b64decode(data).decode("utf-8")
                        break
        emails.append({"id": msg["id"], "sender": sender, "subject": subject, "body": body})
        mark_email_as_read(service, msg["id"])
    return emails


def send_email(credentials, to, subject, body):
    from email.mime.text import MIMEText
    import base64
    service = get_gmail_service(credentials)
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return service.users().messages().send(userId="me", body={"raw": raw}).execute()


def mark_email_as_read(service, msg_id):
    service.users().messages().modify(
        userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}
    ).execute()


def archive_email(service, msg_id):
    service.users().messages().modify(
        userId="me", id=msg_id, body={"removeLabelIds": ["INBOX"]}
    ).execute()


def delete_email(service, msg_id):
    service.users().messages().trash(userId="me", id=msg_id).execute()
    
def get_user_email(credentials):
    """Fetch the authenticated user's email via Gmail API."""
    service = get_gmail_service(credentials)
    profile = service.users().getProfile(userId="me").execute()
    return profile["emailAddress"]