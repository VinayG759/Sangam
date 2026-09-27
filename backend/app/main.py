"""Sangam API entry point."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import get_settings
from app.core.limiter import limiter
from app.core.pack import get_pack
from app.registry import enabled_routers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = get_settings()
app = FastAPI(title="Sangam API", version="2.0.0",
              description="Open-source Digital Public Good: multilingual citizen voice joined with "
                          "public data to recommend infrastructure priorities.")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# No cookies or credentials are used, so origins are restricted and credentials stay off.
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=False,
                   allow_methods=["GET", "POST"], allow_headers=["*"])

for router in enabled_routers():
    app.include_router(router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "pack": get_pack().name}
