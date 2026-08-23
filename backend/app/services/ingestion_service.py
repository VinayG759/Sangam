import logging
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import CitizenReport, PendingIntake
from app.services.gemini_service import gemini_service
from app.utils.hashing import hash_channel_user
from app.utils.tracking_id import generate_tracking_id
from app.services.location_resolver import resolve_location
from datetime import datetime, timedelta
from app.services.pack_loader import pack_loader
from app.services.reprocess_scheduler import schedule_reprocess

logger = logging.getLogger(__name__)

async def ingest_citizen_message(
    db: AsyncSession,
    text: Optional[str] = None,
    audio_bytes: Optional[bytes] = None,
    mime_type: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    channel: str = "web",
    channel_user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Ingest a new citizen voice/text report, translate, analyze PII, generate tracking ID, and save to DB.
    """
    # Generate tracking IDs and hash
    tracking_id = generate_tracking_id()
    reporter_hash = None
    if channel_user_id:
        reporter_hash = hash_channel_user(channel_user_id)

    location_wkt = None
    if latitude is not None and longitude is not None:
        location_wkt = f"SRID=4326;POINT({longitude} {latitude})"

    analysis = {}
    embedding = None
    english_translation = ""
    gemini_failed = False

    try:
        # Run Call 1 Gemini analysis
        analysis = gemini_service.analyze_citizen_report(
            text_content=text,
            audio_bytes=audio_bytes,
            mime_type=mime_type
        )

        english_translation = analysis.get("english_translation") or text or ""

        # Get semantic embedding
        embedding = gemini_service.get_embedding(english_translation)
    except Exception as e:
        logger.error(f"Gemini analysis failed during ingestion: {e}")
        gemini_failed = True

    try:
        if gemini_failed:
            raw_text_to_save = text or "Audio input (unprocessed)"
            pii_redacted = ""
            status = "pending_analysis"
            region_id = None
            needs_location_followup = False
        else:
            status = "complete"
            # Stop persisting raw_text if PII redaction succeeds
            pii_redacted = analysis.get("pii_redacted_text", "")
            if not pii_redacted or pii_redacted == "[Audio - Failed to process]" or "Failed to analyze" in analysis.get("specific_issue", ""):
                # Fallback
                raw_text_to_save = text or "Audio input"
                logger.warning(f"PII redaction failed or fallback occurred. Persisting raw text for tracking_id {tracking_id}.")
            else:
                # Successfully redacted, don't keep raw
                raw_text_to_save = "Redacted"
                
            # Resolve location
            region = await resolve_location(
                analysis.get("location_text_latin", ""),
                pack_loader.load_active_pack().country_code,
                db
            )
            
            region_id = region.id if region else None
            needs_location_followup = False
            
            if not region_id and not location_wkt and reporter_hash:
                needs_location_followup = True

        report = CitizenReport(
            status=status,
            raw_text=raw_text_to_save,
            detected_language=analysis.get("original_language", "unknown") if not gemini_failed else "unknown",
            english_translation=english_translation if not gemini_failed else None,
            sector=analysis.get("sector", "unknown") if not gemini_failed else "unknown",
            specific_issue=analysis.get("specific_issue", "") if not gemini_failed else None,
            urgency_score=analysis.get("urgency_score", 1.0) if not gemini_failed else 1.0,
            sentiment=analysis.get("sentiment", "neutral") if not gemini_failed else None,
            pii_redacted_text=pii_redacted if not gemini_failed else None,
            location=location_wkt,
            region_id=region_id,
            embedding=embedding,
            tracking_id=tracking_id,
            channel=channel,
            reporter_hash=reporter_hash
        )
        db.add(report)
        await db.flush()
        
        if needs_location_followup:
            pending = PendingIntake(
                channel_user_hash=reporter_hash,
                channel=channel,
                partial_report={"report_id": report.id, "analysis": analysis},
                awaiting="location",
                expires_at=datetime.utcnow() + timedelta(hours=1)
            )
            db.add(pending)
            await db.flush()

        # Fire-and-forget: the dashboard (overview/priorities/clusters)
        # only reflects reports that have gone through the clustering/
        # prioritization pipeline, which used to require someone to
        # manually POST /api/v1/reprocess after every batch of new
        # reports. This schedules that pipeline to run automatically a
        # short while after ingestion instead.
        schedule_reprocess()

        return {
            "status": "success",
            "report_id": report.id,
            "tracking_id": tracking_id,
            "analysis_extracted": analysis if not gemini_failed else None,
            "needs_location_followup": needs_location_followup
        }
    except Exception as e:
        logger.error(f"Error persisting citizen message: {e}")
        await db.rollback()
        raise
