"""Smoke test: the review queue renders without raising (Streamlit AppTest)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

st = pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest  # noqa: E402


def test_review_queue_renders():
    at = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "leadfinder_app.py"),
                           default_timeout=60)
    at.run()
    assert not at.exception
