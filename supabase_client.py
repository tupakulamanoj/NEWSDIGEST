# from supabase import create_client
# import os
# from dotenv import load_dotenv
# from datetime import datetime
# import socket
# from tenacity import retry, stop_after_attempt, wait_fixed

# load_dotenv()

# @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
# def create_supabase_client():
#     url = os.getenv("SUPABASE_URL")
#     key = os.getenv("SUPABASE_KEY")
    
#     # Check if we're on Render and need to use alternative connection
#     if "render.com" in os.getenv("RENDER", ""):
#         # For Render deployment, use the pooler connection instead
#         # Replace the direct connection URL with pooler URL
#         if url and "supabase.co" in url:
#             # Extract project reference from URL
#             project_ref = url.split("//")[1].split(".")[0]
#             # Use the pooler endpoint which supports IPv4
#             pooler_url = f"https://{project_ref}.supabase.co"
#             url = pooler_url
#             print(f"Using pooler connection for Render: {url}")
    
#     return create_client(url, key)

# # Alternative approach: Use session mode connection string
# def create_supabase_client_alt():
#     """Alternative connection method using session mode"""
#     # Use the session mode connection which is IPv4 compatible
#     # Get this from your Supabase Dashboard > Settings > Database > Connection string
#     database_url = os.getenv("DATABASE_URL")  # Add this to your .env
#     supabase_url = os.getenv("SUPABASE_URL")
#     supabase_key = os.getenv("SUPABASE_KEY")
    
#     if database_url and "render.com" in os.getenv("RENDER", ""):
#         # If you have a session mode database URL, you can use it for direct DB operations
#         # But for Supabase client, still use the regular URL
#         print(f"Session mode DB URL available: {database_url[:50]}...")
    
#     return create_client(supabase_url, supabase_key)

# # Initialize the client
# supabase = create_supabase_client()

# # Optional: Test connection function (call this when needed, not at module level)
# def test_connection():
#     try:
#         result = supabase.table("users").select("*").limit(1).execute()
#         print("✅ Connection test successful")
#         return True
#     except Exception as e:
#         print(f"❌ Connection test failed: {e}")
#         return False

# def save_user(email, name, news_email):
#     # Check if user exists
#     user = supabase.table("users").select("*").eq("email", email).execute()
    
#     if not user.data:
#         # Create new user with both email and news_email
#         supabase.table("users").insert({
#             "email": email,
#             "name": name,
#             "News_Email": news_email
#         }).execute()
#     else:
#         # Update existing user's news_email
#         supabase.table("users").update({
#             "News_Email": news_email,
#             "name": name
#         }).eq("email", email).execute()

# def subscribe_user(email, name, news_email, companies, frequency, send_hour_start, send_hour_end):
#     try:
#         # First ensure user exists
#         save_user(email, name, news_email)
        
#         # Get user ID
#         user = supabase.table("users").select("*").eq("email", email).execute()
#         user_id = user.data[0]['id']
        
#         # Save customer data
#         save_customer_data(news_email, email, companies, frequency, send_hour_start, send_hour_end)
        
#         return True
#     except Exception as e:
#         print(f"Error subscribing user: {e}")
#         return False

# def unsubscribe_user(email):
#     try:
#         # Get user ID
#         user = supabase.table("users").select("*").eq("email", email).execute()
#         if not user.data:
#             return True  # User doesn't exist, nothing to do
        
#         user_id = user.data[0]['id']
        
#         # Delete from customers table
#         supabase.table("customers").delete().eq("user_id", user_id).execute()
        
#         # Delete from email_tracker table
#         supabase.table("email_tracker").delete().eq("user_id", user_id).execute()
        
#         return True
#     except Exception as e:
#         print(f"Error unsubscribing user: {e}")
#         return False

# def is_user_subscribed(email):
#     try:
#         user = supabase.table("users").select("*").eq("email", email).execute()
#         if not user.data:
#             return False
            
#         user_id = user.data[0]['id']
        
#         customer = supabase.table("customers").select("*").eq("user_id", user_id).execute()
#         return bool(customer.data)
#     except Exception as e:
#         print(f"Error checking subscription status: {e}")
#         return False

# def get_customer_data(email):
#     user = supabase.table("users").select("*").eq("email", email).execute()
#     if not user.data:
#         return None
#     user_id = user.data[0]['id']

#     customer = supabase.table("customers").select("*").eq("user_id", user_id).execute()
#     if not customer.data:
#         return None
#     return customer.data[0]

