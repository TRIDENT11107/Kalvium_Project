import sys
from pathlib import Path
root=str(Path(__file__).resolve().parents[2])
if root not in sys.path: sys.path.insert(0,root)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.settings import settings
from app.api.auth import router as auth_router
from app.api.routes import router as api_router
app=FastAPI(title="AI Lesson Studio API",version="1.0.0")
origins=[x.strip() for x in settings.cors_origins.split(",") if x.strip()]
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_credentials=True,allow_methods=["*"],allow_headers=["Authorization","Content-Type"])
app.include_router(auth_router); app.include_router(api_router)
@app.get("/")
def root():
    return {
        "name": "AI Lesson Studio API",
        "status": "ok",
        "frontend": "http://localhost:8080",
        "docs": "/docs",
        "health": "/health",
    }
@app.get("/health")
def health(): return {"status":"ok"}
