"""
Backend - FastAPI Application
Version: 1.0.1 (cleaned imports)
"""

import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import google.generativeai as genai

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configure Gemini ONCE (fail fast)
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise RuntimeError("GOOGLE_API_KEY not set. Please add it to your .env file.")

genai.configure(api_key=api_key)

# Validate required environment variables
required_env_vars = {
    "DATABASE_URL": "PostgreSQL database connection string",
    "GOOGLE_API_KEY": "Google Generative AI API key",
    "CLOUDINARY_CLOUD_NAME": "Cloudinary cloud name",
    "CLOUDINARY_API_KEY": "Cloudinary API key",
    "CLOUDINARY_API_SECRET": "Cloudinary API secret",
}

missing_vars = []
for var_name, var_desc in required_env_vars.items():
    if not os.getenv(var_name):
        missing_vars.append(f"{var_name} ({var_desc})")

if missing_vars:
    logger.warning(f"Missing environment variables: {', '.join(missing_vars)}")
else:
    logger.info("All required environment variables are set")

# Local imports
from config import UPLOADS_DIR
from database.postgres import init_db
from routers import (
    health,
    quotes,
    upload,
    list,
    get,
    delete,
    matching,
    tags,
    favorites,
    search,
    recommendations,
)

# Create FastAPI app
app = FastAPI(
    title="Fashion Style Recommender API",
    version="0.1.0",
)

# Enable CORS (placed immediately after app creation)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://fashionrecommenderai.netlify.app",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.options("/{full_path:path}")
async def preflight_handler(full_path: str):
    """Handle CORS preflight requests"""
    return {"message": "OK"}


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled errors"""
    logger.exception(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "detail": "Internal server error"},
    )

@app.on_event("startup")
def on_startup():
    try:
        logger.info("Starting up application...")
        init_db()
        logger.info("Application startup complete")
    except Exception as e:
        logger.error(f"Application startup failed: {e}", exc_info=True)
        raise

# Mount uploads directory
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# (CORS middleware moved to immediately after app creation)

# Root endpoint
@app.get("/")
async def root():
    return {"message": "Hello from Fashion Style Recommender Backend!"}

# Register routers
app.include_router(health.router)
app.include_router(quotes.router)
app.include_router(upload.router)
app.include_router(list.router)
app.include_router(favorites.router)
app.include_router(get.router)
app.include_router(delete.router)
app.include_router(matching.router)
app.include_router(tags.router)
app.include_router(search.router)
app.include_router(recommendations.router)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    reload = os.getenv("ENVIRONMENT", "development") == "development"
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload)
