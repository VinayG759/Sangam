from sqlalchemy import func, select

from app.features.intake.service import Inbound, handle_message, reprocess_pending
from app.models import Conversation, Report, ReportMedia


def send(db, ai, pack, text=None, sender="citizen-1", **kw):
    return handle_message(db, ai, pack, Inbound(channel="telegram", sender_id=sender, text=text, **kw))


def only_report(db) -> Report:
    (report,) = db.scalars(select(Report)).all()
    db.refresh(report)
    return report


def test_clear_place_name_is_located_immediately(db, ai, loaded):
    ai.places = ["Riverton"]
    outcome = send(db, ai, loaded, "No water in Riverton for a week")
    report = only_report(db)
    assert report.status == "located" and report.region_id == "TL-A-NORTH-RIVERTON"
    assert report.location_method == "text" and report.embedding is not None
    assert outcome.tracking_id == report.tracking_id and "Riverton" in outcome.reply


def test_raw_sender_id_is_never_stored(db, ai, loaded):
    ai.places = ["Riverton"]
    send(db, ai, loaded, "No water", sender="+919845012345")
    report = only_report(db)
    assert "9845012345" not in report.reporter_hash


def test_phone_number_in_message_is_redacted_before_storage(db, ai, loaded):
    ai.places = ["Riverton"]
    send(db, ai, loaded, "No water. Call 98450 12345")
    report = only_report(db)
    assert "12345" not in report.text_original and "12345" not in report.text_en


def test_weak_match_asks_to_confirm_then_yes_locates(db, ai, loaded):
    ai.places = ["Riverdon"]  # speech-to-text slip; scores 87.5
    outcome = send(db, ai, loaded, "No water in Riverdon")
    assert "Did you mean Riverton?" in outcome.reply
    assert only_report(db).status == "needs_confirmation"

    outcome = send(db, ai, loaded, "yes")
    report = only_report(db)
    assert report.status == "located" and report.region_id == "TL-A-NORTH-RIVERTON"
    assert report.location_confidence == 100.0
    assert db.scalar(select(func.count()).select_from(Conversation)) == 0


def test_missing_place_asks_once_and_accepts_a_typed_answer(db, ai, loaded):
    outcome = send(db, ai, loaded, "No water since Monday")
    assert "Which village, town or county" in outcome.reply  # wording comes from the pack
    send(db, ai, loaded, "Southmere")
    report = only_report(db)
    assert report.status == "located" and report.region_id == "TL-A-SOUTH"


def test_shared_gps_location_answers_the_question(db, ai, loaded):
    send(db, ai, loaded, "No water since Monday")
    send(db, ai, loaded, lat=12.04, lon=77.04)
    assert only_report(db).region_id == "TL-A-NORTH-RIVERTON"


def test_gives_up_after_two_failed_answers_but_keeps_the_report(db, ai, loaded):
    send(db, ai, loaded, "No water")
    send(db, ai, loaded, "qqqq zzzz")
    send(db, ai, loaded, "xxxx yyyy")
    outcome = send(db, ai, loaded, "wwww vvvv")
    assert "saved and counted" in outcome.reply
    assert only_report(db).status == "unlocated"


def test_gemini_outage_still_stores_and_replies_then_reprocess_finishes(db, ai, loaded):
    ai.down = True
    outcome = send(db, ai, loaded, "Road broken near Lakeside", media=b"voice", mime_type="audio/ogg")
    report = only_report(db)
    assert outcome.tracking_id and "process your report shortly" in outcome.reply
    assert report.status == "received" and report.embedding is None  # NULL, never zeros
    assert db.get(ReportMedia, report.id) is not None

    ai.down, ai.sector, ai.places = False, "road", ["Lakeside"]
    assert reprocess_pending(db, ai, loaded)["processed"] == 1
    report = only_report(db)
    assert report.status == "located" and report.sector == "road" and report.embedding is not None
    assert db.get(ReportMedia, report.id) is None  # raw audio deleted once understood


def test_reprocess_stops_cleanly_while_gemini_is_still_down(db, ai, loaded):
    ai.down = True
    send(db, ai, loaded, "No water")
    assert reprocess_pending(db, ai, loaded) == {"processed": 0, "failed": 1, "remaining": 1}


