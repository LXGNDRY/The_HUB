"""
Serves the Legendary HUB store-ops dashboard at /app.
No X-API-Key guard — the dashboard JS authenticates to the API directly.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/app", response_class=HTMLResponse, include_in_schema=False)
def serve_app():
    with open("frontend/index.html", encoding="utf-8") as f:
        return HTMLResponse(f.read())
