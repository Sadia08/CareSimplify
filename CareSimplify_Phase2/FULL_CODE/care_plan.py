from __future__ import annotations
import re
from typing import Any


def timing_from_frequency(frequency: str, source_timing: str = "") -> str:
    """Return a cautious patient-friendly timing phrase from source notation.

    Numeric schedules are expanded into day-parts. OD/BD/TDS/QID only state
    frequency, so they are not converted into invented clock times.
    """
    source_timing = str(source_timing or "").strip()
    if source_timing:
        return source_timing
    value = re.sub(r"\s+", "", str(frequency or "").upper())
    numeric = {
        "1-0-0": "Morning",
        "0-1-0": "Afternoon",
        "0-0-1": "Night",
        "1-1-0": "Morning and afternoon",
        "1-0-1": "Morning and night",
        "0-1-1": "Afternoon and night",
        "1-1-1": "Morning, afternoon and night",
        "1-1-1-1": "Morning, afternoon, evening and night",
    }
    if value in numeric:
        return numeric[value]
    generic = {
        "OD": "Once daily (exact time not specified)",
        "ONCE DAILY": "Once daily (exact time not specified)",
        "BD": "Twice daily (exact times not specified)",
        "BID": "Twice daily (exact times not specified)",
        "TDS": "Three times daily (exact times not specified)",
        "TID": "Three times daily (exact times not specified)",
        "QID": "Four times daily (exact times not specified)",
        "SOS": "Only when needed, as prescribed",
        "PRN": "Only when needed, as prescribed",
        "HS": "At bedtime",
        "STAT": "Immediately, as prescribed",
    }
    return generic.get(value, "Timing not specified — check prescription")


MED_HEADINGS = [
    "DISCHARGE MEDICATIONS", "Rx on discharge", "Medications at Discharge",
    "TREATMENT ADVISED ON DISCHARGE", "ADV ON DISCHARGE", "MEDICINES AT DISCHARGE"
]
WARN_HEADINGS = [
    "RETURN TO EMERGENCY", "Report immediately", "Danger signs",
    "COME BACK TO THE HOSPITAL", "RETURN TO HOSPITAL", "GO TO HOSPITAL IMMEDIATELY"
]
FU_HEADINGS = ["FOLLOW-UP", "F/U", "Follow-up", "Follow up", "REVIEW"]
DIET_HEADINGS = ["Diet:"]
ACTIVITY_HEADINGS = ["Activity:"]

def _section(lines: list[str], headings: list[str]) -> list[str]:
    for i, line in enumerate(lines):
        if any(line.strip().lower().startswith(h.lower()) for h in headings):
            out = []
            for next_line in lines[i + 1:]:
                s = next_line.strip()
                if not s:
                    if out: break
                    continue
                if not s.startswith(("•", "-", "*", "·")) and not re.match(r"^\d+[.)]\s", s):
                    if out: break
                out.append(s)
            return out
    return []

def _clean(line: str) -> str:
    return re.sub(r"^\s*(?:[-•*·]\s*|\d+[.)]\s*)", "", line).strip()

def _frequency(line: str) -> str:
    patterns = [
        r"\b(?:OD|BD|TDS|QID|HS|SOS|PRN|STAT)\b",
        r"\b(?:once|twice|three times|four times)\s+(?:a|per)\s+day\b",
        r"\b\d+\s*-\s*\d+\s*-\s*\d+\b",
        r"\bonce weekly\b|\bonce a week\b"
    ]
    for pat in patterns:
        m = re.search(pat, line, re.I)
        if m: return m.group(0)
    return ""

def _dose(line: str) -> str:
    m = re.search(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|units?|IU|ml|mL|puffs?|tablets?|tabs?|capsules?|drops?)\b", line, re.I)
    if m: return re.sub(r"\s+", " ", m.group(0))
    return ""

def _duration(line: str) -> str:
    pats = [
        r"\b(?:for|x)\s*\d+\s*(?:days?|d|weeks?|wks?|months?|\/\s*12|years?)\b",
        r"\b(?:till|until)\s+(?:the\s+)?(?:next\s+)?(?:visit|review|check[- ]?up)\b",
        r"\blifelong\b"
    ]
    for p in pats:
        m = re.search(p, line, re.I)
        if m:
            value = m.group(0)
            value = re.sub(r"^x\s*", "for ", value, flags=re.I)
            value = re.sub(r"/\s*12", " months", value, flags=re.I)
            return value
    return ""

