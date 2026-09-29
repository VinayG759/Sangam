"""
The one list of features the API serves. Adding a feature = one line here.
Optional features are mounted only when their kill switch is on.
"""

from fastapi import APIRouter

from app.core.config import get_settings
from app.features.analysis.router import router as analysis_router
from app.features.analytics.router import router as analytics_router
from app.features.export.router import router as export_router
from app.features.impact.router import router as impact_router
from app.features.intake.router import admin_router as intake_admin_router
from app.features.intake.router import telegram_router, web_router, whatsapp_router
from app.features.notify.router import router as notify_router
from app.features.overview.router import router as overview_router
from app.features.priorities.router import router as priorities_router
from app.features.regions.router import router as regions_router
from app.features.reports.router import router as reports_router
from app.features.simulator.router import router as simulator_router


def enabled_routers() -> list[APIRouter]:
    settings = get_settings()
    routers: list[tuple[APIRouter, bool]] = [
        (regions_router, True),
        (overview_router, True),
        (analytics_router, True),
        (priorities_router, True),
        (reports_router, True),
        (analysis_router, True),
        (intake_admin_router, True),
        (web_router, settings.FEATURE_WEB_INTAKE),
        (telegram_router, settings.FEATURE_TELEGRAM),
        (whatsapp_router, settings.FEATURE_WHATSAPP),
        (simulator_router, settings.FEATURE_SIMULATOR),
        (export_router, settings.FEATURE_EXPORT),
        (impact_router, settings.FEATURE_IMPACT),
        (notify_router, settings.FEATURE_NOTIFY),
    ]
    return [router for router, enabled in routers if enabled]
