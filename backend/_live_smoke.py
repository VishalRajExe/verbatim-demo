"""Live end-to-end smoke against the running backend using the real Gemini key.

Not part of the pytest suite (it needs network + a configured key). Run manually:
    py -3.13 backend/_live_smoke.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from tests.helpers import make_text_pdf  # noqa: E402

BASE = "http://127.0.0.1:8000"

PARAS = [
    "The Customer shall pay all outstanding amounts within 30 days of the invoice date.",
    "The total liability of either party is capped at AED 100,000 per claim year.",
    "Either party may terminate this Agreement by giving 60 days prior written notice.",
    "This Agreement is governed by the laws of the Emirate of Dubai and the UAE.",
]


def main() -> int:
    # Wait for health.
    for _ in range(30):
        try:
            r = httpx.get(f"{BASE}/api/health", timeout=5)
            if r.status_code == 200:
                print("health:", r.json())
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        print("server not ready")
        return 1

    with tempfile.TemporaryDirectory() as d:
        pdf = make_text_pdf(Path(d) / "contract.pdf", PARAS)
        up = httpx.post(
            f"{BASE}/api/documents/upload",
            files={"file": ("contract.pdf", pdf.read_bytes(), "application/pdf")},
            timeout=60,
        )
        print("upload:", up.status_code)
        doc_id = up.json()["id"]
        # Wait for ready.
        for _ in range(30):
            st = httpx.get(f"{BASE}/api/documents/{doc_id}", timeout=10).json()["status"]
            if st == "ready":
                break
            time.sleep(0.5)
        print("status:", st)

        # Stream a grounded question.
        events = []
        with httpx.stream(
            "POST",
            f"{BASE}/api/ask",
            json={"documentIds": [doc_id], "question": "What is the liability cap and the payment term?"},
            timeout=120,
        ) as resp:
            print("ask HTTP:", resp.status_code, resp.headers.get("content-type"))
            assert resp.status_code == 200
            for line in resp.iter_lines():
                if not line:
                    continue
                ev = json.loads(line)
                events.append(ev)

    types = [e["type"] for e in events]
    print("event types:", types)
    quotes = next((e for e in events if e["type"] == "quotes"), {"quotes": []})
    for q in quotes.get("quotes", []):
        print(f"  verified {q['ref']}: p{q.get('pageStart')} [{q.get('start')}-{q.get('end')}] {q['text'][:60]!r}")
    if quotes.get("unverified"):
        for u in quotes["unverified"]:
            print("  UNVERIFIED:", u["text"][:60], "->", u.get("failReason"))
    cov = next((e for e in events if e["type"] == "coverage"), {"coverage": []})
    print("coverage:", [c.get("complete") for c in cov.get("coverage", [])])
    answer = "".join(e["text"] for e in events if e["type"] == "token")
    print("ANSWER:", answer)

    ok = (
        "token" in types
        and types[-1] == "done"
        and quotes.get("quotes")
        and answer.strip()
    )
    print("\nLIVE SMOKE:", "OK" if ok else "FAILED")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
