from groq import Groq
from config import GROQ_API_KEY
import json

client = Groq(api_key=GROQ_API_KEY)

def classify_and_generate(ticket_text):
    prompt = f"""
You are an enterprise customer support AI assistant.

Tasks:
1. Classify the email into one category:
   - billing
   - technical
   - refund
   - account
   - general
   - spam
   - job_alert
   - newsletter

2. Assign urgency:
   - low
   - medium
   - high

3. Generate a professional support response draft.

Rules:
- Ignore promotional emails
- Mark job alerts/newsletters appropriately
- Keep tone professional
- If spam/newsletter, reply should politely state no action required

Email:
{ticket_text}

Return ONLY valid JSON:
{{
    "category": "",
    "urgency": "",
    "reply": ""
}}
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": "You are an expert enterprise support classifier."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.2
    )

    content = response.choices[0].message.content

    try:
        return json.loads(content)
    except:
        return {
            "category": "general",
            "urgency": "medium",
            "reply": content
        }
        
def batch_classify_emails(emails):
    email_summaries = []

    for i, email in enumerate(emails):
        email_summaries.append(
            f"""
Email {i+1}:
Sender: {email['sender']}
Subject: {email['subject']}
Body: {email['body'][:1200]}
"""
        )

    combined_prompt = f"""
You are an enterprise AI support assistant.

For EACH email below:
1. Classify category:
billing, technical, refund, account, general, spam, newsletter, job_alert
2. Assign urgency:
low, medium, high
3. Draft professional reply

Return ONLY valid JSON array:
[
 {{
   "category": "",
   "urgency": "",
   "reply": ""
 }}
]

Emails:
{''.join(email_summaries)}
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "You classify support emails in batch."},
            {"role": "user", "content": combined_prompt}
        ],
        temperature=0.2
    )

    content = response.choices[0].message.content

    try:
        return json.loads(content)
    except:
        return []