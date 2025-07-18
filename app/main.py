# app/main.py

import os
import json
import uuid
import random
import traceback

from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form, Depends, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import httpx
from app.services.github_listener import GitHubListener
from app.services.analyzer import ProjectAnalyzer
from app.services.scoring import ScoringEngine
from app.services.cv_writer import CVWriter
from app.services.cv_parser import CVParser
from docx2pdf import convert as docx_to_pdf_convert
from dotenv import load_dotenv

# Kage: The initial read of the environment. Foundation for operations.
load_dotenv()

# Kage: Confirming the presence of vital components. Silence is not always absence.
print(f"[Kage] Gemini API state: {'(absent)' if not os.getenv('GEMINI_API') else 'present'}")

# Firebase Imports - The anchor to data persistence.
import firebase_admin
from firebase_admin import credentials, firestore, auth
from firebase_admin.exceptions import FirebaseError

# Decoding tokens. A necessary step for trust.
import jwt

# Communication channel for validation.
import smtplib
from email.mime.text import MIMEText
from email.header import Header

# Shaping URLs. Precision in redirection.
from urllib.parse import quote_plus


app = FastAPI()

# Kage: Static assets mounted. The visible form of the application.
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")

# Kage: Templates prepared. The structure for visual output.
templates = Jinja2Templates(directory="app/web/templates")

# Kage: GitHub interface parameters. Defined boundaries.
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "YOUR_GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "YOUR_GITHUB_CLIENT_SECRET")
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_API = "https://api.github.com/user"
GITHUB_USER_EMAILS_API = "https://api.github.com/user/emails"
GITHUB_SCOPES = "user:email,repo"
FIREBASE_GITHUB_AUTH_HANDLER = f"https://{os.getenv('__app_id')}.firebaseapp.com/__/auth/handler"

# Kage: Email transmission parameters. For vital communications.
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.example.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "your_email@example.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "your_email_password")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "no-reply@kaku-ryu.com")

# Kage: Global data structures. The persistent memory.
db = None
user_cv_data_template = {
    "name": "Guest User",
    "email": "guest@example.com",
    "phone": "N/A",
    "linkedin": "N/A",
    "github_profile": "N/A",
    "professional_summary": "Welcome. Present your true form by uploading your CV.",
    "user_defined_skills": [],
    "user_defined_technologies": [],
    "languages": [],
    "work_experience": [],
    "github_token_encrypted": None,
    "github_oauth_token_encrypted": None,
    "github_user_id": None,
    "email_verified": False,
    "verification_code": None
}

# Kage: Output directory for generated forms. A defined destination.
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Kage: Core tools, dormant until activated.
github_listener = None
project_analyzer = None
scoring_engine = None
cv_writer = None
cv_parser = None

# Kage: Token scheme. A conceptual layer for access control.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Kage: Firebase integration. The link to the persistent realm.
app_id = os.getenv('__app_id')
firebase_config_str = os.getenv('__firebase_config')
initial_auth_token = os.getenv('__initial_auth_token')

raw_frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:8000')
FRONTEND_URL = raw_frontend_url.split('#')[0].strip().strip('"\'')

