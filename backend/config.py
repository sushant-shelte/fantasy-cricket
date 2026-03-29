import os
import pytz

TEST_MODE = True
TEST_MODE_MONTH = 3
TEST_MODE_DATE = 22
TEST_MODE_TIME_HR = 20
TEST_MODE_TIME_MIN = 0

MATCH_CODE_OFFSET = 1107 if TEST_MODE else 1181

ROLES = ["Wicketkeeper", "Batter", "AllRounder", "Bowler"]

SECRET_KEY = os.environ.get("SECRET_KEY", "fantasy-cricket-dev-secret-key")

IST = pytz.timezone("Asia/Kolkata")

TEAM_MAP = {
    "Royal Challengers Bengaluru": "RCB",
    "Mumbai Indians": "MI",
    "Chennai Super Kings": "CSK",
    "Kolkata Knight Riders": "KKR",
    "Rajasthan Royals": "RR",
    "Gujarat Titans": "GT",
    "Delhi Capitals": "DC",
    "Lucknow Super Giants": "LSG",
    "Punjab Kings": "PBKS",
    "Sunrisers Hyderabad": "SRH",
    "RCB": "RCB", "MI": "MI", "CSK": "CSK", "KKR": "KKR", "RR": "RR",
    "GT": "GT", "DC": "DC", "LSG": "LSG", "PBKS": "PBKS", "SRH": "SRH",
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "fantasy.db")
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "data")

FIREBASE_CREDENTIALS_PATH = os.environ.get(
    "FIREBASE_CREDENTIALS_PATH",
    os.path.join(BASE_DIR, "firebase-credentials.json"),
)
