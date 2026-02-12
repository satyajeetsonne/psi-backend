"""
Backend - FastAPI Application
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()

# Configure Gemini ONCE (fail fast)
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise RuntimeError("GOOGLE_API_KEY not set. Please add it to your .env file.")

genai.configure(api_key=api_key)

# Local imports
from config import UPLOADS_DIR
from database.db import init_db
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
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Startup event (clean DB init)
@app.on_event("startup")
def on_startup():
    init_db()

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