# Kage: Initializing Firebase. The first breath of the data connection.
if not firebase_admin._apps:
    try:
        if firebase_config_str:
            processed_firebase_config_str = firebase_config_str.replace('\n', '\\n')
            firebase_config = json.loads(processed_firebase_config_str)
            if "private_key" in firebase_config and isinstance(firebase_config["private_key"], str):
                firebase_config["private_key"] = firebase_config["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(firebase_config)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            print("[Kage] Firebase initialized. The data path is open.")
        else:
            print("[Kage] Firebase configuration absent. Data persistence remains dormant.")
    except json.JSONDecodeError as e:
        print(f"[Kage] Firebase config: JSON corrupted. Error: {e}")
        db = None
    except Exception as e:
        print(f"[Kage] Firebase initialization failed: {e}. Path remains unclear.")
        db = None

# Kage: Current status of the data connection. A silent affirmation.
print(f"[Kage] Data persistence status: {'Active' if db else 'Inactive'}")

# Kage: Dependency for user identification. The first gate.
async def get_current_user_id(request: Request) -> str:
    """
    Kage: Identifies the user. Prioritizes direct token, then header.
    Rejects without a clear path.
    """
    id_token_from_url = request.query_params.get('id_token')
    if id_token_from_url:
        try:
            decoded_payload = jwt.decode(id_token_from_url, options={"verify_signature": False, "verify_aud": False, "verify_exp": False, "verify_nbf": False, "verify_iat": False})
            user_id = decoded_payload.get('uid')
            if user_id:
                return user_id
        except (jwt.exceptions.DecodeError, Exception):
            pass # Kage: Silence failures, move to next.

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        id_token_from_header = auth_header.split(" ")[1]
        try:
            decoded_token = auth.verify_id_token(id_token_from_header)
            return decoded_token['uid']
        except (FirebaseError, Exception):
            pass # Kage: Silence failures, move to next.
    
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized. No valid path found.")

# Kage: Startup sequence. Activating the tools.
@app.on_event("startup")
async def startup_event():
    global github_listener, project_analyzer, scoring_engine, cv_writer, cv_parser, db

    # Kage: Initial user authentication. The first step on the path.
    if initial_auth_token:
        try:
            if db:
                decoded_token = auth.verify_id_token(initial_auth_token)
                app.state.initial_canvas_user_id = decoded_token['uid']
                print(f"[Kage] Primary user authenticated: {app.state.initial_canvas_user_id}.")
            else:
                print("[Kage] Firebase inactive. Cannot verify initial user token. Proceeding as ephemeral.")
                app.state.initial_canvas_user_id = str(uuid.uuid4())
        except FirebaseError:
            print("[Kage] Initial token invalid. Proceeding as ephemeral.")
            app.state.initial_canvas_user_id = str(uuid.uuid4())
    else:
        app.state.initial_canvas_user_id = str(uuid.uuid4())
        print(f"[Kage] No initial token. Operating as ephemeral entity: {app.state.initial_canvas_user_id}.")

    # Kage: Tool activation sequence.
    try:
        github_listener = GitHubListener()
        print("[Kage] GitHub Listener: Active.")
    except Exception as e:
        print(f"[Kage] GitHub Listener: Failure. {e}")

    try:
        gemini_api_key = os.getenv("GEMINI_API")
        if not gemini_api_key:
            print("[Kage] GEMINI_API environment variable not set. Project Analyzer and CV Parser will be dormant.")
            project_analyzer = None
            cv_parser = None
        else:
            project_analyzer = ProjectAnalyzer(model_name="gemini-2.0-flash", api_key=gemini_api_key)
            print("[Kage] Project Analyzer: Active.")
            cv_parser = CVParser(model_name="gemini-2.0-flash", api_key=gemini_api_key)
            print("[Kage] CV Parser: Active.")
    except Exception as e:
        print(f"[Kage] LLM tool activation failed: {e}")
        project_analyzer = None
        cv_parser = None

    try:
        scoring_engine = ScoringEngine()
        print("[Kage] Scoring Engine: Active.")
    except Exception as e:
        print(f"[Kage] Scoring Engine: Failure. {e}")

    try:
        cv_writer = CVWriter(output_dir=OUTPUT_DIR)
        print("[Kage] CV Writer: Active.")
    except Exception as e:
        print(f"[Kage] CV Writer: Failure. {e}")


# Kage: Data retrieval from the persistent realm.
async def get_user_cv_data_from_firestore(user_id: str):
    """
    Kage: Retrieves user profile. If absent, a default form is manifested.
    """
    global db
    if not db or not app_id:
        return user_cv_data_template.copy()

    try:
        user_doc_ref = db.collection('artifacts').document(app_id).collection('users').document(user_id).collection('cv_data').document('profile')
        user_doc = user_doc_ref.get()
        if user_doc.exists:
            loaded_data = user_doc.to_dict()
            for key, default_value in user_cv_data_template.items():
                if key not in loaded_data:
                    loaded_data[key] = default_value
            return loaded_data
        else:
            user_doc_ref.set(user_cv_data_template)
            return user_cv_data_template.copy()
    except Exception as e:
        print(f"[Kage] Data retrieval failed for {user_id}: {e}")
        traceback.print_exc()
        return user_cv_data_template.copy()

# Kage: Email communication. A channel for validation.
def send_verification_email(recipient_email: str, verification_code: str):
    """
    Kage: Dispatches the verification code. Errors indicate a blocked path.
    """
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT")) if os.getenv("SMTP_PORT") else 587
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender_email = os.getenv("SENDER_EMAIL")

    if not all([smtp_server, smtp_username, smtp_password, sender_email]):
        raise ValueError("Email path incomplete. SMTP credentials missing.")

    subject = "Kaku-Ryu: Path Verification Code"
    body = f"""
    Kaku-Ryu Disciple,

    Your path requires verification. Your code: {verification_code}

    Enter this code to solidify your presence.

    If this request is not your action, disregard this message.

    Kage.
    """

    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = sender_email
    msg['To'] = recipient_email
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        print(f"[Kage] Verification sent to {recipient_email}.")
    except (smtplib.SMTPAuthenticationError, smtplib.SMTPConnectError, Exception) as e:
        print(f"[Kage] Email transmission failed to {recipient_email}: {e}")
        raise ConnectionError(f"Email path obstructed: {e}")

# Kage: Public facing portals. The points of entry.
@app.get("/login_page", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/register_page", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/verify_page", response_class=HTMLResponse)
async def verify_page(request: Request):
    return templates.TemplateResponse("verify.html", {"request": request})

@app.post("/signup")
async def signup(username: str = Form(...), email: str = Form(...), password: str = Form(...)):
    global db
    if not db or not app_id:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="System foundation not set.")
    
    try:
        user = auth.create_user(email=email, password=password, display_name=username)
        verification_code = str(random.randint(100000, 999999))
        
        user_doc_ref = db.collection('artifacts').document(app_id).collection('users').document(user.uid).collection('cv_data').document('profile')
        initial_user_data = {
            **user_cv_data_template,
            "email": email,
            "name": username,
            "email_verified": False,
            "verification_code": verification_code
        }
        user_doc_ref.set(initial_user_data)
        
        email_sent_successfully = True
        email_error_message = None
        try:
            send_verification_email(email, verification_code)
        except Exception as email_err:
            email_sent_successfully = False
            email_error_message = f"Email path obstructed: {email_err}. Resend code if needed."

        redirect_url = f"/verify_page?email={quote_plus(email)}"
        if not email_sent_successfully:
            redirect_url += f"&message={quote_plus(email_error_message)}&type=error"

        return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    except FirebaseError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Firebase impediment: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Entry failed: {e}")

