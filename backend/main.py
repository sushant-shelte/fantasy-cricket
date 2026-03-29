from dotenv import load_dotenv
load_dotenv()  # Load .env file from project root

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.firebase_setup import init_firebase
from backend.services import data_service
from backend.models.tournament import Tournament
from backend.routes import auth, matches, players, teams, scores, leaderboard, admin

app = FastAPI(title="Fantasy Cricket API")

# CORS for React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(auth.router)
app.include_router(matches.router)
app.include_router(players.router)
app.include_router(teams.router)
app.include_router(scores.router)
app.include_router(leaderboard.router)
app.include_router(admin.router)

# Tournament singleton
tournament = Tournament()


@app.on_event("startup")
def startup():
    # Initialize database
    init_db()
    print("Database initialized")

    # Initialize Firebase (optional - works in dev mode without it)
    init_firebase()

    # Set tournament reference for admin recalculate
    admin.set_tournament(tournament)

    # Load data and start scheduler
    players_data = data_service.get_cached_data("players")
    matches_data = data_service.get_cached_data("matches")
    teams_data = data_service.get_teams()

    tournament.initialize(players_data, matches_data, teams_data)
    tournament.start_scheduler()

    print("Fantasy Cricket API started!")


@app.get("/api/health")
def health():
    return {"status": "ok"}
