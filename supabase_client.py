from supabase import create_client
import os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
# Add this at the top of your supabase_client.py
print(f"Supabase URL: {url}")  # Debugging - remove after verification
print(f"Supabase Key: {key[:5]}...{key[-5:]}")  # Show partial key for security
# Initialize Supabase client


supabase = create_client(url, key)
print(supabase)

def save_user(email, name, news_email):
    # Check if user exists
    user = supabase.table("users").select("*").eq("email", email).execute()
    
    if not user.data:
        # Create new user with both email and news_email
        supabase.table("users").insert({
            "email": email,
            "name": name,
            "News_Email": news_email
        }).execute()
    else:
        # Update existing user's news_email
        supabase.table("users").update({
            "News_Email": news_email,
            "name": name
        }).eq("email", email).execute()

def subscribe_user(email, name, news_email, companies, frequency, send_hour_start, send_hour_end):
    try:
        # First ensure user exists
        save_user(email, name, news_email)
        
        # Get user ID
        user = supabase.table("users").select("*").eq("email", email).execute()
        user_id = user.data[0]['id']
        
        # Save customer data
        save_customer_data(news_email, email, companies, frequency, send_hour_start, send_hour_end)
        
        return True
    except Exception as e:
        print(f"Error subscribing user: {e}")
        return False

def unsubscribe_user(email):
    try:
        # Get user ID
        user = supabase.table("users").select("*").eq("email", email).execute()
        if not user.data:
            return True  # User doesn't exist, nothing to do
        
        user_id = user.data[0]['id']
        
        # Delete from customers table
        supabase.table("customers").delete().eq("user_id", user_id).execute()
        
        # Delete from email_tracker table
        supabase.table("email_tracker").delete().eq("user_id", user_id).execute()
        
        return True
    except Exception as e:
        print(f"Error unsubscribing user: {e}")
        return False

def is_user_subscribed(email):
    try:
        user = supabase.table("users").select("*").eq("email", email).execute()
        if not user.data:
            return False
            
        user_id = user.data[0]['id']
        
        customer = supabase.table("customers").select("*").eq("user_id", user_id).execute()
        return bool(customer.data)
    except Exception as e:
        print(f"Error checking subscription status: {e}")
        return False

def get_customer_data(email):
    user = supabase.table("users").select("*").eq("email", email).execute()
    if not user.data:
        return None
    user_id = user.data[0]['id']

    customer = supabase.table("customers").select("*").eq("user_id", user_id).execute()
    if not customer.data:
        return None
    return customer.data[0]

def save_customer_data(news_email, email, companies, frequency, send_hour_start, send_hour_end):
    user = supabase.table("users").select("*").eq("email", email).execute()
    if not user.data:
        # Create user if doesn't exist (shouldn't happen as save_user is called first)
        supabase.table("users").insert({
            "email": email,
            "news_email": news_email
        }).execute()
        user = supabase.table("users").select("*").eq("email", email).execute()

    user_id = user.data[0]['id']

    # Update or create customer data
    customer = supabase.table("customers").select("*").eq("user_id", user_id).execute()
    if customer.data:
        supabase.table("customers").update({
            "company_names": companies,
            "frequency": frequency,
            "send_hour_start": send_hour_start,
            "send_hour_end": send_hour_end
        }).eq("user_id", user_id).execute()
    else:
        supabase.table("customers").insert({
            "user_id": user_id,
            "company_names": companies,
            "frequency": frequency,
            "send_hour_start": send_hour_start,
            "send_hour_end": send_hour_end
        }).execute()

def update_tracker(user_id, timestamp):
    """Update the email tracker with last sent time"""
    iso_time = timestamp.isoformat()
    try:
        existing = supabase.table("email_tracker").select("*").eq("user_id", user_id).execute().data
        if existing:
            supabase.table("email_tracker").update({"last_sent": iso_time}).eq("user_id", user_id).execute()
        else:
            supabase.table("email_tracker").insert({"user_id": user_id, "last_sent": iso_time}).execute()
    except Exception as e:
        print(f"⚠️ Failed to update tracker for user {user_id}: {e}")

def get_users_with_customer_data():
    """Get all users with their customer data"""
    try:
        # Using raw SQL for better performance
        query = """
            SELECT 
                u.id, u.email,
                COALESCE(c.frequency, 'week') AS frequency,
                COALESCE(c.send_hour_start, 6) AS send_hour_start,
                COALESCE(c.send_hour_end, 18) AS send_hour_end,
                COALESCE(c.company_names, '') AS company_names,
                et.last_sent
            FROM 
                users u
            LEFT JOIN 
                customers c ON u.id = c.user_id
            LEFT JOIN 
                email_tracker et ON u.id = et.user_id
            WHERE 
                c.company_names IS NOT NULL AND
                c.company_names != ''
        """
        response = supabase.rpc('query', {'query': query}).execute()
        return response.data
    except Exception as e:
        print(f"Error fetching users with customer data: {e}")
        return []