# def save_customer_data(news_email, email, companies, frequency, send_hour_start, send_hour_end):
#     user = supabase.table("users").select("*").eq("email", email).execute()
#     if not user.data:
#         # Create user if doesn't exist (shouldn't happen as save_user is called first)
#         supabase.table("users").insert({
#             "email": email,
#             "news_email": news_email
#         }).execute()
#         user = supabase.table("users").select("*").eq("email", email).execute()

#     user_id = user.data[0]['id']

#     # Update or create customer data
#     customer = supabase.table("customers").select("*").eq("user_id", user_id).execute()
#     if customer.data:
#         supabase.table("customers").update({
#             "company_names": companies,
#             "frequency": frequency,
#             "send_hour_start": send_hour_start,
#             "send_hour_end": send_hour_end
#         }).eq("user_id", user_id).execute()
#     else:
#         supabase.table("customers").insert({
#             "user_id": user_id,
#             "company_names": companies,
#             "frequency": frequency,
#             "send_hour_start": send_hour_start,
#             "send_hour_end": send_hour_end
#         }).execute()

# def update_tracker(user_id, timestamp):
#     """Update the email tracker with last sent time"""
#     iso_time = timestamp.isoformat()
#     try:
#         existing = supabase.table("email_tracker").select("*").eq("user_id", user_id).execute().data
#         if existing:
#             supabase.table("email_tracker").update({"last_sent": iso_time}).eq("user_id", user_id).execute()
#         else:
#             supabase.table("email_tracker").insert({"user_id": user_id, "last_sent": iso_time}).execute()
#     except Exception as e:
#         print(f"⚠️ Failed to update tracker for user {user_id}: {e}")

# def get_users_with_customer_data():
#     """Get all users with their customer data"""
#     try:
#         # Use regular table queries instead of raw SQL for better compatibility
#         users_response = supabase.table("users").select(
#             "id, email, customers(frequency, send_hour_start, send_hour_end, company_names), email_tracker(last_sent)"
#         ).not_.is_("customers.company_names", "null").execute()
        
#         # Transform the data to match expected format
#         users_data = []
#         for user in users_response.data:
#             if user.get('customers') and user['customers'][0].get('company_names'):
#                 customer = user['customers'][0]
#                 tracker = user.get('email_tracker', [{}])[0] if user.get('email_tracker') else {}
                
#                 users_data.append({
#                     'id': user['id'],
#                     'email': user['email'],
#                     'frequency': customer.get('frequency', 'week'),
#                     'send_hour_start': customer.get('send_hour_start', 6),
#                     'send_hour_end': customer.get('send_hour_end', 18),
#                     'company_names': customer.get('company_names', ''),
#                     'last_sent': tracker.get('last_sent')
#                 })
        
#         return users_data
#     except Exception as e:
#         print(f"Error fetching users with customer data: {e}")
#         return []
from supabase import create_client
import os
from dotenv import load_dotenv
from datetime import datetime
import socket
from tenacity import retry, stop_after_attempt, wait_fixed

load_dotenv()

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def create_supabase_client():
    # Use the direct PostgreSQL connection string for database operations
    database_url = os.getenv("DATABASE_URL")
    
    # For Supabase client, we still need the regular URL and key
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    print(f"SUPABASE_URL: {SUPABASE_URL}")
    print(f"SUPABASE_KEY: {'set' if SUPABASE_KEY else 'missing'}")

    if not supabase_url or not supabase_key:
        raise ValueError("Supabase URL and Key must be provided in environment variables")
    
    return create_client(supabase_url, supabase_key)

# Initialize the client
supabase = create_supabase_client()

# Optional: Test connection function (call this when needed, not at module level)
def test_connection():
    try:
        result = supabase.table("users").select("*").limit(1).execute()
        print("✅ Connection test successful")
        return True
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False

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
        # Use regular table queries instead of raw SQL for better compatibility
        users_response = supabase.table("users").select(
            "id, email, customers(frequency, send_hour_start, send_hour_end, company_names), email_tracker(last_sent)"
        ).not_.is_("customers.company_names", "null").execute()
        
        # Transform the data to match expected format
        users_data = []
        for user in users_response.data:
            if user.get('customers') and user['customers'][0].get('company_names'):
                customer = user['customers'][0]
                tracker = user.get('email_tracker', [{}])[0] if user.get('email_tracker') else {}
                
                users_data.append({
                    'id': user['id'],
                    'email': user['email'],
                    'frequency': customer.get('frequency', 'week'),
                    'send_hour_start': customer.get('send_hour_start', 6),
                    'send_hour_end': customer.get('send_hour_end', 18),
                    'company_names': customer.get('company_names', ''),
                    'last_sent': tracker.get('last_sent')
                })
        
        return users_data
    except Exception as e:
        print(f"Error fetching users with customer data: {e}")
        return []
