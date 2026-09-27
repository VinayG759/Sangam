from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core.crypto import decrypt
from app.features.analysis.run import run_analysis
from app.features.impact.service import (
    IMPROVED,
    INSUFFICIENT_DATA,
    NO_CHANGE,
    NOT_REACHING,
    STILL_SHORT,
    WORSENED,
    change_label,
    progress_label,
)
from app.features.intake.service import Inbound, handle_message
from app.features.notify.service import send_updates
from app.models import Contact, Project, Report
from tests.conftest import ADMIN
from tests.helpers import add_quiet_background, add_reports


def report_via_telegram(db, ai, pack, chat_id="555", place="Southmere"):
    ai.places = [place]
    return handle_message(db, ai, pack, Inbound(channel="telegram", sender_id=chat_id, text=f"No water in {place}",
                                                reply_to=chat_id))


# ── Encrypted contacts ──────────────────────────────────────────────────────


def test_chat_id_is_stored_only_encrypted(db, ai, loaded):
    report_via_telegram(db, ai, loaded, chat_id="98450")
    contact = db.scalar(select(Contact))
    assert b"98450" not in contact.address_encrypted
    assert decrypt(contact.address_encrypted) == "98450"
    assert contact.expires_at > datetime.now(timezone.utc) + timedelta(days=179)


def test_no_contact_is_kept_without_an_encryption_key(db, ai, loaded, monkeypatch):
    monkeypatch.setattr("app.features.intake.service.contacts_enabled", lambda: False)
    report_via_telegram(db, ai, loaded)
    assert db.scalar(select(func.count()).select_from(Contact)) == 0


def test_web_reports_keep_no_contact(client, loaded):
    client.post("/api/v1/reports", data={"client_id": "browser-123456", "text": "No water", "region_id": "TL-A-SOUTH"})
    from app.core.db import new_session
    with new_session() as db:
        assert db.scalar(select(func.count()).select_from(Contact)) == 0


# ── Status updates ──────────────────────────────────────────────────────────


def prioritised_south(db, ai, pack):
    add_quiet_background(db)
    add_reports(db, "TL-A-SOUTH", "water", 12)
    outcome = report_via_telegram(db, ai, pack)
    run_analysis(db, ai, pack, pause_seconds=0)
    return outcome.tracking_id


def test_citizen_is_told_once_then_their_chat_id_is_deleted(db, ai, loaded, monkeypatch):
    sent = []
    monkeypatch.setattr("app.core.messaging.send_telegram", lambda chat, text: sent.append((chat, text)) or True)
    tracking = prioritised_south(db, ai, loaded)

    assert send_updates(db, loaded)["sent"] == 1
    chat, text = sent[0]
    assert chat == "555" and tracking in text and "priority list" in text
    assert f"https://sangam.example/track/{tracking}" in text
    assert db.scalar(select(func.count()).select_from(Contact)) == 0

    assert send_updates(db, loaded)["sent"] == 0  # never twice
    assert len(sent) == 1


def test_failed_delivery_is_kept_for_a_retry(db, ai, loaded, monkeypatch):
    monkeypatch.setattr("app.core.messaging.send_telegram", lambda chat, text: False)
    prioritised_south(db, ai, loaded)
    assert send_updates(db, loaded)["failed"] == 1
    assert db.scalar(select(func.count()).select_from(Contact)) == 1


def test_no_update_while_the_place_is_below_the_privacy_floor(db, ai, loaded, monkeypatch):
    sent = []
    monkeypatch.setattr("app.core.messaging.send_telegram", lambda chat, text: sent.append(text) or True)
    add_quiet_background(db)
    report_via_telegram(db, ai, loaded)  # a lone reporter: never shown, so nothing to announce
    run_analysis(db, ai, loaded, pause_seconds=0)
    assert send_updates(db, loaded)["sent"] == 0 and sent == []