@app.post("/verify-email")
async def verify_email(email: str = Form(...), code: str = Form(...)):
    global db
    if not db or not app_id:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="System foundation not set.")
    
    try:
        user = auth.get_user_by_email(email)
        user_id = user.uid

        user_doc_ref = db.collection('artifacts').document(app_id).collection('users').document(user_id).collection('cv_data').document('profile')
        user_doc = user_doc_ref.get()
        
        if not user_doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User data not found.")
        
        stored_data = user_doc.to_dict()
        email_already_verified = stored_data.get("email_verified", False)

        if email_already_verified:
            return JSONResponse(content={"message": "Path already verified."})

        if stored_data.get("verification_code") == code:
            user_doc_ref.update({"email_verified": True, "verification_code": firestore.DELETE_FIELD})
            print(f"[Kage] Email {email} path verified.")
            return JSONResponse(content={"message": "Path verified. Proceed to login."})
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code invalid.")

    except auth.UserNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    except FirebaseError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Firebase impediment: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Verification failed: {e}")

@app.post("/resend-verification-code")
async def resend_verification_code(email: str = Form(...)):
    global db
    if not db or not app_id:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="System foundation not set.")

    try:
        user = auth.get_user_by_email(email)
        user_id = user.uid

        user_doc_ref = db.collection('artifacts').document(app_id).collection('users').document(user_id).collection('cv_data').document('profile')
        user_doc = user_doc_ref.get()

        if not user_doc.exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User data not found.")
        
        stored_data = user_doc.to_dict()
        email_already_verified = stored_data.get("email_verified", False)

        if email_already_verified:
            return JSONResponse(content={"message": "Path already verified. Proceed to login."})

        verification_code = stored_data.get("verification_code")
        if not verification_code:
            verification_code = str(random.randint(100000, 999999))
            user_doc_ref.update({"verification_code": verification_code})

        send_verification_email(email, verification_code)
        return JSONResponse(content={"message": "Verification code dispatched. Observe your inbox."})

    except auth.UserNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    except ConnectionError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Email path obstructed: {e}")
    except FirebaseError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Firebase impediment: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Resend failed: {e}")

