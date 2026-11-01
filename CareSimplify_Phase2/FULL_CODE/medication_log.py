from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any


LOG_PATH = Path(__file__).resolve().parent / "data" / "medication_log.json"


def _read_log() -> dict[str, Any]:
    if not LOG_PATH.exists():
        return {}
    try:
        with LOG_PATH.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_log(log: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = LOG_PATH.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(log, handle, ensure_ascii=False, indent=2)
    temporary.replace(LOG_PATH)


def medicine_id(document_id: str, medicine: dict[str, Any]) -> str:
    """Create a stable, document-scoped ID without storing patient details."""
    identity = "|".join(
        str(medicine.get(field, ""))
        for field in ("name", "dose", "frequency", "duration", "how_to_take_plain")
    )
    raw = f"{document_id}|{identity}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def is_dose_taken(document_id: str, medicine: dict[str, Any], dose_date: date, slot: str) -> bool:
    key = medicine_id(document_id, medicine)
    dose_key = f"{dose_date.isoformat()}|{slot}"
    return bool(_read_log().get(key, {}).get(dose_key, {}).get("taken", False))


def set_dose_taken(
    document_id: str,
    medicine: dict[str, Any],
    dose_date: date,
    slot: str,
    taken: bool,
) -> None:
    log = _read_log()
    key = medicine_id(document_id, medicine)
    dose_key = f"{dose_date.isoformat()}|{slot}"
    if taken:
        log.setdefault(key, {})[dose_key] = {
            "taken": True,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
    else:
        log.get(key, {}).pop(dose_key, None)
        if not log.get(key):
            log.pop(key, None)
    _write_log(log)


def count_taken(document_id: str, medicine: dict[str, Any], doses: list[tuple[date, str]]) -> int:
    return sum(is_dose_taken(document_id, medicine, day, slot) for day, slot in doses)
