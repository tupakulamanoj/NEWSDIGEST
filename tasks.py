import os
from dramatiq import actor
from email_scheduler import send_newsletter
from supabase_client import get_customer_data
import logging

logger = logging.getLogger(__name__)

@actor
async def send_newsletter_task(email: str):
    """Send newsletter to a specific email address."""
    try:
        customer_data = get_customer_data(email)
        if customer_data:
            await send_newsletter(
                email=email,
                companies=customer_data.get('companies', ''),
                frequency=customer_data.get('frequency', 'week'),
                send_hour_start=customer_data.get('send_hour_start', 6),
                send_hour_end=customer_data.get('send_hour_end', 18)
            )
            logger.info(f"Newsletter sent successfully to {email}")
        else:
            logger.warning(f"No customer data found for {email}")
    except Exception as e:
        logger.error(f"Error sending newsletter to {email}: {str(e)}")