@app.post("/login")
async def login(email: str = Form(...), password: str = Form(...)):
    global db
    if not db:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="System foundation not set.")
    
    try:
        user = auth.get_user_by_email(email)
        user_id = user.uid

        user_data = await get_user_cv_data_from_firestore(user_id)
        if not user_data.get("email_verified"):
            return RedirectResponse(url=f"/verify_page?email={quote_plus(email)}&message={quote_plus('Path not verified. Complete verification first.')}&type=error", status_code=status.HTTP_302_FOUND)

        custom_token = auth.create_custom_token(user.uid)
        
        return JSONResponse(content={"message": "Login successful. Path clear.", "id_token": custom_token.decode('utf-8')})
    except auth.UserNotFoundError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid credentials.")
    except FirebaseError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Firebase impediment: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Login failed: {e}")

@app.get("/github_login")
async def github_login():
    """
    Kage: Initiates the GitHub connection. Redirects to external authorization.
    """
    state = str(uuid.uuid4())
    redirect_uri_for_github = f"{FRONTEND_URL}/github_callback"

    authorize_url = (
        f"{GITHUB_AUTHORIZE_URL}?"
        f"client_id={GITHUB_CLIENT_ID}&"
        f"redirect_uri={redirect_uri_for_github}&"
        f"scope={GITHUB_SCOPES}&"
        f"state={state}"
    )
    return RedirectResponse(authorize_url)

