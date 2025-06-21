from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
import os
import uuid
import logging
from urllib.parse import urlencode
from supabase_client import get_customer_data

auth_router = APIRouter()
oauth = OAuth()
logger = logging.getLogger(__name__)

def configure_oauth(app):
    config = Config('.env')
    oauth.register(
        name='google',
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile',
            'prompt': 'select_account'  # Ensures users select account each time
        }
    )

@auth_router.get('/login')
async def login(request: Request):
    try:
        redirect_uri = str(request.url_for('auth_callback'))
        logger.info(f"Redirect URI: {redirect_uri}")
        
        # Generate secure state and nonce
        state = uuid.uuid4().hex
        nonce = uuid.uuid4().hex
        
        # Store in session with expiration
        request.session.update({
            'oauth_state': state,
            'nonce': nonce,
            'redirect_after_auth': str(request.query_params.get('next', '/'))
        })
        
        # Additional parameters for security
        auth_params = {
            'access_type': 'offline',
            'include_granted_scopes': 'true',
            'response_type': 'code',
            'state': state,
            'nonce': nonce
        }
        
        authorization_url = await oauth.google.authorize_redirect(
            request, 
            redirect_uri,
            **auth_params
        )
        
        return authorization_url
        
    except Exception as e:
        logger.error(f"Login initialization failed: {e}")
        raise HTTPException(500, "Login initialization failed")

@auth_router.get('/auth/callback')
async def auth_callback(request: Request):
    try:
        # Verify state parameter first
        received_state = request.query_params.get('state')
        session_state = request.session.pop('oauth_state', None)
        
        if not received_state or received_state != session_state:
            logger.error(f"State mismatch: received {received_state}, expected {session_state}")
            raise HTTPException(400, "Invalid state parameter")
        
        # Check for OAuth errors
        if 'error' in request.query_params:
            error = request.query_params.get('error')
            error_desc = request.query_params.get('error_description', 'No description')
            logger.error(f"OAuth error: {error} - {error_desc}")
            raise HTTPException(400, f"OAuth error: {error}")
        
        # Exchange code for token
        token = await oauth.google.authorize_access_token(request)
        if not token:
            raise HTTPException(400, "Failed to obtain access token")
            
        logger.info("Token received successfully")
        
        # Verify nonce
        nonce = request.session.pop('nonce', None)
        id_token = token.get('id_token')
        if id_token and nonce:
            try:
                claims = await oauth.google.parse_id_token(request, token, nonce=nonce)
            except Exception as e:
                logger.error(f"ID token validation failed: {e}")
                raise HTTPException(400, "Invalid ID token")
        
        # Get user info
        userinfo = token.get('userinfo')
        if not userinfo:
            # Fallback to userinfo endpoint
            resp = await oauth.google.get('https://www.googleapis.com/oauth2/v3/userinfo', token=token)
            userinfo = resp.json()
        
        if not userinfo.get('email_verified', False):
            raise HTTPException(400, "Email not verified by provider")
        
        # Store user session
        request.session.update({
            'user': {
                'id': userinfo.get('sub'),
                'email': userinfo.get('email'),
                'name': userinfo.get('name'),
                'picture': userinfo.get('picture')
            },
            'authenticated': True
        })
        
        # Get customer data if exists
        try:
            customer_data = get_customer_data(userinfo['email'])
            if customer_data:
                request.session['customer_data'] = customer_data
        except Exception as e:
            logger.error(f"Failed to fetch customer data: {e}")
            # Continue without customer data
        
        # Redirect to original destination or dashboard
        redirect_url = request.session.pop('redirect_after_auth', '/dashboard')
        return RedirectResponse(url=redirect_url)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication failed: {e}", exc_info=True)
        raise HTTPException(500, "Authentication process failed")
