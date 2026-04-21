"""Tiny HTTP helper with UA, timeout, and JSON/text convenience."""
from __future__ import annotations
import logging
from typing import Any
import requests
from config import HTTP_TIMEOUT_SEC, USER_AGENT

log = logging.getLogger("morning-brief.http")

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})


def get_json(url: str, params: dict | None = None, timeout: int = HTTP_TIMEOUT_SEC) -> Any:
    try:
        r = _SESSION.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning("GET-json failed %s: %s", url, e)
        return None


def get_text(url: str, params: dict | None = None, timeout: int = HTTP_TIMEOUT_SEC) -> str | None:
    try:
        r = _SESSION.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.text
    except Exception as e:
        log.warning("GET-text failed %s: %s", url, e)
        return None
