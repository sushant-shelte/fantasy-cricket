import os
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth
from backend.config import FIREBASE_CREDENTIALS_PATH

_initialized = False


def init_firebase():
    global _initialized
    if _initialized:
        return

    if os.path.exists(FIREBASE_CREDENTIALS_PATH):
        cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred)
        _initialized = True
        print("Firebase Admin SDK initialized")
    else:
        # Try environment variable
        creds_json = os.environ.get("FIREBASE_CREDENTIALS")
        if creds_json:
            import json
            cred = credentials.Certificate(json.loads(creds_json))
            firebase_admin.initialize_app(cred)
            _initialized = True
            print("Firebase Admin SDK initialized from env")
        else:
            print("WARNING: Firebase credentials not found. Auth will use dev mode.")
            _initialized = True  # Mark as initialized to avoid retrying


def verify_firebase_token(id_token: str) -> dict | None:
    try:
        decoded = firebase_auth.verify_id_token(id_token)
        return decoded
    except Exception:
        return None
