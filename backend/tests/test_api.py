import hashlib
import hmac
import io
import json

from pypdf import PdfReader
from sqlalchemy import select

from app.core.db import new_session
from app.features.analysis.run import run_analysis
from app.models import Report
from tests.conftest import ADMIN
from tests.helpers import add_quiet_background, add_reports


def analysed(ai, pack):
    with new_session() as db:
        add_quiet_background(db)
        add_reports(db, "TL-A-SOUTH", "water", 12)
        add_reports(db, "TL-A-NORTH", "water", 12)
        add_reports(db, "TL-A-EAST", "water", 12)
        add_reports(db, "TL-A-NORTH-RIVERTON", "water", 3)
        add_reports(db, "TL-A-EAST", "road", 2)
        run_analysis(db, ai, pack, pause_seconds=0)


# ── Security boundaries ─────────────────────────────────────────────────────


def test_admin_routes_need_the_token(client, loaded):
    assert client.get("/api/v1/admin/runs").status_code == 401
    assert client.get("/api/v1/admin/runs", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/v1/admin/runs", headers=ADMIN).status_code == 200


def test_telegram_webhook_rejects_requests_without_the_secret(client, loaded):
    assert client.post("/api/v1/webhooks/telegram", json={}).status_code == 403
    response = client.post("/api/v1/webhooks/telegram", json={},
                           headers={"X-Telegram-Bot-Api-Secret-Token": "guess"})
    assert response.status_code == 403


def test_telegram_message_with_secret_is_processed_and_answered(client, ai, loaded, monkeypatch):
    sent = []
    monkeypatch.setattr("app.features.intake.telegram.send", lambda chat, text: sent.append((chat, text)))
    ai.places = ["Riverton"]
    update = {"message": {"chat": {"id": 7}, "from": {"id": 7}, "text": "No water in Riverton"}}
    response = client.post("/api/v1/webhooks/telegram", json=update,
                           headers={"X-Telegram-Bot-Api-Secret-Token": "test-telegram-secret"})
    assert response.status_code == 200
    assert sent and sent[0][0] == 7 and "Tracking ID" in sent[0][1]


def test_whatsapp_verification_handshake(client):
    ok = client.get("/api/v1/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "test-verify-token",
                                                         "hub.challenge": "12345"})
    assert ok.status_code == 200 and ok.text == "12345"
    assert client.get("/api/v1/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "no",
                                                           "hub.challenge": "1"}).status_code == 403


