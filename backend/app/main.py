import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.config import settings
from app.limiter import limiter

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

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Root & Health endpoints (no prefix) ─────────────────────────────────────

@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Welcome to the Sangam DPG API. Visit /docs for the interactive API specification."
    }

@app.get("/health", tags=["Root"])
async def health_check():
    return {
        "status": "healthy",
        "app": "Sangam Backend Engine",
        "active_pack": settings.ACTIVE_COUNTRY_PACK
    }

# ── Register all API route groups from centralized registry ─────────────────

from app.routes import all_routers

for router in all_routers:
    app.include_router(router)

logger.info(f"Registered {len(all_routers)} API route groups")
