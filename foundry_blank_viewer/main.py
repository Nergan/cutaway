from pathlib import Path
from fastapi import FastAPI, APIRouter
from fastapi.responses import HTMLResponse

# Create a router to integrate into the main Cutaway project
router = APIRouter()

# Define the base directory to locate the HTML file
BASE_DIR = Path(__file__).parent

@router.get("/", response_class=HTMLResponse)
async def foundry_viewer_home():
    """
    Serves the single HTML file containing the viewer.
    """
    html_path = BASE_DIR / "foundry_blank_viewer.html"
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()

# Initialize a standalone app for testing via `uvicorn foundry_blank_viewer.main:app`
app = FastAPI(title="Foundry Blank Viewer")
app.include_router(router)