def test_whatsapp_webhook_checks_the_signature(client, ai, loaded, monkeypatch):
    sent = []
    monkeypatch.setattr("app.features.intake.whatsapp.send", lambda to, text: sent.append((to, text)))
    ai.places = ["Southmere"]
    body = json.dumps({"entry": [{"changes": [{"value": {"messages": [
        {"from": "919900000000", "type": "text", "text": {"body": "No water in Southmere"}}]}}]}]}).encode()
    assert client.post("/api/v1/webhooks/whatsapp", content=body,
                       headers={"X-Hub-Signature-256": "sha256=bad"}).status_code == 403
    signature = "sha256=" + hmac.new(b"test-app-secret", body, hashlib.sha256).hexdigest()
    response = client.post("/api/v1/webhooks/whatsapp", content=body,
                           headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"})
    assert response.status_code == 200 and "Tracking ID" in sent[0][1]


def test_cors_allows_only_configured_origins(client):
    allowed = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    blocked = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in blocked.headers


# ── Web intake and tracking ─────────────────────────────────────────────────


def test_web_report_with_place_picker(client, ai, loaded):
    response = client.post("/api/v1/reports", data={"client_id": "browser-123456", "text": "No water",
                                                    "region_id": "TL-A-SOUTH"})
    body = response.json()
    assert response.status_code == 200 and body["region_name"] == "Southmere" and body["status"] == "located"
    track = client.get(f"/api/v1/track/{body['tracking_id'].lower()}").json()
    assert track["stage"] == "located" and track["region_name"] == "Southmere"


def test_web_report_needs_a_description_and_a_place(client, loaded):
    no_text = client.post("/api/v1/reports", data={"client_id": "browser-123456", "region_id": "TL-A-SOUTH"})
    no_place = client.post("/api/v1/reports", data={"client_id": "browser-123456", "text": "No water"})
    bad_file = client.post("/api/v1/reports", data={"client_id": "browser-123456", "region_id": "TL-A-SOUTH"},
                           files={"file": ("x.pdf", b"%PDF", "application/pdf")})
    assert (no_text.status_code, no_place.status_code, bad_file.status_code) == (422, 422, 422)


def test_web_report_accepts_a_voice_note(client, ai, loaded):
    response = client.post("/api/v1/reports", data={"client_id": "browser-123456", "region_id": "TL-A-SOUTH"},
                           files={"file": ("note.webm", b"voice-bytes", "audio/webm")})
    assert response.status_code == 200
    with new_session() as db:
        assert db.scalar(select(Report)).has_media is True


def test_tracking_shows_when_a_report_has_been_prioritised(client, ai, loaded):
    receipt = client.post("/api/v1/reports", data={"client_id": "browser-123456", "text": "No water",
                                                   "region_id": "TL-A-SOUTH"}).json()
    analysed(ai, loaded)
    track = client.get(f"/api/v1/track/{receipt['tracking_id']}").json()
    assert track["stage"] == "prioritised" and track["verdict"] == "UNSERVED_GAP" and track["rank"] >= 1


def test_unknown_tracking_id_is_404(client, loaded):
    assert client.get("/api/v1/track/SG-NOPE00").status_code == 404


# ── Dashboard reads ─────────────────────────────────────────────────────────


def test_dashboard_is_empty_but_healthy_before_any_run(client, loaded):
    assert client.get("/api/v1/priorities").json() == {"run": None, "items": []}
    assert client.get("/api/v1/overview").json()["run"] is None
    assert client.get("/api/v1/map").json() == []


def test_priorities_hide_groups_below_the_privacy_floor(client, ai, loaded):
    analysed(ai, loaded)
    items = client.get("/api/v1/priorities").json()["items"]
    assert ("TL-A-EAST", "road") not in {(i["region"]["id"], i["sector"]) for i in items}
    assert [i["rank"] for i in items] == sorted(i["rank"] for i in items)
    riverton = next(i for i in items if i["region"]["id"] == "TL-A-NORTH-RIVERTON")
    assert riverton["region"]["parent_name"] == "Northfield" and riverton["region"]["level_name"] == "block"


def test_priority_filters_and_search(client, ai, loaded):
    analysed(ai, loaded)
    stalled = client.get("/api/v1/priorities", params={"verdict": "STALLED_ALLOCATION"}).json()["items"]
    assert [i["region"]["name"] for i in stalled] == ["Eastbrook"]
    found = client.get("/api/v1/priorities", params={"q": "northf"}).json()["items"]
    assert {i["region"]["name"] for i in found} == {"Northfield", "Riverton"}


def test_priority_detail_evidence_and_sources(client, ai, loaded):
    analysed(ai, loaded)
    first = client.get("/api/v1/priorities").json()["items"][0]
    detail = client.get(f"/api/v1/priorities/{first['id']}").json()
    assert detail["components"] and detail["evidence"][0]["id"] == "F1"
    sources = client.get(f"/api/v1/priorities/{first['id']}/reports").json()
    assert sources and "reporter_hash" not in sources[0] and "tracking_id" not in sources[0]


def test_hidden_priority_cannot_be_fetched_by_id(client, ai, loaded):
    analysed(ai, loaded)
    with new_session() as db:
        from app.models import Priority
        hidden = db.scalar(select(Priority).where(Priority.displayable.is_(False)))
    assert client.get(f"/api/v1/priorities/{hidden.id}").status_code == 404
    assert client.get(f"/api/v1/priorities/{hidden.id}/reports").status_code == 404
    assert client.get(f"/api/v1/priorities/{hidden.id}/brief.pdf").status_code == 404


def test_reports_list_only_shows_reports_above_the_floor(client, ai, loaded):
    analysed(ai, loaded)
    body = client.get("/api/v1/reports").json()
    assert body["total"] == 39  # 12 + 12 + 12 + 3; the 2 road reports in Eastbrook are hidden
    assert all(item["sector"] == "water" for item in body["items"])


def test_overview_counts(client, ai, loaded):
    analysed(ai, loaded)
    body = client.get("/api/v1/overview").json()
    assert body["reports"]["total"] == 49 and body["run"] is not None
    assert body["verdicts"] == {"UNSERVED_GAP": 1, "DELIVERY_GAP": 1, "STALLED_ALLOCATION": 1, "MONITOR": 1}


def test_map_uses_parent_location_when_a_place_has_none(client, ai, loaded):
    with new_session() as db:
        add_reports(db, "TL-A-NORTH-HILLVIEW", "water", 3)
    analysed(ai, loaded)
    points = {p["region_name"]: p for p in client.get("/api/v1/map").json()}
    assert points["Hillview"]["approximate"] is True and points["Hillview"]["lat"] == 12.0
    assert points["Riverton"]["approximate"] is False


def test_simulator_funds_only_unserved_gaps_within_budget(client, ai, loaded):
    analysed(ai, loaded)
    small = client.post("/api/v1/simulate", json={"budget": 100_000}).json()
    assert small["funded"] == [] and small["candidates"] == 1
    big = client.post("/api/v1/simulate", json={"budget": 1_000_000, "strategy": "reach"}).json()
    assert [f["region_name"] for f in big["funded"]] == ["Southmere"]
    assert big["total_cost"] == 700_000 and big["beneficiaries"] == 700 and big["audit_count"] == 2
    assert client.post("/api/v1/simulate", json={"budget": -1}).status_code == 422


def test_brief_pdf_contains_evidence_and_sources(client, ai, loaded):
    analysed(ai, loaded)
    first = client.get("/api/v1/priorities").json()["items"][0]
    response = client.get(f"/api/v1/priorities/{first['id']}/brief.pdf")
    assert response.headers["content-type"] == "application/pdf"
    text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages)
    assert "Evidence" in text and "Test statistics office" in text and "synthetic" not in text


def test_pack_endpoint_describes_the_country(client, loaded):
    body = client.get("/api/v1/pack").json()
    assert body["country_code"] == "TL" and [n["key"] for n in body["needs"]] == ["water", "road"]
    regions = client.get("/api/v1/regions").json()
    assert {"id": "TL-A-NORTH-RIVERTON", "name": "Riverton", "level": 3, "parent_id": "TL-A-NORTH"} in regions


def test_admin_can_start_a_run(client, loaded):
    response = client.post("/api/v1/admin/runs", headers=ADMIN)
    assert response.status_code == 202
    runs = client.get("/api/v1/admin/runs", headers=ADMIN).json()
    assert runs[0]["id"] == response.json()["run_id"] and runs[0]["status"] == "complete"
