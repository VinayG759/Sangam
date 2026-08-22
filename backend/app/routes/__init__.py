"""
Centralized route registration for the Sangam API.

All route modules are imported here and collected into a single list.
main.py includes them all via a single import from this module.
"""

from app.routes.overview import router as overview_router
from app.routes.priorities import router as priorities_router
from app.routes.regions import router as regions_router
from app.routes.reports import router as reports_router
from app.routes.expenditures import router as expenditures_router
from app.routes.clusters import router as clusters_router
from app.routes.pack import router as pack_router

# Ordered list of all API route groups
all_routers = [
    overview_router,
    priorities_router,
    regions_router,
    reports_router,
    expenditures_router,
    clusters_router,
    pack_router,
]
