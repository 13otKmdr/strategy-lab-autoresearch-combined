"""Append-only JSONL audit trail for all execution decisions.

Every trade intent, gate check, order state transition, and risk daemon
decision MUST be logged here. The log is never truncated during a session.

Format: one JSON object per line (JSONL).
Each entry has: timestamp, event_type, data.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class AuditLogger:
    """Thread-safe-ish append-only JSONL logger.

    Each call to .log() opens the file in append mode, writes one line,
    and closes the file handle. This is intentionally simple — we prefer
    durability over throughput for audit logs.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event_type: str, data: dict) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "data": data,
        }
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")
