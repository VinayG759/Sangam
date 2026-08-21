import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Sangam API",
    description="Multilingual Digital Public Good for Evidence-Backed Infrastructure Prioritization",
    version="1.0.0"
)

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "app": "Sangam Backend Engine",
        "active_pack": settings.ACTIVE_COUNTRY_PACK
    }

from app.routes.overview import router as overview_router
from app.routes.priorities import router as priorities_router

app.include_router(overview_router)
app.include_router(priorities_router)

@app.get("/")
async def root():
    return {
        "message": "Welcome to the Sangam DPG API. Visit /docs for the interactive API specification."
    }