def test_whatsapp_updates_wait_for_an_approved_template(db, ai, loaded, monkeypatch):
    calls = []
    monkeypatch.setattr("app.core.messaging.send_whatsapp_template", lambda *a: calls.append(a) or True)
    add_quiet_background(db)
    add_reports(db, "TL-A-SOUTH", "water", 12)
    ai.places = ["Southmere"]
    handle_message(db, ai, loaded, Inbound(channel="whatsapp", sender_id="9199", text="No water", reply_to="9199"))
    run_analysis(db, ai, loaded, pause_seconds=0)

    assert send_updates(db, loaded)["skipped"] == 1 and calls == []

    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "WHATSAPP_NOTIFY_TEMPLATE", "report_update")
    assert send_updates(db, loaded)["sent"] == 1
    to, template, language, params = calls[0]
    assert (to, template) == ("9199", "report_update") and params[0].startswith("SG-")


def test_expired_contacts_are_deleted_unsent(db, ai, loaded):
    report_via_telegram(db, ai, loaded)
    later = datetime.now(timezone.utc) + timedelta(days=181)
    assert send_updates(db, loaded, now=later)["expired_deleted"] == 1
    assert db.scalar(select(func.count()).select_from(Contact)) == 0


def test_notify_endpoint_needs_admin(client, loaded):
    assert client.post("/api/v1/admin/notify").status_code == 401
    assert client.post("/api/v1/admin/notify", headers=ADMIN).status_code == 200


# ── Impact ──────────────────────────────────────────────────────────────────


def test_progress_labels_follow_the_verdict():
    assert progress_label("DELIVERY_GAP") == NOT_REACHING
    assert progress_label("UNSERVED_GAP") == STILL_SHORT
    assert progress_label("MONITOR") == progress_label(None) == "NO_MAJOR_COMPLAINTS"


def test_change_labels():
    assert change_label(20, 8, 5, 0.3) == (IMPROVED, -0.6)
    assert change_label(20, 18, 5, 0.3) == (NO_CHANGE, -0.1)
    assert change_label(10, 15, 5, 0.3) == (WORSENED, 0.5)
    assert change_label(2, 1, 5, 0.3) == (INSUFFICIENT_DATA, None)


def test_programme_progress_joins_official_change_with_residents(client, ai, loaded):
    from app.core.db import new_session
    with new_session() as db:
        add_quiet_background(db)
        add_reports(db, "TL-A-NORTH", "water", 12)  # 90% served on paper, loud → not reaching
        add_reports(db, "TL-A-SOUTH", "water", 12)  # 30% served, loud → still short
        run_analysis(db, ai, loaded, pause_seconds=0)
    body = client.get("/api/v1/impact/progress").json()
    (water,) = body["programmes"]
    rows = {r["region_name"]: r for r in water["rows"]}
    assert rows["Northfield"]["label"] == NOT_REACHING and rows["Northfield"]["change"] == 50
    assert rows["Northfield"]["baseline_period"] == "2019" and rows["Northfield"]["residents_reporting"] == 12
    assert rows["Southmere"]["label"] == STILL_SHORT
    assert rows["Eastbrook"]["label"] == "NO_MAJOR_COMPLAINTS" and rows["Eastbrook"]["residents_reporting"] is None
    assert water["rows"][0]["label"] == NOT_REACHING  # the finding leads
    assert water["source_name"] == "Test statistics office"


def test_project_before_and_after(client, loaded):
    from app.core.db import new_session
    done = date.today() - timedelta(days=200)
    with new_session() as db:
        db.add(Project(id="TL-P2", region_id="TL-A-SOUTH", sector="water", title="Southmere pipeline", amount=1000,
                       currency="TLD", status="completed", completion_date=done, source_name="Test ministry"))
        db.add(Project(id="TL-P3", region_id="TL-A-NORTH", sector="water", title="Too recent", amount=1000,
                       currency="TLD", status="completed", completion_date=date.today() - timedelta(days=10),
                       source_name="Test ministry"))
        db.commit()
        add_reports(db, "TL-A-SOUTH", "water", 20, days_ago=230, prefix="before")  # in the 90 days before
        add_reports(db, "TL-A-SOUTH", "water", 6, days_ago=120, prefix="after")  # in the window after grace
    body = client.get("/api/v1/impact/projects").json()
    rows = {r["project_id"]: r for r in body["projects"]}
    assert body["has_project_data"] is True
    assert rows["TL-P2"]["label"] == IMPROVED and rows["TL-P2"]["reporters_before"] == 20
    assert rows["TL-P2"]["reporters_after"] == 6
    assert rows["TL-P3"]["label"] == "TOO_EARLY" and rows["TL-P3"]["reporters_before"] is None
