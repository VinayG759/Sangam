import logging
from typing import Optional, Dict, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.models.models import CitizenReport, PendingIntake
from app.services.gemini_service import gemini_service
from app.utils.hashing import hash_channel_user
from app.utils.tracking_id import generate_tracking_id
from app.services.location_resolver import resolve_location, resolve_location_with_confidence
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

    # Phase 20: Abuse Resistance - max 10 reports/day per reporter_hash
    if reporter_hash:
        start_of_day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        count_stmt = (
            select(func.count(CitizenReport.id))
            .where(
                CitizenReport.reporter_hash == reporter_hash,
                CitizenReport.reported_at >= start_of_day
            )
        )
        count_res = await db.execute(count_stmt)
        today_count = 0
        if hasattr(count_res, "scalar") and callable(count_res.scalar):
            val = count_res.scalar()
            import inspect
            if inspect.iscoroutine(val):
                val.close()
                today_count = 0
            elif isinstance(val, (int, float)):
                today_count = int(val)

        if today_count >= 10:
            logger.warning(f"Rate limit exceeded for reporter_hash {reporter_hash}: {today_count}/10 reports today.")
            return {
                "status": "rejected",
                "message": "Maximum reports for today reached. Please try again tomorrow.",
                "report_id": None,
                "tracking_id": None,
                "needs_location_followup": False,
                "needs_location_confirmation": False
            }

    location_wkt = None
    if latitude is not None and longitude is not None:
        location_wkt = f"SRID=4326;POINT({longitude} {latitude})"

    # Phase 22: Media size limit (10 MB)
    if audio_bytes and len(audio_bytes) > 10 * 1024 * 1024:
        return {
            "status": "rejected",
            "message": "The media file is too large (maximum size is 10 MB). Please send a shorter voice note or smaller image.",
            "report_id": None,
            "tracking_id": None,
            "needs_location_followup": False,
            "needs_location_confirmation": False
        }

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

    region_id = None
    needs_location_followup = False
    needs_location_confirmation = False
    candidate_region = None

    try:
        if gemini_failed:
            raw_text_to_save = text or "Audio input (unprocessed)"
            pii_redacted = ""
            status = "pending_analysis"
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
            loc_text = analysis.get("location_text_latin", "")
            region = await resolve_location(
                loc_text,
                pack_loader.load_active_pack().country_code,
                db
            )
            
            region_id = region.id if region else None
            
            if not region_id and not location_wkt and reporter_hash:
                try:
                    loc_conf = await resolve_location_with_confidence(
                        loc_text,
                        pack_loader.load_active_pack().country_code,
                        db
                    )
                    if loc_conf.get("candidate"):
                        candidate_region = loc_conf["candidate"]
                        needs_location_confirmation = True
                    else:
                        needs_location_followup = True
                except Exception as ex:
                    logger.warning(f"Failed resolving location confidence: {ex}")
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
            reporter_hash=reporter_hash,
            flagged_coordinated=False
        )
        db.add(report)
        await db.flush()

        # Coordinated-flood check (Phase 20: Abuse Resistance)
        # Cosine distance < 0.03 (similarity > 0.97) between distinct reporters in last 1 hour
        if embedding is not None and reporter_hash is not None:
            try:
                window_start = datetime.utcnow() - timedelta(hours=1)
                matching_stmt = (
                    select(CitizenReport)
                    .where(
                        CitizenReport.id != report.id,
                        CitizenReport.reported_at >= window_start,
                        CitizenReport.reporter_hash.isnot(None),
                        CitizenReport.reporter_hash != reporter_hash,
                        CitizenReport.embedding.isnot(None),
                        CitizenReport.embedding.cosine_distance(embedding) < 0.03
                    )
                )
                res = await db.execute(matching_stmt)
                scalars_fn = getattr(res, "scalars", None)
                matches = []
                if callable(scalars_fn):
                    s_obj = scalars_fn()
                    import inspect
                    if inspect.iscoroutine(s_obj):
                        s_obj.close()
                    elif hasattr(s_obj, "all") and callable(s_obj.all):
                        all_res = s_obj.all()
                        if inspect.iscoroutine(all_res):
                            all_res.close()
                        elif isinstance(all_res, (list, tuple)):
                            matches = list(all_res)
                elif hasattr(res, "all") and callable(res.all):
                    all_res = res.all()
                    import inspect
                    if inspect.iscoroutine(all_res):
                        all_res.close()
                    elif isinstance(all_res, (list, tuple)):
                        matches = list(all_res)

                if matches:
                    report.flagged_coordinated = True
                    for m in matches:
                        m.flagged_coordinated = True
                    await db.flush()
            except Exception as e:
                logger.warning(f"Coordinated flood check encountered an error: {e}")
        
        if needs_location_confirmation and candidate_region:
            upsert_stmt = pg_insert(PendingIntake).values(
                channel_user_hash=reporter_hash,
                channel=channel,
                partial_report={
                    "report_id": report.id,
                    "tracking_id": tracking_id,
                    "candidate_region_id": candidate_region.id,
                    "candidate_region_name": candidate_region.name,
                    "analysis": analysis
                },
                awaiting="location_confirmation",
                expires_at=datetime.utcnow() + timedelta(hours=1)
            ).on_conflict_do_update(
                index_elements=[PendingIntake.channel_user_hash],
                set_={
                    "channel": channel,
                    "partial_report": {
                        "report_id": report.id,
                        "tracking_id": tracking_id,
                        "candidate_region_id": candidate_region.id,
                        "candidate_region_name": candidate_region.name,
                        "analysis": analysis
                    },
                    "awaiting": "location_confirmation",
                    "expires_at": datetime.utcnow() + timedelta(hours=1)
                }
            )
            await db.execute(upsert_stmt)
            await db.flush()
        elif needs_location_followup:
            # channel_user_hash is PendingIntake's primary key -- one
            # pending conversation per user at a time. A plain insert
            # crashes with a UniqueViolationError if this same user still
            # has an earlier, unanswered location question outstanding
            # (reproduced live: a voice note that itself needed a location
            # follow-up collided with one from a still-unresolved text
            # report). Upsert instead: the newest report needing a
            # location supersedes an older, presumably-forgotten one --
            # only one pending question can be tracked per user regardless,
            # so the most recent context is the more useful one to keep.
            upsert_stmt = pg_insert(PendingIntake).values(
                channel_user_hash=reporter_hash,
                channel=channel,
                partial_report={"report_id": report.id, "tracking_id": tracking_id, "analysis": analysis},
                awaiting="location",
                expires_at=datetime.utcnow() + timedelta(hours=1)
            ).on_conflict_do_update(
                index_elements=[PendingIntake.channel_user_hash],
                set_={
                    "channel": channel,
                    "partial_report": {"report_id": report.id, "tracking_id": tracking_id, "analysis": analysis},
                    "awaiting": "location",
                    "expires_at": datetime.utcnow() + timedelta(hours=1)
                }
            )
            await db.execute(upsert_stmt)
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
            "needs_location_followup": needs_location_followup,
            "needs_location_confirmation": needs_location_confirmation,
            "candidate_region_name": candidate_region.name if candidate_region else None
        }
    except Exception as e:
        logger.error(f"Error persisting citizen message: {e}")
        await db.rollback()
        raise
