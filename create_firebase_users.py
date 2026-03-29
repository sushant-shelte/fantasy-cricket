"""
Create Firebase Auth accounts for all users.
Run once: python create_firebase_users.py
"""
import firebase_admin
from firebase_admin import credentials, auth
import json
import os

# Initialize Firebase Admin
cred_path = os.path.join("backend", "firebase-credentials.json")
if os.path.exists(cred_path):
    cred = credentials.Certificate(cred_path)
else:
    cred = credentials.Certificate(json.loads(os.environ["FIREBASE_CREDENTIALS"]))

firebase_admin.initialize_app(cred)

# Users to create: (email, password, display_name)
users = [
    ("sushant@gmail.com", "hippies123", "Sushant"),
    ("poonam@gmail.com", "hippies123", "Poonam"),
    ("aashay@gmail.com", "hippies123", "Aashay"),
    ("sagar@gmail.com", "hippies123", "Sagar"),
    ("akshay@gmail.com", "hippies123", "Akshay"),
    ("ajinkya@gmail.com", "hippies123", "Ajinkya"),
    ("ajinkyasathe@gmail.com", "hippies123", "Ajinkya Sathe"),
    ("neha@gmail.com", "hippies123", "Neha"),
    ("prachi@gmail.com", "hippies123", "Prachi"),
    ("priyanka@gmail.com", "hippies123", "Priyanka"),
    ("ravi@gmail.com", "hippies123", "Ravi"),
    ("sejal@gmail.com", "hippies123", "Sejal"),
    ("nidhi@gmail.com", "hippies123", "Nidhi"),
    ("pradyumna@gmail.com", "hippies123", "Pradyumna"),
    ("rupesh@gmail.com", "hippies123", "Rupesh"),
]

print("Creating Firebase accounts...\n")

for email, password, name in users:
    try:
        # Check if user already exists
        existing = auth.get_user_by_email(email)
        print(f"  EXISTS: {name:20s} {email:30s} uid={existing.uid}")
    except auth.UserNotFoundError:
        # Create new user
        user = auth.create_user(
            email=email,
            password=password,
            display_name=name,
        )
        print(f"  CREATED: {name:20s} {email:30s} uid={user.uid}")
    except Exception as e:
        print(f"  ERROR: {name:20s} {email:30s} -> {e}")

print("\nDone! Default password for all: hippies123")
print("Users should change their password after first login.")
