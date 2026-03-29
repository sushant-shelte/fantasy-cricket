import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.database import init_db
from backend.firebase_setup import init_firebase
from backend.services import data_service
from backend.models.tournament import Tournament
from backend.routes import auth, matches, players, teams, scores, leaderboard, admin

app = FastAPI(title="Fantasy Cricket API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
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
    init_db()
    print("Database initialized")

    init_firebase()

    admin.set_tournament(tournament)

    players_data = data_service.get_cached_data("players")
    matches_data = data_service.get_cached_data("matches")
    teams_data = data_service.get_teams()

    tournament.initialize(players_data, matches_data, teams_data)
    tournament.start_scheduler()

    print("Fantasy Cricket API started!")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve React static files in production
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")

if os.path.isdir(STATIC_DIR):
    # Serve static assets (js, css, images)
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="static-assets")

    # Serve other static files (favicon, etc)
    @app.get("/favicon.svg")
    async def favicon():
        return FileResponse(os.path.join(STATIC_DIR, "favicon.svg"))

    # Catch-all: serve index.html for React Router (must be LAST)
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        # Don't intercept API routes
        if full_path.startswith("api/"):
            return {"detail": "Not found"}
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
