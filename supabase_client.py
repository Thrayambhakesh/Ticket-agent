from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def insert_ticket(data):
    return supabase.table("tickets").insert(data).execute()

def get_tickets(user_email):
    return supabase.table("tickets").select("*").eq("user_email", user_email).execute()
def approve_ticket(ticket_id):
    return supabase.table("tickets").update({"approved": True}).eq("id", ticket_id).execute()