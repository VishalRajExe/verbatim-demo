"""Streaming citation filter (Architecture §8).

While an answer streams token by token we must drop any ``[Q#]`` marker whose
number is NOT in the verified-quote set (invariant I-3: only verified quotes are
citable). The tricky part is a marker split across tokens (``"["``, ``"Q"``,
``"1]"``), so we hold back any trailing text that could still become a marker
until we know. This is a pure, fully testable state machine.
"""
from __future__ import annotations

import re

_MARKER = re.compile(r"\[Q(\d+)\]")
# A trailing fragment that might still turn into a complete marker.
_PARTIAL = re.compile(r"\[Q?\d*$")


class CitationFilter:
    def __init__(self, verified: set[int]) -> None:
        self.verified = set(verified)
        self._buf = ""

    def feed(self, token: str) -> str:
        """Return the text that is now safe to emit."""
        self._buf += token
        return self._drain(final=False)

    def flush(self) -> str:
        """Emit anything left at end of stream, resolving partial markers."""
        return self._drain(final=True)

    def _drain(self, final: bool) -> str:
        out: list[str] = []
        while True:
            i = self._buf.find("[")
            if i == -1:
                out.append(self._buf)
                self._buf = ""
                break
            out.append(self._buf[:i])
            rest = self._buf[i:]
            m = _MARKER.match(rest)
            if m:
                qid = int(m.group(1))
                if qid in self.verified:
                    out.append(m.group(0))
                # else: silently drop an unverified citation marker.
                self._buf = rest[m.end():]
                continue
            if not final and _PARTIAL.match(rest):
                # Could still become a marker on the next token: hold it.
                break
            # Not a marker (e.g. "[note]") -> emit the bracket literally.
            out.append("[")
            self._buf = rest[1:]
        return "".join(out)
