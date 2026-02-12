import sys
from pathlib import Path

# Add current directory to Python path for Backend modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import the FastAPI app from main.py
from main import app
from mangum import Mangum

# Wrap the FastAPI app with Mangum for Vercel serverless execution
handler = Mangum(app)