def extract_candidate_plan(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    meds, stops = [], []
    in_meds = False
    for line in lines:
        s = line.strip()
        if any(s.lower().startswith(h.lower()) for h in MED_HEADINGS):
            in_meds = True
            continue
        if in_meds and s and (s.endswith(":") or any(s.lower().startswith(h.lower()) for h in WARN_HEADINGS + FU_HEADINGS + ["Instructions", "Diet:", "Activity:", "Others:"])):
            in_meds = False
        if in_meds:
            if s.startswith("|"):
                cells = [x.strip() for x in s.strip("|").split("|")]
                if len(cells) >= 4 and cells[0].lower() not in ("no", "s.no", "sr no"):
                    meds.append({"name": cells[1], "dose": cells[2], "frequency": cells[4] if len(cells)>4 else "", "timing": timing_from_frequency(cells[4] if len(cells)>4 else "", cells[6] if len(cells)>6 else ""), "duration": cells[5] if len(cells)>5 else "", "how_to_take_plain": s})
            elif re.match(r"^(?:[-•*·]|\d+[.)])\s*", s):
                raw = _clean(s)
                if raw.upper().startswith("STOP "):
                    stops.append(raw[5:].strip())
                    continue
                # Candidate only: keep entire original instruction to avoid dropping modifiers.
                name = re.split(r"\s+(?:\d+(?:\.\d+)?\s*(?:mg|mcg|g|units?|IU|ml|mL)|PO\b)", raw, maxsplit=1, flags=re.I)[0].strip()
                freq = _frequency(raw)
                meds.append({"name": name, "dose": _dose(raw), "frequency": freq, "timing": timing_from_frequency(freq), "duration": _duration(raw), "how_to_take_plain": raw})
    # Also collect explicit stop lines outside the medication section.
    for line in lines:
        s = _clean(line)
        if re.match(r"^STOP\s+", s, re.I):
            stops.append(re.sub(r"^STOP\s+", "", s, flags=re.I))
    # Deduplicate while preserving order.
    seen = set()
    meds = [m for m in meds if not (m["how_to_take_plain"].lower() in seen or seen.add(m["how_to_take_plain"].lower()))]
    stops = list(dict.fromkeys(stops))
    warnings = [_clean(x) for x in _section(lines, WARN_HEADINGS)]
    diet = [_clean(x) for x in _section(lines, DIET_HEADINGS)]
    activity = [_clean(x) for x in _section(lines, ACTIVITY_HEADINGS)]
    other = []
    for line in lines:
        s = _clean(line)
        if re.match(r"^(?:Check BP|Check blood pressure|Exclusive breastfeeding|Feed the baby|Maintain a chart)", s, re.I):
            other.append(s)
    fu_lines = _section(lines, FU_HEADINGS)
    follow_ups = []
    for line in fu_lines:
        date_match = re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b|\b\d{1,2}-[A-Za-z]{3}-\d{2}\b|\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b", line)
        follow_ups.append({"date": date_match.group(0) if date_match else "", "with_whom": "", "purpose": _clean(line)})
    return {"medicines": meds, "stop_medicines": stops, "warning_signs": warnings, "diet": diet, "activity": activity, "follow_ups": follow_ups, "other_advice": other}

def build_plain_text(plan: dict[str, Any]) -> str:
    out = ["MY CARE PLAN", "", "YOUR MEDICINES — follow the discharge summary exactly"]
    for i, m in enumerate(plan.get("medicines", []), 1):
        out += [f"{i}. {m.get('name','')}".strip(), f"   Dose: {m.get('dose') or 'Not confidently extracted — check the source'}",
                f"   Frequency: {m.get('frequency') or 'Not confidently extracted — check the source'}"]
        if m.get("timing"): out.append(f"   Timing: {m['timing']}")
        if m.get("duration"): out.append(f"   Duration: {m['duration']}")
        out.append(f"   Source instruction: {m.get('how_to_take_plain','')}")
    out += ["", "MEDICINES TO STOP"]
    out += [f"- STOP {x}" for x in plan.get("stop_medicines", [])] or ["- No stop instruction was confidently extracted. Check the original summary."]
    for title, key in [("WARNING SIGNS — SEEK URGENT CARE AS WRITTEN IN YOUR SUMMARY", "warning_signs"), ("FOOD / DIET", "diet"), ("ACTIVITY", "activity"), ("OTHER ADVICE", "other_advice")]:
        out += ["", title]
        out += [f"- {x}" for x in plan.get(key, [])] or ["- No instruction confidently extracted. Check the original summary."]
    out += ["", "FOLLOW-UP"]
    out += [f"- {x.get('date','')} {x.get('with_whom','')} {x.get('purpose','')}".strip() for x in plan.get("follow_ups", [])] or ["- No follow-up confidently extracted. Check the original summary."]
    out += ["", "IMPORTANT: This is a draft generated from extracted text. Confirm every item with the original discharge summary and care team."]
    return "\n".join(out)

def readability_score(text: str) -> dict[str, float]:
    words = re.findall(r"[A-Za-z]+", text)
    sentences = max(1, len(re.findall(r"[.!?]+", text)))
    syllables = 0
    for word in words:
        w = word.lower()
        groups = len(re.findall(r"[aeiouy]+", w))
        if w.endswith("e") and groups > 1: groups -= 1
        syllables += max(1, groups)
    n = max(1, len(words))
    grade = 0.39 * (n / sentences) + 11.8 * (syllables / n) - 15.59
    return {"grade": max(0.0, grade)}

TE_LABELS = {
    "MY CARE PLAN": "నా సంరక్షణ ప్రణాళిక",
    "YOUR MEDICINES — follow the discharge summary exactly": "మీ మందులు — డిశ్చార్జ్ పత్రంలో ఉన్న సూచనలనే ఖచ్చితంగా పాటించండి",
    "MEDICINES TO STOP": "ఆపాల్సిన మందులు",
    "WARNING SIGNS — SEEK URGENT CARE AS WRITTEN IN YOUR SUMMARY": "హెచ్చరిక లక్షణాలు — వెంటనే వైద్య సహాయం పొందండి",
    "FOOD / DIET": "ఆహారం / ఆహార నియమాలు",
    "ACTIVITY": "కదలికలు / శారీరక కార్యకలాపాలు",
    "OTHER ADVICE": "ఇతర సూచనలు",
    "FOLLOW-UP": "తదుపరి వైద్య పరీక్షలు",
    "Dose:": "మోతాదు:",
    "Frequency:": "ఎన్ని సార్లు తీసుకోవాలి:",
    "Timing:": "తీసుకునే సమయం:",
    "Duration:": "ఎన్ని రోజులు / ఎంతకాలం:",
    "Source instruction:": "అసలు పత్రంలోని సూచన:",
    "No stop instruction was confidently extracted. Check the original summary.": "మందు ఆపే సూచన స్పష్టంగా గుర్తించబడలేదు. అసలు డిశ్చార్జ్ పత్రాన్ని పరిశీలించండి.",
    "No instruction confidently extracted. Check the original summary.": "సూచన స్పష్టంగా గుర్తించబడలేదు. అసలు డిశ్చార్జ్ పత్రాన్ని పరిశీలించండి.",
    "No follow-up confidently extracted. Check the original summary.": "తదుపరి పరీక్ష వివరాలు స్పష్టంగా గుర్తించబడలేదు. అసలు డిశ్చార్జ్ పత్రాన్ని పరిశీలించండి.",
    "Not confidently extracted — check the source": "స్పష్టంగా గుర్తించబడలేదు — అసలు పత్రాన్ని చూడండి",
    "IMPORTANT: This is a draft generated from extracted text. Confirm every item with the original discharge summary and care team.": "ముఖ్యం: ఇది పత్రం నుంచి తీసిన సమాచారంతో రూపొందించిన ముసాయిదా. ప్రతి అంశాన్ని అసలు డిశ్చార్జ్ పత్రం మరియు వైద్య బృందంతో నిర్ధారించండి.",
}

# Phrase translations for common patient instructions. Unknown clinical text is deliberately
# preserved in English rather than guessed or translated inaccurately.
TE_PHRASES = {
    "Excessive PV bleeding (> 1 pad soaked per hour) / passing clots": "అధికంగా యోని రక్తస్రావం కావడం (గంటకు ఒక ప్యాడ్ పూర్తిగా తడిసేంత) లేదా రక్తపు గడ్డలు రావడం",
    "Fever above 100.4 F (38 C)": "100.4°F (38°C) కంటే ఎక్కువ జ్వరం రావడం",
    "Breast - painful red hard swelling with fever": "స్తనంలో నొప్పి, ఎర్రదనం, గట్టిగా వాపు ఉండటం మరియు జ్వరం రావడం",
    "Severe headache, blurring of vision or pain in upper abdomen": "తీవ్రమైన తలనొప్పి, చూపు మసకబారడం లేదా పై పొత్తికడుపులో నొప్పి రావడం",
    "Baby: poor feeding / lethargy / fever / yellowish skin": "శిశువు సరిగా పాలు తాగకపోవడం, నీరసంగా ఉండటం, జ్వరం రావడం లేదా చర్మం పసుపు రంగులోకి మారడం",
    "Feeling low or hopeless most of the time, unable to sleep, or thoughts of harming self or baby": "ఎక్కువ సమయం బాధగా లేదా నిరాశగా అనిపించడం, నిద్ర పట్టకపోవడం, తనకు లేదా బిడ్డకు హాని చేయాలనే ఆలోచనలు రావడం",
    "Redness, swelling, pus or discharge from the wound": "గాయం వద్ద ఎర్రదనం, వాపు, చీము లేదా ద్రవం రావడం",
    "Avoid sugar and sweets; keep a healthy weight": "చక్కెర మరియు తీపి పదార్థాలను తగ్గించండి; ఆరోగ్యకరమైన బరువును కొనసాగించండి",
    "Nutritious diet with 1 extra meal a day - green leafy vegetables, milk, dal; plenty of fluids": "రోజుకు ఒక అదనపు భోజనంతో పోషకాహారం తీసుకోండి. ఆకుకూరలు, పాలు, పప్పులు తినండి; తగినంత ద్రవాలు తాగండి",
    "Gradually increase walking as tolerated": "మీకు సాధ్యమైనంత మేరకు నడకను క్రమంగా పెంచండి",
    "Morning": "ఉదయం",
    "Afternoon": "మధ్యాహ్నం",
    "Night": "రాత్రి",
    "Morning and afternoon": "ఉదయం మరియు మధ్యాహ్నం",
    "Morning and night": "ఉదయం మరియు రాత్రి",
    "Afternoon and night": "మధ్యాహ్నం మరియు రాత్రి",
    "Morning, afternoon and night": "ఉదయం, మధ్యాహ్నం మరియు రాత్రి",
    "Morning, afternoon, evening and night": "ఉదయం, మధ్యాహ్నం, సాయంత్రం మరియు రాత్రి",
    "Once daily (exact time not specified)": "రోజుకు ఒకసారి (ఖచ్చితమైన సమయం పేర్కొనలేదు)",
    "Twice daily (exact times not specified)": "రోజుకు రెండుసార్లు (ఖచ్చితమైన సమయాలు పేర్కొనలేదు)",
    "Three times daily (exact times not specified)": "రోజుకు మూడుసార్లు (ఖచ్చితమైన సమయాలు పేర్కొనలేదు)",
    "Four times daily (exact times not specified)": "రోజుకు నాలుగుసార్లు (ఖచ్చితమైన సమయాలు పేర్కొనలేదు)",
    "Only when needed, as prescribed": "వైద్యుని సూచన ప్రకారం అవసరమైనప్పుడు మాత్రమే",
    "At bedtime": "నిద్రపోయే ముందు",
    "Immediately, as prescribed": "వైద్యుని సూచన ప్రకారం వెంటనే",
    "Timing not specified — check prescription": "సమయం పేర్కొనలేదు — ప్రిస్క్రిప్షన్‌ను పరిశీలించండి",
    "No instruction confidently extracted. Check the original summary.": "సూచన స్పష్టంగా గుర్తించబడలేదు. అసలు డిశ్చార్జ్ పత్రాన్ని పరిశీలించండి.",
}

def translate_telugu_conservative(text: str) -> str:
    """Translate known patient-facing labels/phrases; preserve unknown clinical details."""
    result = []
    for line in text.splitlines():
        raw = line
        stripped = line.strip()
        if stripped in TE_LABELS:
            translated = TE_LABELS[stripped]
            result.append(line[:len(line)-len(line.lstrip())] + translated)
            continue
        # Translate field labels without altering medicine names, doses, dates, or frequencies.
        for source, target in [("Dose:", "మోతాదు:"), ("Frequency:", "ఎన్ని సార్లు తీసుకోవాలి:"),
                               ("Timing:", "తీసుకునే సమయం:"), ("Duration:", "ఎన్ని రోజులు / ఎంతకాలం:"),
                               ("Source instruction:", "అసలు పత్రంలోని సూచన:")]:
            if stripped.startswith(source):
                prefix = raw[:len(raw)-len(raw.lstrip())]
                value = stripped[len(source):].strip()
                if source == "Timing:":
                    value = TE_PHRASES.get(value, value)
                result.append(prefix + target + (" " + value if value else ""))
                break
        else:
            bullet = ""
            content = stripped
            if content.startswith("- "):
                bullet, content = "- ", content[2:]
            elif content[:1].isdigit() and ". " in content[:5]:
                idx = content.find(". ")
                bullet, content = content[:idx+2], content[idx+2:]
            translated = TE_PHRASES.get(content, TE_LABELS.get(content, content))
            result.append(bullet + translated if bullet else translated)
    return "\n".join(result)
