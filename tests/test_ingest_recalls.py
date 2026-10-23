"""Tests for the cleaning step of ingest_recalls.py. These use made-up records, so they need no database or network.

Run with:  .\\venv\\Scripts\\python.exe -m pytest
"""
import logging

from ingest_recalls import build_recalls


def record(number, **extra):
    return {"recall_number": number, "recalling_firm": "Acme", "report_date": "20260101",
            "recall_initiation_date": "20251201", **extra}


def test_repeated_recall_number_keeps_the_first_and_logs_a_warning(caplog):
    records = [record("D-1-2026", status="Ongoing"), record("D-2-2026"), record("D-1-2026", status="Terminated")]
    with caplog.at_level(logging.WARNING, logger="ingest_recalls"):
        df = build_recalls(records)
    assert list(df["recall_number"]) == ["D-1-2026", "D-2-2026"]
    assert df.loc[df["recall_number"] == "D-1-2026", "status"].iloc[0] == "Ongoing"  # the first one was kept
    assert any("D-1-2026" in m and "2 times" in m for m in caplog.messages)


def test_blank_recall_number_is_dropped_with_a_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="ingest_recalls"):
        df = build_recalls([record("D-1-2026"), record("")])
    assert list(df["recall_number"]) == ["D-1-2026"]
    assert any("missing or blank" in m for m in caplog.messages)


def test_clean_data_logs_no_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="ingest_recalls"):
        df = build_recalls([record("D-1-2026"), record("D-2-2026")])
    assert len(df) == 2
    assert caplog.messages == []
