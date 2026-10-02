"""Manual end-to-end smoke test against a running server (brief §35).

Exercises the live HTTP API exactly as a client would:
    health -> upload -> poll status -> list -> pages -> text -> file -> delete
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import make_docx  # noqa: E402

BASE = "http://127.0.0.1:8000/api"
TERMS = (
    "The Customer shall pay all outstanding amounts within 30 days of invoice. "
    "Late payments accrue interest at four percent per annum."
)
LIABILITY = (
    "Neither party shall be liable for indirect or consequential damages arising "
    "out of this agreement. The total liability cap is AED 100,000."
)


def main() -> int:
    tmp = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    docx = make_docx(tmp / "smoke.docx", [TERMS, LIABILITY], page_breaks=[0])
    doc_id = None
    with httpx.Client(timeout=30.0) as c:
        h = c.get(f"{BASE}/health")
        print("health:", h.status_code, h.json())

        with open(docx, "rb") as fh:
            r = c.post(
                f"{BASE}/documents/upload",
                files={"file": ("smoke.docx", fh, "application/octet-stream")},
            )
        print("upload:", r.status_code, r.json())
        assert r.status_code == 202, r.text
        doc_id = r.json()["id"]

        # Real server runs background processing; poll until terminal state.
        status = None
        for _ in range(40):
            d = c.get(f"{BASE}/documents/{doc_id}").json()
            status = d["status"]
            if status in ("ready", "error"):
                break
            time.sleep(0.25)
        print("final status:", status, "page_count:", d.get("page_count"))
        assert status == "ready", d

        lst = c.get(f"{BASE}/documents").json()
        print("library total:", lst["total"])

        pages = c.get(f"{BASE}/documents/{doc_id}/pages").json()
        print("pages:", pages["total_pages"], "| p2 has cap:",
              "AED 100,000" in pages["pages"][1]["text"])

        file_r = c.get(f"{BASE}/documents/{doc_id}/file")
        print("file fetch:", file_r.status_code, len(file_r.content), "bytes")

        c.delete(f"{BASE}/documents/{doc_id}")
        gone = c.get(f"{BASE}/documents/{doc_id}")
        print("after delete:", gone.status_code)
        assert gone.status_code == 404

    print("\nSMOKE TEST PASSED (live server).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
