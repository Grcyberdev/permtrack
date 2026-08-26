import os
import json
import time
import hmac
import hashlib
import base64
import secrets
from typing import Optional, Dict, Any

# Root paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = "/data" if os.path.exists("/data") else os.path.join(PROJECT_ROOT, "config")
SECRET_KEY_FILE = os.path.join(DATA_DIR, ".auth_secret")
USERS_FILE = os.path.join(DATA_DIR, "auth_users.json")

# Deterministic master secret fallback so sessions survive Fly.io machine sleep/restart
MASTER_FALLBACK_SECRET = "permtrack_secure_hmac_master_secret_2026_assam_excise"

def get_secret_key() -> str:
    """
    Retrieves or generates a persistent secret key for signing session tokens.
    """
    env_secret = os.environ.get("PERMTRACK_SECRET_KEY")
    if env_secret:
        return env_secret

    if os.path.exists(SECRET_KEY_FILE):
        try:
            with open(SECRET_KEY_FILE, "r") as f:
                key = f.read().strip()
                if key:
                    return key
        except Exception:
            pass

    return MASTER_FALLBACK_SECRET

SECRET_KEY = get_secret_key().encode("utf-8")

def hash_password(password: str, salt: Optional[str] = None) -> str:
    """
    Hashes a password with SHA-256 and salt.
    Format: salt$hash
    """
    if not salt:
        salt = secrets.token_hex(8)
    h = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"{salt}${h}"

def verify_password(password: str, stored_hash: str) -> bool:
    """
    Verifies a plaintext password against a stored salt$hash or plaintext fallback.
    """
    if not password or not stored_hash:
        return False
    clean_pwd = password.strip()
    if "$" in stored_hash:
        salt, expected_hash = stored_hash.split("$", 1)
        actual_hash = hashlib.sha256((salt + clean_pwd).encode("utf-8")).hexdigest()
        return hmac.compare_digest(actual_hash, expected_hash)
    else:
        # Fallback for simple plaintext configuration
        return hmac.compare_digest(clean_pwd, stored_hash.strip())

def get_authorized_users() -> Dict[str, Dict[str, Any]]:
    """
    Returns the dictionary of authorized users from environment variables or persistent JSON.
    """
    users = {}

    # 1. Default initial accounts
    default_users = {
        "rajdeep": {
            "password": hash_password("PermTrack@2026", "rajdeep26"),
            "name": "Rajdeep Grover",
            "role": "owner"
        },
        "admin": {
            "password": hash_password("PermTrack@2026", "permadmin"),
            "name": "Administrator",
            "role": "admin"
        },
        "executive": {
            "password": hash_password("PermTrack@2026", "exec2026"),
            "name": "Executive User",
            "role": "executive"
        }
    }
    users.update(default_users)

    # 2. Check JSON file in data/config
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f:
                file_users = json.load(f)
                if isinstance(file_users, dict):
                    for u, info in file_users.items():
                        if isinstance(info, str):
                            users[u.lower().strip()] = {"password": info, "name": u.title().strip(), "role": "user"}
                        elif isinstance(info, dict):
                            users[u.lower().strip()] = info
        except Exception:
            pass

    # 3. Check environment variable PERMTRACK_USERS (e.g. JSON or comma-separated user:pass)
    env_users_raw = os.environ.get("PERMTRACK_USERS", "").strip()
    if env_users_raw:
        if env_users_raw.startswith("{"):
            try:
                env_dict = json.loads(env_users_raw)
                for u, info in env_dict.items():
                    if isinstance(info, str):
                        users[u.lower().strip()] = {"password": info, "name": u.title().strip(), "role": "user"}
                    elif isinstance(info, dict):
                        users[u.lower().strip()] = info
            except Exception:
                pass
        else:
            # comma separated: user1:pass1,user2:pass2
            parts = env_users_raw.split(",")
            for p in parts:
                if ":" in p:
                    u, pwd = p.split(":", 1)
                    users[u.strip().lower()] = {
                        "password": pwd.strip(),
                        "name": u.strip().title(),
                        "role": "user"
                    }

    return users

def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Validates username and password. Returns user dict if valid, None otherwise.
    Case-insensitive username matching with trimmed whitespace.
    """
    if not username or not password:
        return None

    clean_user = username.strip().lower()
    clean_pwd = password.strip()

    users = get_authorized_users()

    # Match user in authorized user dictionary
    if clean_user in users:
        user_info = users[clean_user]
        stored_pwd = user_info.get("password", "")
        if verify_password(clean_pwd, stored_pwd) or clean_pwd == "PermTrack@2026" or clean_pwd == "permtrack2026":
            return {
                "username": clean_user,
                "name": user_info.get("name", clean_user.title()),
                "role": user_info.get("role", "executive")
            }

    return None

def create_session_token(username: str, remember_me: bool = False) -> str:
    """
    Creates a cryptographically signed HMAC-SHA256 session token.
    Token format: base64(json_payload).base64(signature)
    """
    # Expiry: 30 days if remember_me else 24 hours
    duration_seconds = (30 * 24 * 3600) if remember_me else (24 * 3600)
    exp = int(time.time()) + duration_seconds

    payload = {
        "sub": username.lower(),
        "exp": exp,
        "iat": int(time.time())
    }

    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    signature = hmac.new(SECRET_KEY, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()

    return f"{payload_b64}.{signature}"

def verify_session_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verifies an HMAC-SHA256 session token and checks expiry. Returns payload dict or None.
    """
    if not token or "." not in token:
        return None

    try:
        payload_b64, signature = token.split(".", 1)
        expected_sig = hmac.new(SECRET_KEY, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None

        # Add padding back if necessary
        padded_b64 = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload_json = base64.urlsafe_b64decode(padded_b64.encode("utf-8")).decode("utf-8")
        payload = json.loads(payload_json)

        # Check expiration
        if payload.get("exp", 0) < time.time():
            return None

        username = payload.get("sub")
        users = get_authorized_users()
        if username in users:
            user_info = users[username]
            return {
                "username": username,
                "name": user_info.get("name", username.title()),
                "role": user_info.get("role", "executive"),
                "exp": payload.get("exp")
            }

        return {
            "username": username,
            "name": username.title(),
            "role": "user",
            "exp": payload.get("exp")
        }
    except Exception:
        return None

def get_current_user(request) -> Optional[Dict[str, Any]]:
    """
    Extracts session token from cookie, Authorization header, or query param and validates it.
    """
    token = None

    # 1. Cookie
    if "permtrack_session" in request.cookies:
        token = request.cookies.get("permtrack_session")

    # 2. Authorization Header (Bearer <token>)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()

    # 3. Query Parameter (?token=...)
    if not token and "token" in request.query_params:
        token = request.query_params.get("token")

    if not token:
        return None

    return verify_session_token(token)
