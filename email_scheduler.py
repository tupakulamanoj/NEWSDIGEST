
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from pytz import timezone, utc
from supabase_client import supabase
from jobs import run_user_job
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
IST = timezone("Asia/Kolkata")
def check_and_send_emails():
    try:
        now_utc = datetime.utcnow().replace(tzinfo=utc)
        now_ist = now_utc.astimezone(IST)
        current_hour_ist = now_ist.hour
        current_date_ist = now_ist.date()
        
        logger.info(f"\n{'='*50}\nEmail check at {now_ist} IST (hour: {current_hour_ist})\n{'='*50}")
        
        # Fetch users with customer data
        response = supabase.table("users").select("*, customers(*)").execute()
        users = response.data
        logger.info(f"Found {len(users)} users")
        
        emails_queued = 0
        
        for user in users:
            try:
                if not user.get('customers') or not user.get('News_Email'):
                    continue
                
                customer = user['customers'][0]
                email = user['News_Email']
                user_id = user['id']
                interval = customer.get('frequency', 'week')
                
                # Check last sent email info with additional status check
                tracker = supabase.table("email_tracker").select("*").eq("user_id", user_id).execute()
                last_sent_data = tracker.data[0] if tracker.data else None
                
                should_send = False
                
                if last_sent_data is None:
                    # No entry in tracker - first time sending to this user
                    # Create a temporary tracker entry to prevent duplicates
                    temp_entry = {
                        "user_id": user_id,
                        "last_sent": now_utc.isoformat(),
                        "last_status": "queued",
                        "last_email": email
                    }
                    supabase.table("email_tracker").upsert(temp_entry).execute()
                    logger.info(f"Created temp tracker entry for {email} - sending first email")
                    should_send = True
                else:
                    # Check if email is already queued or in progress
                    if last_sent_data.get("last_status") in ["queued", "in_progress"]:
                        logger.info(f"Skipping {email} - email already queued/in progress")
                        continue
                    
                    send_hour_start = customer.get('send_hour_start', 11)
                    send_hour_end = customer.get('send_hour_end', 12)
                    
                    # Check if current IST time is within user's preferred window
                    if not (send_hour_start <= current_hour_ist < send_hour_end):
                        logger.info(f"Skipping {email} - current hour {current_hour_ist} not in window {send_hour_start}-{send_hour_end} IST")
                        continue
                    
                    last_sent_time = datetime.fromisoformat(last_sent_data["last_sent"]).replace(tzinfo=utc).astimezone(IST)
                    last_sent_date = last_sent_time.date()
                    
                    # Check if already sent today (regardless of time)
                    if last_sent_date == current_date_ist:
                        logger.info(f"Already sent to {email} today ({last_sent_date})")
                        should_send = False
                    
                    # Check interval requirement
                    elif interval > 0 and (current_date_ist - last_sent_date).days < interval:
                        logger.info(f"Interval not yet passed for {email} - last sent {last_sent_date}, interval {interval} days")
                        should_send = False
                    
                    # Safety check: prevent sending too frequently (within 5 minutes)
                    elif (now_ist - last_sent_time) < timedelta(minutes=5):
                        logger.info(f"Recently sent to {email} at {last_sent_time}, skipping for safety")
                        should_send = False
                    else:
                        should_send = True
                
                if should_send:
                    # Mark as queued before sending to prevent duplicates
                    supabase.table("email_tracker").upsert({
                        "user_id": user_id,
                        "last_sent": now_utc.isoformat(),
                        "last_status": "queued",
                        "last_email": email
                    }).execute()
                    
                    run_user_job.send(user_id, email, customer.get('company_names', ''), interval=interval)
                    logger.info(f"Queued email for {email}")
                    emails_queued += 1
                    
            except Exception as e:
                logger.error(f"Error processing user {user.get('id', '?')}: {str(e)}")
        
        logger.info(f"Total emails queued: {emails_queued}")
        
    except Exception as e:
        logger.error(f"Scheduler failure: {str(e)}")
def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        check_and_send_emails,
        trigger='interval',
        minutes=5,
        next_run_time=datetime.now()  # immediate first run
    )
    scheduler.start()
    logger.info("Email scheduler started.")