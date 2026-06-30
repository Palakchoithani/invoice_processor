import sys
from pathlib import Path

# Add the project root to sys.path so it can find services/, models/, config/ etc.
sys.path.append(str(Path(__file__).parent.parent))

# Import the FastAPI app instance from app.py
from app import app
