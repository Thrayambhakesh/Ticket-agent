import streamlit as st
import pandas as pd
from gmail_service import authenticate_user, get_user_credentials
from gmail_service import (
    fetch_unread_emails,
    send_email,
    archive_email,
    delete_email,
    get_gmail_service
)
from groq_classifier import batch_classify_emails
from supabase_client import insert_ticket, get_tickets, approve_ticket
import plotly.express as px
from datetime import datetime


# ---------------- PAGE CONFIG ----------------
st.set_page_config(
    page_title="AI Support Ticket Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------- CUSTOM CSS ----------------
# Load external CSS
with open("styles.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# ---------------- GOOGLE AUTH ----------------
query_params = st.query_params

if "code" not in query_params:
    auth_url = authenticate_user()
    st.markdown("## Welcome to InboxIQ")
    st.markdown("Please login with Google to continue.")
    st.markdown(f"[Login with Google]({auth_url})")
    st.stop()

if "gmail_creds" not in st.session_state:
    try:
        code = query_params["code"]
        creds = get_user_credentials(code)
        st.session_state.gmail_creds = creds
        st.query_params.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Authentication failed: {str(e)}")
        st.session_state.clear()
        st.stop()

# ---------------- HEADER ----------------
st.title("InboxIQ")
st.markdown('<p style="font-size: 1.3rem; color: #0f172a;">Enterprise-grade AI email triage, urgency detection, and smart response generation</p>', unsafe_allow_html=True)

# ---------------- SIDEBAR ----------------
st.sidebar.title("Control Panel")

fetch_button = st.sidebar.button("Fetch Last 10 Emails")
refresh_button = st.sidebar.button("Refresh Dashboard")
if st.sidebar.button("Logout"):
    if "gmail_creds" in st.session_state:
        del st.session_state["gmail_creds"]
    st.query_params.clear()
    st.rerun()
search_term = st.sidebar.text_input("Search by Sender / Subject")

category_options = [
    "All", "billing", "technical", "refund",
    "account", "general", "spam", "newsletter", "job_alert"
]
category_filter = st.sidebar.selectbox("Filter Category", category_options)

urgency_filter = st.sidebar.selectbox(
    "Filter Urgency",
    ["All", "high", "medium", "low"]
)

st.sidebar.markdown("---")
st.sidebar.subheader("Analytics Options")
show_charts = st.sidebar.checkbox("Show Performance Charts", value=True)

# ---------------- FETCH EMAILS ----------------
if fetch_button:
    try:
        with st.spinner("Fetching and processing emails..."):
            emails = fetch_unread_emails(st.session_state.gmail_creds)[:10]

            if not emails:
                st.warning("No unread emails found.")
            else:
                processed_count = 0
                spam_count = 0

                progress_bar = st.progress(0)
                status_text = st.empty()
                ai_results = batch_classify_emails(emails)

                for i, (email, ai_result) in enumerate(zip(emails, ai_results)):
                    progress_bar.progress((i + 1) / len(emails))
                    status_text.text(f"Processing email {i+1} of {len(emails)}...")
                    if ai_result["category"] in ["spam", "newsletter", "job_alert"]:
                        spam_count += 1

                    ticket_data = {
                        "gmail_id": email["id"],
                        "user_email": st.session_state.gmail_creds.id_token["email"],
                        "sender": email["sender"],
                        "subject": email["subject"],
                        "body": email["body"][:1500],
                        "category": ai_result["category"],
                        "urgency": ai_result["urgency"],
                        "ai_reply": ai_result["reply"]
                    }

                    insert_ticket(ticket_data)
                    processed_count += 1

                st.success(f"Processed {processed_count} emails successfully")
                st.info(f"Filtered {spam_count} low-priority emails")

    except Exception as e:
        st.error(f"Error fetching emails: {str(e)}")

# ---------------- LOAD TICKETS ----------------
try:
    response = get_tickets(st.session_state.gmail_creds.id_token["email"])
    tickets = response.data
except Exception as e:
    st.error(f"Supabase Error: {str(e)}")
    tickets = []

df = pd.DataFrame(tickets)


# ---------------- DASHBOARD METRICS ----------------
if not df.empty:
    total_tickets = len(df)
    high_urgency = len(df[df["urgency"] == "high"])
    approved_count = len(df[df["approved"] == True]) if "approved" in df.columns else 0
    spam_filtered = len(df[df["category"].isin(["spam", "newsletter", "job_alert"])])

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Tickets", total_tickets)
    col2.metric("High Urgency", high_urgency)
    col3.metric("Approved Replies", approved_count)
    col4.metric("Spam/Newsletters", spam_filtered)

# ---------------- FILTERS ----------------
if not df.empty:
    if category_filter != "All":
        df = df[df["category"] == category_filter]

    if urgency_filter != "All":
        df = df[df["urgency"] == urgency_filter]

    if search_term:
        df = df[
            df["sender"].str.contains(search_term, case=False, na=False) |
            df["subject"].str.contains(search_term, case=False, na=False)
        ]

# ---------------- TABS ----------------
tab1, tab2 = st.tabs(["Ticket Inbox", "Analytics Dashboard"])

# =====================================================
# TICKET INBOX
# =====================================================
with tab1:
    st.subheader("Support Ticket Inbox")

    if df.empty:
        st.info("No tickets available.")
    else:
        for _, row in df.iterrows():

            urgency_class = row["urgency"].lower() if pd.notna(row["urgency"]) else "low"

            icon = ""

            with st.expander(
                f"#{row['id']} | {row['subject']} | {row['category'].upper()}"
            ):
                st.markdown(f"**Sender:** {row['sender']}")
                st.markdown(
                    f"**Urgency:** <span class='{urgency_class}'>{row['urgency'].upper()}</span>",
                    unsafe_allow_html=True
                )

                st.markdown("### Customer Email")
                st.text_area(
                    f"Body_{row['id']}",
                    row["body"],
                    height=200,
                    disabled=True
                )

                st.markdown("### AI Draft Response")
                edited_reply = st.text_area(
                    f"Reply_{row['id']}",
                    row["ai_reply"],
                    height=180
                )

                colA, colB, colC = st.columns(3)

                with colA:
                    if st.button(f"Approve & Send #{row['id']}"):
                        try:
                            send_email(
                                st.session_state.gmail_creds,
                                row["sender"],
                                f"Re: {row['subject']}",
                                edited_reply
                            )
                            approve_ticket(row["id"])
                            st.success("Reply sent successfully")
                        except Exception as e:
                            st.error(f"Email send failed: {str(e)}")

                with colB:
                    if st.button(f"Archive #{row['id']}"):
                        try:
                            service = get_gmail_service(st.session_state.gmail_creds)
                            archive_email(service, row["gmail_id"])
                            st.success("Email archived successfully")
                        except Exception as e:
                            st.error(f"Archive failed: {str(e)}")

                with colC:
                    if st.button(f"Delete #{row['id']}"):
                        try:
                            service = get_gmail_service(st.session_state.gmail_creds)
                            delete_email(service, row["gmail_id"])
                            st.success("Email deleted successfully")
                        except Exception as e:
                            st.error(f"Delete failed: {str(e)}")
            
# =====================================================
# ANALYTICS
# =====================================================
with tab2:
    st.subheader("Performance Analytics Dashboard")

    if not df.empty and show_charts:

        # Category Breakdown
        category_counts = df["category"].value_counts().reset_index()
        category_counts.columns = ["Category", "Count"]

        fig1 = px.bar(
            category_counts,
            x="Category",
            y="Count",
            title="Ticket Category Breakdown"
        )
        st.plotly_chart(fig1, width="stretch")

        # Urgency Distribution
        urgency_counts = df["urgency"].value_counts().reset_index()
        urgency_counts.columns = ["Urgency", "Count"]

        fig2 = px.pie(
            urgency_counts,
            names="Urgency",
            values="Count",
            title="Urgency Distribution"
        )
        st.plotly_chart(fig2, width="stretch")

        # Daily Trends
        if "created_at" in df.columns:
            df["created_at"] = pd.to_datetime(df["created_at"])
            df["date"] = df["created_at"].dt.date

            trend_data = df.groupby("date").size().reset_index(name="Tickets")

            fig3 = px.line(
                trend_data,
                x="date",
                y="Tickets",
                title="Daily Ticket Volume"
            )
            st.plotly_chart(fig3, width="stretch")

# ---------------- FOOTER ----------------
st.markdown("---")
st.caption("Built with Streamlit | Gmail API | Groq LLM | Supabase")