@app.get("/github_callback")
async def github_callback(request: Request, code: str, state: str | None = None):
    """
    Kage: Processes the GitHub response. Establishes the user's connection.
    """
    global db
    if GITHUB_CLIENT_ID == "YOUR_GITHUB_CLIENT_ID" or GITHUB_CLIENT_SECRET == "YOUR_GITHUB_CLIENT_SECRET":
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="GitHub path parameters undefined.")
    if not db:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="System foundation not set.")

    try:
        async with httpx.AsyncClient() as client:
            redirect_uri_for_token_exchange = f"{FRONTEND_URL}/github_callback"

            token_response = await client.post(
                GITHUB_TOKEN_URL,
                headers={"Accept": "application/json"},
                data={
                    "client_id": GITHUB_CLIENT_ID,
                    "client_secret": GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": redirect_uri_for_token_exchange
                }
            )
            token_data = token_response.json()
            github_access_token = token_data.get("access_token")

            if not github_access_token:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="GitHub access denied.")

            user_info_response = await client.get(
                GITHUB_USER_API,
                headers={"Authorization": f"token {github_access_token}"}
            )
            user_info_response.raise_for_status()
            github_user_info = user_info_response.json()
            github_id = str(github_user_info.get("id"))
            github_username = github_user_info.get("login")
            github_profile_url = github_user_info.get("html_url")
            
            emails_response = await client.get(
                GITHUB_USER_EMAILS_API,
                headers={"Authorization": f"token {github_access_token}"}
            )
            emails_response.raise_for_status()
            emails_data = emails_response.json()
            primary_email = next((email['email'] for email in emails_data if email['primary'] and email['verified']), None)

            if not primary_email:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Primary verified email from GitHub elusive.")

            try:
                firebase_user = auth.get_user_by_email(primary_email)
                user_uid = firebase_user.uid
            except auth.UserNotFoundError:
                firebase_user = auth.create_user(
                    email=primary_email,
                    display_name=github_username,
                    email_verified=True
                )
                user_uid = firebase_user.uid

            firebase_custom_token = auth.create_custom_token(user_uid)

            user_doc_ref = db.collection('artifacts').document(app_id).collection('users').document(user_uid).collection('cv_data').document('profile')
            existing_user_data = await get_user_cv_data_from_firestore(user_uid)
            
            updated_user_data = {
                **existing_user_data,
                "email": primary_email,
                "name": github_username or existing_user_data.get("name", "N/A"),
                "email_verified": True,
                "github_oauth_token_encrypted": github_access_token, # TODO: Encryption needed for security.
                "github_user_id": github_id,
                "github_profile": github_profile_url or existing_user_data.get("github_profile", "N/A"),
                "verification_code": firestore.DELETE_FIELD
            }
            user_doc_ref.set(updated_user_data, merge=True)
            print(f"[Kage] GitHub path integrated for {user_uid}.")

            redirect_url = (
                f"{FRONTEND_URL}/?"
                f"id_token={firebase_custom_token.decode('utf-8')}&"
                f"message=GitHub%20connection%20established.&type=success"
            )
            return RedirectResponse(redirect_url, status_code=status.HTTP_302_FOUND)

    except httpx.RequestError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"External network obstruction: {e}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"GitHub API impedance: {e.response.text}")
    except FirebaseError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Firebase impediment: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unexpected obstruction: {e}")

@app.post("/set-github-token")
async def set_github_token(github_token: str = Form(...), user_id: str = Depends(get_current_user_id)):
    """
    Kage: Records the GitHub access key. A direct, less secure path.
    """
    global db
    if not db or not user_id:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="System foundation or user identity absent.")
    
    encrypted_token = github_token # Kage: Placeholder. Encryption is the true safeguard.

    try:
        user_doc_ref = db.collection('artifacts').document(app_id).collection('users').document(user_id).collection('cv_data').document('profile')
        user_doc_ref.update({"github_token_encrypted": encrypted_token})
        return JSONResponse(content={"message": "GitHub access key recorded."})
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to secure access key: {e}")

# Kage: Core application pathways.
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """
    Kage: The primary gateway. Verifies presence before granting access to the domain.
    """
    try:
        user_id = await get_current_user_id(request)
    except HTTPException as e:
        if e.status_code == status.HTTP_401_UNAUTHORIZED:
            return RedirectResponse(url="/login_page", status_code=status.HTTP_302_FOUND)
        raise

    current_user_cv_data = await get_user_cv_data_from_firestore(user_id)
    
    if not current_user_cv_data.get("email_verified"):
        return RedirectResponse(url="/login_page?message=Path not verified. Complete verification.&type=error", status_code=status.HTTP_302_FOUND)

    display_user_name = current_user_cv_data.get("name", "Ephemeral Being")

    github_status_message = "GitHub API: Active." if (current_user_cv_data.get("github_oauth_token_encrypted") or current_user_cv_data.get("github_token_encrypted")) else "GitHub access: Dormant. Provide key."
    analyzer_status_message = "LLM Analyzer: Active." if project_analyzer else "LLM Analyzer: Dormant. Configuration needed."
    scoring_status_message = "Scoring Engine: Active." if scoring_engine else "Scoring Engine: Dormant. Configuration needed."
    cv_writer_status_message = "CV Writer: Active." if cv_writer else "CV Writer: Dormant. Configuration needed."
    cv_parser_status_message = "CV Parser: Active." if cv_parser else "CV Parser: Dormant. Configuration needed."

    return templates.TemplateResponse("index.html", {
        "request": request,
        "github_status": github_status_message,
        "analyzer_status": analyzer_status_message,
        "scoring_status": scoring_status_message,
        "cv_writer_status": cv_writer_status_message,
        "cv_parser_status": cv_parser_status_message,
        "projects": [],
        "user_cv_data": current_user_cv_data,
        "current_user_id": user_id,
        "display_user_name": display_user_name
    })