def test_daily_cap_refuses_extra_reports(db, ai, loaded):
    ai.places = ["Riverton"]
    for _ in range(3):
        send(db, ai, loaded, "No water in Riverton")
    outcome = send(db, ai, loaded, "No water in Riverton")
    assert "many reports today" in outcome.reply
    assert db.scalar(select(func.count()).select_from(Report)) == 3


def test_greeting_is_not_stored(db, ai, loaded):
    ai.actionable = False
    outcome = send(db, ai, loaded, "hello")
    assert "Please describe the problem" in outcome.reply
    assert db.scalar(select(func.count()).select_from(Report)) == 0


def test_identical_messages_from_many_people_are_flagged(db, ai, loaded):
    ai.places = ["Riverton"]
    for person in range(3):
        send(db, ai, loaded, "Vote for X: no water in Riverton", sender=f"bot-{person}")
    flagged = db.scalar(select(func.count()).select_from(Report).where(Report.flagged_coordinated.is_(True)))
    assert flagged == 3


def test_local_need_label_is_used_in_reply(db, ai, loaded):
    ai.places, ai.language = ["Riverton"], "xx"
    assert "Wasser" in send(db, ai, loaded, "kein Wasser").reply


def test_giving_up_records_why(db, ai, loaded):
    send(db, ai, loaded, "No water")
    for answer in ["qqqq zzzz", "xxxx yyyy", "wwww vvvv"]:
        send(db, ai, loaded, answer)
    assert only_report(db).location_failure == "gave_up_after_questions"


def test_reprocessed_report_without_a_place_records_why(db, ai, loaded):
    ai.down = True
    send(db, ai, loaded, "No water")
    ai.down = False
    reprocess_pending(db, ai, loaded)
    report = only_report(db)
    assert report.status == "unlocated" and report.location_failure == "no_place_named"


def test_reprocessed_report_with_an_unknown_place_records_why(db, ai, loaded):
    ai.down = True
    send(db, ai, loaded, "No water in Qzxwv")
    ai.down, ai.places = False, ["Qzxwv"]
    reprocess_pending(db, ai, loaded)
    report = only_report(db)
    assert report.status == "unlocated" and report.location_failure == "place_not_recognised"


# ── Voice notes: speech service first, Gemini as fallback ───────────────────


def _record_calls(ai):
    calls = []
    original = ai.understand

    def spy(pack, text, media, mime_type):
        calls.append({"text": text, "media": media, "mime_type": mime_type})
        return original(pack, text, media, mime_type)

    ai.understand = spy
    return calls


def test_voice_note_is_transcribed_then_understood_as_text(db, ai, loaded, monkeypatch):
    from app.core.speech import Heard

    heard = []
    monkeypatch.setattr("app.features.intake.service.transcribe",
                        lambda audio, mime: heard.append(mime) or Heard("ಹೊನ್ನಾವರದಲ್ಲಿ ರಸ್ತೆ ಹಾಳಾಗಿದೆ", "kn"))
    calls = _record_calls(ai)
    ai.places = ["Riverton"]
    send(db, ai, loaded, None, media=b"voice", mime_type="audio/ogg")
    assert heard == ["audio/ogg"]
    assert calls[0]["media"] is None and "ಹೊನ್ನಾವರದಲ್ಲಿ ರಸ್ತೆ ಹಾಳಾಗಿದೆ" in calls[0]["text"]
    assert only_report(db).language == "kn"  # the speech service's detection wins


def test_voice_note_falls_back_to_gemini_listening_when_speech_fails(db, ai, loaded, monkeypatch):
    monkeypatch.setattr("app.features.intake.service.transcribe", lambda audio, mime: None)
    calls = _record_calls(ai)
    ai.places = ["Riverton"]
    send(db, ai, loaded, None, media=b"voice", mime_type="audio/webm")
    assert calls[0]["media"] == b"voice" and calls[0]["mime_type"] == "audio/webm"
    assert only_report(db).status == "located"


def test_photos_never_go_to_the_speech_service(db, ai, loaded, monkeypatch):
    monkeypatch.setattr("app.features.intake.service.transcribe",
                        lambda audio, mime: (_ for _ in ()).throw(AssertionError("photo sent to speech")))
    ai.places = ["Riverton"]
    send(db, ai, loaded, "broken road", media=b"jpeg", mime_type="image/jpeg")
    assert only_report(db).status == "located"


def test_speech_service_is_off_without_a_key():
    from app.core.speech import speech_enabled, transcribe

    assert speech_enabled() is False and transcribe(b"voice", "audio/ogg") is None
