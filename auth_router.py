


from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from starlette.middleware.sessions import SessionMiddleware
import os
import uuid

auth_router = APIRouter()
oauth = OAuth()

def configure_oauth(app):
    config = Config('.env')  # Load environment variables
    oauth.register(
        name='google',
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )
    app.add_middleware(SessionMiddleware, secret_key=os.getenv('FLASK_SECRET_KEY', 'supersecret'))

@auth_router.get('/login')
async def login(request: Request):
    # Debug: Print the redirect URI
    redirect_uri = str(request.url_for('auth_callback'))
    print(f"Redirect URI: {redirect_uri}")
    
    # Ensure the redirect URI matches exactly what's registered in Google Cloud Console
    nonce = uuid.uuid4().hex
    request.session['nonce'] = nonce
    
    # Add state parameter for additional security
    state = uuid.uuid4().hex
    request.session['oauth_state'] = state
    
    print(f"Starting OAuth flow with nonce: {nonce[:8]}... and state: {state[:8]}...")
    
    return await oauth.google.authorize_redirect(
        request, 
        redirect_uri, 
        nonce=nonce,
        state=state
    )

@auth_router.get('/auth/callback')
async def auth_callback(request: Request):
    try:
        # Debug: Print the callback URL and parameters
        print(f"Callback URL: {request.url}")
        print(f"Query params: {dict(request.query_params)}")
        
        # Validate state parameter
        received_state = request.query_params.get('state')
        session_state = request.session.pop('oauth_state', None)
        if received_state != session_state:
            print(f"State mismatch: received {received_state}, expected {session_state}")
            raise HTTPException(status_code=400, detail="Invalid state parameter")
        
        # Check if there's an error in the callback
        if 'error' in request.query_params:
            error = request.query_params.get('error')
            error_description = request.query_params.get('error_description', '')
            print(f"OAuth error: {error} - {error_description}")
            raise HTTPException(status_code=400, detail=f"OAuth error: {error} - {error_description}")
        
        # Get the access token
        token = await oauth.google.authorize_access_token(request)
        print(f"Token received: {bool(token)}")
        
        # Clean up nonce from session
        nonce = request.session.pop('nonce', None)
        
        # Get user info from the token
        user_info = token.get('userinfo')
        if not user_info:
            # If userinfo is not in token, try to parse the ID token
            try:
                user_info = await oauth.google.parse_id_token(request, token)
                print("User info from ID token")
            except Exception as parse_error:
                print(f"Error parsing ID token: {parse_error}")
                # Fallback: make a request to userinfo endpoint
                resp = await oauth.google.get('https://www.googleapis.com/oauth2/v2/userinfo', token=token)
                user_info = resp.json()
                print("User info from userinfo endpoint")
        
        print(f"User info: {user_info}")
        
        # Check if email is verified
        if not user_info.get('email_verified') and not user_info.get('verified_email'):
            raise HTTPException(status_code=400, detail="Email not verified by Google")
            
        # Store user info in session
        request.session['email'] = user_info['email']
        request.session['name'] = user_info.get('name')
        request.session['user_id'] = user_info.get('id')
        
        print(f"User authenticated: {user_info['email']}")
        return RedirectResponse(url=request.url_for('dashboard'))
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected error in auth callback: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"Authentication failed: {str(e)}")
