from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass
class RouteLogEntry:
    id: int
    timestamp: datetime
    method: str
    path: str
    query: str
    status_code: int
    duration_ms: float
    client_ip: str
    user_id: int | None
    user_agent: str
    level: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "method": self.method,
            "path": self.path,
            "query": self.query,
            "status_code": self.status_code,
            "duration_ms": self.duration_ms,
            "client_ip": self.client_ip,
            "user_id": self.user_id,
            "user_agent": self.user_agent,
            "level": self.level,
            "status": "success" if 200 <= self.status_code < 400 else ("warning" if 400 <= self.status_code < 500 else "failure"),
            "summary": self.summary,
        }

    def to_terminal_line(self) -> str:
        ts_str = self.timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        user_str = f" [user:{self.user_id}]" if self.user_id else ""
        query_str = f"?{self.query}" if self.query else ""
        return (
            f"[{ts_str}] [{self.level:<5}] {self.method:<6} {self.path}{query_str} "
            f"-> {self.status_code} ({self.duration_ms:.1f}ms) from {self.client_ip}{user_str}"
        )


class ServerLogStore:
    """
    In-memory, thread-safe server route and terminal log recorder.
    Enforces a strict 10-minute maximum retention window (nhẹ data, siêu tốc độ).
    """

    def __init__(self, retention_minutes: int = 10) -> None:
        self.retention_minutes = retention_minutes
        self._lock = threading.Lock()
        self._counter = 1000
        self._entries: list[RouteLogEntry] = []
        self._start_time = time.time()
        self._record_boot_log()

    def _record_boot_log(self) -> None:
        """Record real server startup event."""
        now = datetime.now(timezone.utc)
        self._counter += 1
        self._entries.append(
            RouteLogEntry(
                id=self._counter,
                timestamp=now,
                method="SYSTEM",
                path="/api/v1/system/startup",
                query="",
                status_code=200,
                duration_ms=0.5,
                client_ip="127.0.0.1",
                user_id=None,
                user_agent="Interviewly FastApi Daemon",
                level="INFO",
                summary="Server API daemon started successfully (10m memory retention active)",
            )
        )

    def _prune(self) -> None:
        """Discard any log entry older than retention_minutes (10 minutes)."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.retention_minutes)
        self._entries = [e for e in self._entries if e.timestamp >= cutoff]

    def record_route_log(
        self,
        *,
        method: str,
        path: str,
        query: str = "",
        status_code: int,
        duration_ms: float,
        client_ip: str,
        user_agent: str = "-",
        user_id: int | None = None,
    ) -> RouteLogEntry:
        if status_code >= 500:
            level = "ERROR"
        elif status_code >= 400:
            level = "WARN"
        else:
            level = "INFO"

        summary = f"{method} {path} {status_code} ({duration_ms:.1f}ms)"

        entry = RouteLogEntry(
            id=0,
            timestamp=datetime.now(timezone.utc),
            method=method.upper(),
            path=path,
            query=query,
            status_code=status_code,
            duration_ms=duration_ms,
            client_ip=client_ip,
            user_id=user_id,
            user_agent=user_agent,
            level=level,
            summary=summary,
        )

        with self._lock:
            self._counter += 1
            entry.id = self._counter
            self._entries.append(entry)
            self._prune()

        return entry

    def get_route_logs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        level: str | None = None,
        search: str | None = None,
        method: str | None = None,
        status_code: int | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        with self._lock:
            self._prune()
            candidates = list(reversed(self._entries))

        filtered = []
        for e in candidates:
            if level and level.upper() != "ALL" and e.level != level.upper():
                continue
            if method and method.upper() != "ALL" and e.method != method.upper():
                continue
            if status_code is not None and e.status_code != status_code:
                continue
            if search:
                q = search.lower()
                matches = (
                    q in e.path.lower()
                    or q in e.summary.lower()
                    or q in e.client_ip.lower()
                    or (e.user_id and q in str(e.user_id))
                    or q in e.method.lower()
                )
                if not matches:
                    continue
            filtered.append(e)

        total = len(filtered)
        paginated = filtered[offset : offset + limit]
        return [item.to_dict() for item in paginated], total

    def get_terminal_lines(
        self,
        *,
        tail: int = 80,
        level: str | None = None,
    ) -> list[str]:
        with self._lock:
            self._prune()
            entries = list(self._entries)

        if level and level.upper() != "ALL":
            entries = [e for e in entries if e.level == level.upper()]

        recent = entries[-tail:]
        return [e.to_terminal_line() for e in recent]

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            self._prune()
            entries = list(self._entries)

        total = len(entries)
        success = sum(1 for e in entries if 200 <= e.status_code < 400)
        client_err = sum(1 for e in entries if 400 <= e.status_code < 500)
        server_err = sum(1 for e in entries if e.status_code >= 500)
        avg_dur = round(sum(e.duration_ms for e in entries) / total, 1) if total > 0 else 0.0

        return {
            "total_requests": total,
            "success_count": success,
            "client_error_count": client_err,
            "server_error_count": server_err,
            "avg_duration_ms": avg_dur,
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "retention_minutes": self.retention_minutes,
        }


# Singleton instance with 10-minute maximum retention
global_server_log_store = ServerLogStore(retention_minutes=10)