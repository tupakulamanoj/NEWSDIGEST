from fastapi import FastAPI
from auth_router import auth_router, configure_oauth
from supabase_client import save_user, get_customer_data, save_customer_data, subscribe_user, unsubscribe_user, is_user_subscribed
from email_scheduler import start_scheduler
import logging
import os
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
app.include_router(auth_router, prefix="/auth")
configure_oauth(app)

# Configure Dramatiq with Redis
redis_url = os.getenv('REDIS_URL', 'redis://redis-service:6379')
broker = RedisBroker(url=redis_url)
broker.add_middleware(Results(backend=RedisBackend(url=redis_url)))
Broker.set_default(broker)

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
