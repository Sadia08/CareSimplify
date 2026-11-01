import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from care_plan import extract_candidate_plan, build_plain_text, readability_score
from timetable import build_timetable

def test_extracts_explicit_dose_frequency_duration():
    text = """DISCHARGE MEDICATIONS:
- Tab. Labetalol 100 mg PO BD till next visit

FOLLOW-UP:
- Review on 05/11/2026 with clinic
"""
    plan = extract_candidate_plan(text)
    assert len(plan["medicines"]) == 1
    assert "100 mg" in plan["medicines"][0]["dose"]
    assert plan["medicines"][0]["frequency"] == "BD"
    assert plan["medicines"][0]["timing"] == "Twice daily (exact times not specified)"
    assert len(plan["follow_ups"]) == 1

def test_sos_not_scheduled_at_clock_time():
    rows = build_timetable([{"name":"Paracetamol","dose":"650 mg","frequency":"SOS","duration":"","how_to_take_plain":"only when needed"}])
    assert rows[0]["Frequency"] == "SOS"
    assert rows[0]["Timing"] == "Only when needed, as prescribed"

def test_missing_frequency_is_flagged():
    rows = build_timetable([{"name":"Medicine","dose":"5 mg","frequency":"","duration":"","how_to_take_plain":""}])
    assert "Not confidently extracted" in rows[0]["Frequency"]
    assert "Timing not specified" in rows[0]["Timing"]

def test_readability_returns_number():
    assert isinstance(readability_score("This is a short sentence.")["grade"], float)


def test_telugu_fridge_sheet_uses_telugu_labels():
    from io import BytesIO
    from pypdf import PdfReader
    from exports import make_fridge_pdf

    plan = {
        "medicines": [{"name": "Paracetamol", "dose": "650 mg", "frequency": "1-1-1", "duration": "5 days"}],
        "stop_medicines": ["Metformin 500 mg"],
        "warning_signs": ["Fever above 100.4 F (38 C)"],
        "diet": ["Avoid sugar and sweets; keep a healthy weight"],
        "activity": ["Gradually increase walking as tolerated"],
        "other_advice": [],
        "follow_ups": [{"date": "05/11/2026", "with_whom": "clinic", "purpose": "Review"}],
    }
    pdf = make_fridge_pdf(plan, "Telugu (conservative draft)")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)
    assert "మందులు" in text
    assert "హెచ్చరిక లక్షణాలు" in text
    assert "ఆహారం" in text
    assert "Paracetamol" in text  # Preserve medicine names exactly.


def test_numeric_schedule_expands_into_day_parts():
    from care_plan import timing_from_frequency
    assert timing_from_frequency("1-1-1") == "Morning, afternoon and night"
    assert timing_from_frequency("1-0-1") == "Morning and night"


def test_telugu_translation_translates_timing_value():
    from care_plan import translate_telugu_conservative
    translated = translate_telugu_conservative("Timing: Morning, afternoon and night")
    assert "ఉదయం, మధ్యాహ్నం మరియు రాత్రి" in translated


def test_duration_to_days_handles_months_and_unknown():
    from timetable import duration_to_days
    assert duration_to_days("for 5 days") == 5
    assert duration_to_days("for 6 months") == 180
    assert duration_to_days("till next visit") is None


def test_dose_slots_preserve_explicit_numeric_schedule():
    from timetable import dose_slots
    assert dose_slots({"frequency": "1-1-1"}) == ["Morning", "Afternoon", "Night"]
    assert dose_slots({"frequency": "1-0-1"}) == ["Morning", "Night"]
    assert dose_slots({"frequency": "BD"}) == ["Dose 1", "Dose 2"]
    assert dose_slots({"frequency": "SOS"}) == []


def test_medication_log_persists_and_can_be_unticked(tmp_path, monkeypatch):
    from datetime import date
    import medication_log

    monkeypatch.setattr(medication_log, "LOG_PATH", tmp_path / "medication_log.json")
    med = {"name": "Sample", "dose": "1 tablet", "frequency": "1-0-0", "duration": "5 days"}
    day = date(2026, 10, 30)
    assert not medication_log.is_dose_taken("doc123", med, day, "Morning")
    medication_log.set_dose_taken("doc123", med, day, "Morning", True)
    assert medication_log.is_dose_taken("doc123", med, day, "Morning")
    medication_log.set_dose_taken("doc123", med, day, "Morning", False)
    assert not medication_log.is_dose_taken("doc123", med, day, "Morning")
