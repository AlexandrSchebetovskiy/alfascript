"""
state.py — Shared runtime state and SSE communication layer.

This module owns:
- The mutable application state dict (_state)
- The SSE client queue list (_clients)
- The in-memory log history buffer (_log_history)
- _push() — broadcast a typed message to all connected SSE clients
- _log()  — append a log entry and broadcast it

Everything that needs to read or mutate running state, push SSE events,
or write log entries should import from here. No Flask, no business logic.
"""

import json
import threading
from datetime import datetime
from typing import Any

from src.config import  default_task_states


# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------

_state: dict[str, Any] = {
    "running":      False,
    "cancel":       False,
    "tasks":        default_task_states(),
    "active_preset": "⚡  Полный скрипт",
    "progress":     0,
    "status":       "Готов",
    "status_type":  "idle",
    "test_results": None,
}


# ---------------------------------------------------------------------------
# SSE client queues
# ---------------------------------------------------------------------------

_clients: list = []
_clients_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Log history buffer
# ---------------------------------------------------------------------------

_log_history: list[dict] = []
_LOG_HISTORY_MAX = 2000


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def push(msg_type: str, data: Any) -> None:
    """Broadcast a typed SSE message to all connected clients.

    Silently drops messages for clients whose queues are full or closed.
    """
    payload = json.dumps({"type": msg_type, "data": data}, ensure_ascii=False)
    with _clients_lock:
        clients = list(_clients)
    for q in clients:
        try:
            q.put_nowait(payload)
        except Exception:
            pass


def log(text: str, level: str = "info") -> None:
    """Append a log entry to the history buffer and broadcast it via SSE.

    Args:
        text:  The log message.
        level: Severity tag — one of ``"info"``, ``"ok"``, ``"warn"``,
               ``"err"``, or ``"muted"``.
    """
    ts = datetime.now().strftime("%H:%M:%S")
    entry = {"ts": ts, "text": text, "level": level}

    with _clients_lock:
        _log_history.append(entry)
        if len(_log_history) > _LOG_HISTORY_MAX:
            del _log_history[0]

    push("log", entry)


def add_client(q) -> list[dict]:
    """Register a new SSE client queue and return a snapshot of log history.

    Returns the current log history so the caller can replay it to the
    newly connected client before streaming live events.
    """
    with _clients_lock:
        _clients.append(q)
        snapshot = list(_log_history)
    return snapshot


def remove_client(q) -> None:
    """Deregister an SSE client queue."""
    with _clients_lock:
        if q in _clients:
            _clients.remove(q)


def get_state_snapshot() -> dict[str, Any]:
    """Return a shallow copy of the current state dict.

    Use this when you need a consistent read without holding a lock across
    a slow operation (e.g. building a JSON response).
    """
    return dict(_state)