@app.get("/api/user_cv_data", response_class=JSONResponse)
async def get_user_cv_data_api(user_id: str = Depends(get_current_user_id)):
    """
    Kage: Reveals the user's profile data. Conceals sensitive elements.
    """
    try:
        current_user_cv_data = await get_user_cv_data_from_firestore(user_id)
        data_to_send = current_user_cv_data.copy()
        data_to_send.pop("github_oauth_token_encrypted", None)
        data_to_send.pop("github_token_encrypted", None)
        data_to_send.pop("verification_code", None)
        
        return JSONResponse(content={"user_cv_data": data_to_send})
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[Kage] Profile data retrieval failed for {user_id}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to perceive user profile: {e}")

@app.get("/api/projects", response_class=JSONResponse)
async def get_projects_data(user_id: str = Depends(get_current_user_id)):
    global db, project_analyzer, scoring_engine

    current_user_cv_data = await get_user_cv_data_from_firestore(user_id)
    
    user_github_token = current_user_cv_data.get("github_oauth_token_encrypted") or \
                        current_user_cv_data.get("github_token_encrypted") # Kage: Decrypt if implemented.

    if not user_github_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="GitHub access key not present. Provide access.")

    try:
        user_github_listener = GitHubListener(github_token=user_github_token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"GitHub Listener: Initialization failed with user key: {e}")

    if not project_analyzer:
        print("[Kage] Project Analyzer: Dormant. Proceeding without deep insight.")
        raw_projects_data = user_github_listener.get_all_project_data(include_private=True, min_stars=0)
        return {
            "projects": [{
                **project,
                "skills": [], "technologies": [], "achievements": ["Insight withheld: Analyzer inactive."],
                "summary": "Full analysis is not possible for this project.",
                "keywords": [], "estimated_complexity_qualitative": "N/A",
                "performance_metrics": {},
                "score": 0.0
            } for project in raw_projects_data],
            "status": "warning",
            "message": "Project Analyzer dormant. Full insight unavailable.",
            "username": current_user_cv_data.get("name", "Ephemeral Being"),
            "user_id": user_id
        }

    if not scoring_engine:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Scoring Engine: Dormant. Evaluation cannot proceed.")

    try:
        raw_projects_data = user_github_listener.get_all_project_data(include_private=True, min_stars=0)
        
        analyzed_and_scored_projects = []
        for project in raw_projects_data:
            try:
                analyzed_data = await project_analyzer.analyze_project(project)
                combined_data = {**project, **analyzed_data}
                score = scoring_engine.calculate_score(combined_data)
                combined_data['score'] = round(score, 2)
                analyzed_and_scored_projects.append(combined_data)
            except Exception as e:
                print(f"[Kage] Insight failed for project {project.get('name', 'Unnamed')}: {e}. Skipping depth.")
                analyzed_and_scored_projects.append({
                    **project,
                    "skills": [], "technologies": [], "achievements": [f"Insight and evaluation failed: {e}"],
                    "summary": "Full understanding and evaluation could not be completed for this project.",
                    "keywords": [], "estimated_complexity_qualitative": "N/A",
                    "performance_metrics": {},
                    "score": 0.0
                })

        print(f"[Kage] {len(analyzed_and_scored_projects)} projects observed and evaluated for {user_id}.")
        return {
            "projects": analyzed_and_scored_projects,
            "status": "success",
            "message": f"Observation and evaluation complete for {len(analyzed_and_scored_projects)} projects.",
            "username": current_user_cv_data.get("name", "Ephemeral Being"),
            "user_id": user_id
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Observation of projects obstructed: {e}")

@app.post("/upload-cv")
async def upload_cv(file: UploadFile = File(...), user_id: str = Depends(get_current_user_id)):
    global db, cv_parser

    current_user_cv_data = await get_user_cv_data_from_firestore(user_id)
    
    if not cv_parser:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="CV Parser: Dormant. Cannot ingest.")
    if not db or not user_id:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="System foundation or user identity absent for data storage.")

    file_extension = os.path.splitext(file.filename)[1].lower()
    if file_extension not in [".docx", ".pdf"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .docx or .pdf forms are accepted.")

    temp_file_path = os.path.join(OUTPUT_DIR, file.filename)
    try:
        with open(temp_file_path, "wb") as buffer:
            buffer.write(await file.read())
        
        parsed_data = cv_parser.parse_cv(temp_file_path)
        
        current_user_cv_data.update(parsed_data)
        
        user_doc_ref = db.collection('artifacts').document(app_id).collection('users').document(user_id).collection('cv_data').document('profile')
        user_doc_ref.set(current_user_cv_data)
        print(f"[Kage] User CV absorbed and stored for {user_id}.")

        return JSONResponse(content={"message": "CV absorbed and processed.", "data": parsed_data})
    except Exception as e:
        print(f"[Kage] CV ingestion failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to process CV: {e}")
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

@app.get("/download-resume")
async def download_resume(format: str = "pdf", user_id: str = Depends(get_current_user_id)):
    """
    Kage: Generates and provides the user's compiled form.
    """
    global cv_writer

    if not cv_writer:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="CV Writer: Dormant. Cannot forge documents.")
    if not db or not user_id:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="System foundation or user identity absent for document creation.")

    current_user_cv_data = await get_user_cv_data_from_firestore(user_id)

    try:
        # Kage: Direct call to get raw project data, bypassing FastAPI's JSONResponse wrapper
        # when called internally. This ensures a consistent dictionary format.
        projects_response = await get_projects_data(user_id=user_id)
        all_projects_data = projects_response.get('projects', [])

        # Kage: Sort projects by score in descending order and select the top 4.
        # This aligns with the principle of focusing on the most impactful projects.
        sorted_projects = sorted(all_projects_data, key=lambda p: p.get('score', 0), reverse=True)
        projects_data = sorted_projects[:4] # Select top 4

    except HTTPException as e:
        print(f"[Kage] Project data for document forging failed: {e.detail}")
        raise e
    except Exception as e:
        print(f"[Kage] Project data acquisition for document forging obstructed: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to gather project data for document creation: {e}")

    cv_filename_base = f"{current_user_cv_data.get('name', 'Kaku-Ryu_Form').replace(' ', '_')}"
    docx_output_filename = f"{cv_filename_base}.docx"
    pdf_output_filename = f"{cv_filename_base}.pdf"

    generated_docx_path = cv_writer.generate_cv(
        projects_data,
        current_user_cv_data,
        output_filename=docx_output_filename
    )

    if not generated_docx_path:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Document forging failed. DOCX path unmanifested.")

    if format.lower() == "pdf":
        pdf_path = os.path.join(OUTPUT_DIR, pdf_output_filename)
        try:
            docx_to_pdf_convert(generated_docx_path, pdf_path)
            print(f"[Kage] Form transformed to PDF: {pdf_path}")
            return FileResponse(path=pdf_path, filename=pdf_output_filename, media_type="application/pdf")
        except Exception as e:
            print(f"[Kage] PDF transformation failed: {e}. Presenting DOCX alternative.")
            traceback.print_exc()
            return FileResponse(path=generated_docx_path, filename=docx_output_filename, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    else:
        print(f"[Kage] Presenting DOCX form: {generated_docx_path}")
        return FileResponse(path=generated_docx_path, filename=docx_output_filename, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
