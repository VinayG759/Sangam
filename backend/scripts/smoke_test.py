"""
Ten-second check that a deployment works. Run after every deploy.

    python -m scripts.smoke_test https://your-api.onrender.com
    python -m scripts.smoke_test http://localhost:8000

Exits non-zero if any check fails. Needs no credentials; checks that admin
and webhook endpoints REFUSE unauthenticated requests.
"""

import sys
from datetime import datetime, timezone

import httpx


def main(base: str) -> int:
    base = base.rstrip("/")
    client = httpx.Client(base_url=base, timeout=90)  # a sleeping free-tier host can take ~60s to wake
    failures = 0

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        failures += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))

    health = client.get("/health")
    check("health responds", health.status_code == 200, health.text[:80])

    overview = client.get("/api/v1/overview")
    body = overview.json() if overview.status_code == 200 else {}
    check("overview reads the database", overview.status_code == 200 and body.get("reports", {}).get("total", 0) > 0,
          f"{body.get('reports', {}).get('total')} reports")
    run = body.get("run")
    check("a complete analysis run exists", run is not None)
    if run:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(run["completed_at"])
        print(f"INFO  latest run {run['id']} completed {age.total_seconds() / 3600:.1f} hours ago")

    priorities = client.get("/api/v1/priorities?limit=5").json().get("items", [])
    check("priorities have verdicts and summaries", bool(priorities) and all(p["verdict"] and p["summary"] for p in priorities))
    if priorities:
        detail = client.get(f"/api/v1/priorities/{priorities[0]['id']}").json()
        check("top priority has sourced evidence", all(f.get("source_name") for f in detail.get("evidence", [])))
        pdf = client.get(f"/api/v1/priorities/{priorities[0]['id']}/brief.pdf")
        check("PDF brief downloads", pdf.status_code == 200 and pdf.content[:4] == b"%PDF")

    check("admin refuses requests without a token", client.get("/api/v1/admin/runs").status_code == 401)
    check("Telegram webhook refuses requests without the secret",
          client.post("/api/v1/webhooks/telegram", json={}).status_code == 403)
    check("WhatsApp webhook refuses unsigned requests",
          client.post("/api/v1/webhooks/whatsapp", json={}).status_code == 403)

    print(f"\n{'ALL CHECKS PASSED' if not failures else f'{failures} CHECK(S) FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"))
