from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from care_plan import timing_from_frequency


def duration_to_days(duration: str) -> int | None:
    """Convert an explicit duration to days; do not infer an unknown duration."""
    value = str(duration or "").lower().strip()
    match = re.search(r"\b(\d+)\s*(days?|d|weeks?|wks?|months?|mos?|years?)\b", value)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit.startswith("w"):
        return amount * 7
    if unit.startswith("month") or unit.startswith("mo"):
        return amount * 30
    if unit.startswith("year"):
        return amount * 365
    return amount


def dose_slots(medicine: dict[str, Any]) -> list[str]:
    """Return slots only where the source notation supports a fixed daily count."""
    frequency = str(medicine.get("frequency") or "").strip().upper()
    numeric = re.search(r"(?<!\d)(\d+(?:-\d+){1,3})(?!\d)", frequency)
    if numeric:
        parts = numeric.group(1).split("-")
        names = (["Morning", "Afternoon", "Night"] if len(parts) == 3 else ["Morning", "Afternoon", "Evening", "Night"])
        slots = []
        for index, amount in enumerate(parts):
            try:
                count = int(amount)
            except ValueError:
                return []
            if count > 1:
                # Preserve the number of prescribed doses without guessing clock times.
                slots.extend([f"{names[index] if index < len(names) else 'Dose'} {n + 1}" for n in range(count)])
            elif count == 1:
                slots.append(names[index] if index < len(names) else f"Dose {index + 1}")
        return slots

    aliases = {
        "OD": 1, "ONCE DAILY": 1,
        "BD": 2, "BID": 2, "TWICE DAILY": 2,
        "TDS": 3, "TID": 3, "THREE TIMES DAILY": 3,
        "QID": 4, "FOUR TIMES DAILY": 4,
    }
    count = aliases.get(frequency)
    if count is None:
        return []
    return [f"Dose {index + 1}" for index in range(count)]


def build_timetable(medicines: list[dict], stop_medicines: list[str] | None = None) -> list[dict]:
    """Build export-friendly medicine summary rows.

    Stop instructions are separate, explicitly labelled STOP rows with no schedule
    fields populated. They must never be mistaken for active doses.
    """
    rows = []
    for med in medicines:
        freq = (med.get("frequency") or "").strip()
        duration = med.get("duration") or "Not specified in extracted text"
        raw = med.get("how_to_take_plain") or ""
        timing = timing_from_frequency(freq, med.get("timing", ""))
        rows.append({
            "Medicine": med.get("name", ""),
            "Dose": med.get("dose", ""),
            "Frequency": freq or "Not confidently extracted — check source",
            "Timing": timing,
            "Duration": duration,
            "Instruction Copied from Source": raw,
        })
    for stop in (stop_medicines or []):
        rows.append({
            "Medicine": str(stop),
            "Dose": "",
            "Frequency": "",
            "Timing": "",
            "Duration": "",
            "Instruction Copied from Source": f"STOP — {stop}",
            "Status": "STOP",
        })
    return rows


def seven_day_dates(start_date: date) -> list[date]:
    return [start_date + timedelta(days=offset) for offset in range(7)]
