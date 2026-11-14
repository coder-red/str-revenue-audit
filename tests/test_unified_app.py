"""Smoke tests: both modes of the unified app render without raising."""

from __future__ import annotations

from pathlib import Path

import pytest

st = pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _run(mode: str, monkeypatch) -> AppTest:
    monkeypatch.setenv("LANDING_MODE", mode)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    return at


def test_unified_audit_mode_renders(monkeypatch):
    at = _run("audit", monkeypatch)
    assert not at.exception


def test_unified_leads_mode_renders(monkeypatch):
    at = _run("leads", monkeypatch)
    assert not at.exception
