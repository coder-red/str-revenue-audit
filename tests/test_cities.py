"""City registry smoke tests — no network, no files."""

from __future__ import annotations

import os

import pytest

from str_audit import cities


def test_registry_has_three_metros_with_distinct_snapshots():
    assert set(cities.CITIES) == {"austin", "dallas", "fort-worth"}
    snaps = {c["snapshot"] for c in cities.CITIES.values()}
    assert len(snaps) == 2  # austin + fort-worth share 2026-09-17; dallas 2026-09-19


def test_label_and_default_data_path(tmp_path, monkeypatch):
    monkeypatch.setenv("STR_CITY", "dallas")
    assert cities.city()["slug"] == "dallas"
    assert cities.label() == "Dallas, TX"
    assert cities.default_data().as_posix().endswith("data/dallas-2026-09-19/listings.csv.gz")
    assert "DALLAS" in cities.metro_line()
    assert "Inside Airbnb — Dallas, TX" in cities.data_source()


def test_fort_worth_round_trip(monkeypatch):
    monkeypatch.setenv("STR_CITY", "fort-worth")
    assert cities.city()["name"] == "Fort Worth"
    assert cities.default_data().as_posix().endswith("data/fort-worth-2026-09-17/listings.csv.gz")


def test_unknown_city_rejected(monkeypatch):
    monkeypatch.setenv("STR_CITY", "mars")
    with pytest.raises(ValueError):
        cities.city()


def test_expense_usd_austin_paths(monkeypatch):
    monkeypatch.setenv("STR_CITY", "austin")
    assert cities.default_data().as_posix().endswith("data/austin-2026-09-17/listings.csv.gz")
    assert cities.label() == "Austin, TX"
