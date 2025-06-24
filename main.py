from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from auth_router import auth_router, configure_oauth
from supabase_client import save_user, get_customer_data, save_customer_data, subscribe_user, unsubscribe_user, is_user_subscribed
from email_scheduler import start_scheduler
from dramatiq import Broker, Middleware
from dramatiq.brokers.redis import RedisBroker
from dramatiq.results import Results
from dramatiq.results.backends import RedisBackend
import logging
import os
from dotenv import load_dotenv

from starlette.middleware.sessions import SessionMiddleware
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI()
app.include_router(auth_router, prefix="/auth")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET_KEY", os.urandom(32).hex()),
    session_cookie="session_cookie",
    https_only=True,  # Requires HTTPS
    same_site="lax",  # CSRF protection
    max_age=3600,     # 1 hour expiration
)
configure_oauth(app)

from dramatiq.brokers.redis import RedisBroker
from dramatiq.results import Results
from dramatiq.results.backends import RedisBackend
import dramatiq


redis_url = os.getenv('REDIS_URL')
broker = RedisBroker(url=redis_url)
broker.add_middleware(Results(backend=RedisBackend(url=redis_url)))
dramatiq.set_broker(broker)

# Start scheduler
def start_app():
    start_scheduler()
    logger.info("Application started and scheduler initialized")

@app.on_event("startup")
async def startup_event():
    start_app()

templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/subscription")
async def handle_subscription(request: Request):
    if 'email' not in request.session:
        return JSONResponse(
            {'success': False, 'message': 'Not authenticated'}, 
            status_code=401
        )

    try:
        data = await request.json()
        email = request.session['email']
        name = request.session.get('name', '')
        
        if data.get('subscribe'):
            companies = data.get('companies', '').strip()
            if not companies:
                return JSONResponse(
                    {'success': False, 'message': 'Please enter at least one company'}, 
                    status_code=400
                )
                
            try:
                frequency = data.get('frequency', 'week')
                send_hour_start = int(data.get('send_hour_start', 6))
                send_hour_end = int(data.get('send_hour_end', 18))
            except (TypeError, ValueError):
                return JSONResponse(
                    {'success': False, 'message': 'Invalid values provided'}, 
                    status_code=400
                )

            success = subscribe_user(
                email=email,
                name=name,
                news_email=data.get('news_email', email),
                companies=companies,
                frequency=frequency,
                send_hour_start=send_hour_start,
                send_hour_end=send_hour_end
            )
            message = 'Subscribed successfully!' if success else 'Failed to subscribe'
        else:
            success = unsubscribe_user(email)
            message = 'Unsubscribed successfully!' if success else 'Failed to unsubscribe'
            
        return {'success': success, 'message': message}
    except Exception as e:
        logger.error(f"Error in subscription route: {str(e)}")
        return JSONResponse(
            {'success': False, 'message': 'An error occurred'}, 
            status_code=500
        )
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    if 'email' not in request.session:
        return RedirectResponse(url='/')

    try:
        is_subscribed = is_user_subscribed(request.session['email'])
        customer_data = get_customer_data(request.session['email']) if is_subscribed else None
        
        defaults = {
            'companies': '',  # Changed from 'company_names' to match template
            'frequency': 'week',
            'send_hour_start': 6,
            'send_hour_end': 18,
            'submit_url': request.url_for('submit'),
            'news_email': request.session.get('email', '')
        }
        
        if customer_data:
            defaults.update({
                'companies': customer_data.get('companies', ''),  # Changed key to match template
                'frequency': customer_data.get('frequency', 'week'),
                'send_hour_start': customer_data.get('send_hour_start', 6),
                'send_hour_end': customer_data.get('send_hour_end', 18),
                'news_email': customer_data.get('news_email', request.session.get('email', ''))
            })
            
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "name": request.session.get('name', ''),
                "email": request.session.get('email', ''),
                "news_email": defaults['news_email'],
                "companies": defaults['companies'],  # Pass empty string or user's companies
                "frequency": defaults['frequency'],
                "send_hour_start": defaults['send_hour_start'],
                "send_hour_end": defaults['send_hour_end'],
                "is_subscribed": is_subscribed,
                "url_for_submit": defaults['submit_url']
            }
        )
    except Exception as e:
        logger.error(f"Error in dashboard route: {str(e)}")
        return templates.TemplateResponse(
            "error.html", 
            {"request": request, "message": "An error occurred while loading the dashboard"}
        )
@app.post("/submit")
async def submit(request: Request):
    if 'email' not in request.session:
        return JSONResponse(
            {'success': False, 'message': 'Not authenticated'}, 
            status_code=401
        )

    try:
        form_data = await request.form()
        email = request.session['email']
        name = request.session.get('name', '')
        news_email = form_data.get('news_email', email)
        companies = form_data.get('companies', '')
        frequency = form_data.get('frequency', 'week')
        send_hour_start = int(form_data.get('send_hour_start', 6))
        send_hour_end = int(form_data.get('send_hour_end', 18))

        save_user(email, name, news_email)
        save_customer_data(news_email, email, companies, frequency, send_hour_start, send_hour_end)
        
        return JSONResponse({
            'success': True,
            'message': 'Preferences saved successfully!',
            'redirect': '/dashboard'
        })
    except Exception as e:
        logger.error(f"Error in submit route: {str(e)}")
        return JSONResponse(
            {'success': False, 'message': 'An error occurred while saving your data'}, 
            status_code=500
        )

# Add health check endpoint for Render
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    if os.getenv("RUN_SCHEDULER") == "true":
        start_scheduler()
    
    # Get port from environment or default to 5000 for local development
    port = int(os.getenv("PORT", 5000))
    
    # Start the FastAPI app
    uvicorn.run(app, host="0.0.0.0", port=port)
