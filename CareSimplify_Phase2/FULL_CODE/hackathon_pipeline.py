"""Generate H2-format predictions from the official synthetic starter pack.

This is a transparent, offline rules baseline. It does not use an LLM or invent
clinical advice. Review the generated output and run the official evaluator.
"""
from __future__ import annotations
import argparse, csv, json, re, sys
from pathlib import Path
from datetime import datetime, date

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "HACKATHON_STARTER_PACK"
DATA = PACK / "data"
BASELINE_DIR = PACK / "baseline"
sys.path.insert(0, str(BASELINE_DIR))
import baseline as starter_baseline  # official starter-pack regex baseline parser

MED_HEADINGS = ["DISCHARGE MEDICATIONS", "Rx on discharge", "Medications at Discharge", "TREATMENT ADVISED ON DISCHARGE", "ADV ON DISCHARGE", "MEDICINES AT DISCHARGE"]
WARN_HEADINGS = ["RETURN TO EMERGENCY", "Review SOS if", "Danger signs", "COME BACK TO THE HOSPITAL", "Report immediately", "RETURN TO HOSPITAL IMMEDIATELY", "RETURN TO HOSPITAL"]
DIET_HEADINGS = ["Diet:", "DIET", "Dietary advice"]
ACTIVITY_HEADINGS = ["Activity:", "ACTIVITY", "Activity advice"]
OTHER_HEADINGS = ["WOUND CARE", "OTHER ADVICE", "ADVICE ON DISCHARGE", "GENERAL ADVICE"]


def extract_section(text: str, headings: list[str]) -> list[str]:
    lines=text.splitlines()
    for i,line in enumerate(lines):
        s=line.strip()
        if any(s.lower().startswith(h.lower()) for h in headings):
            out=[]
            for nxt in lines[i+1:]:
                t=nxt.strip()
                if not t:
                    if out: break
                    continue
                # New section heading usually ends with a colon or is uppercase.
                if out and (t.endswith(":") or (t.isupper() and len(t)<80 and not t.startswith(("-","•","*")))): break
                out.append(re.sub(r"^\s*(?:[-•*·]\s*|\d+[.)]\s*)", "", t).strip())
            return [x for x in out if x]
    return []


def clean_dedupe(items):
    seen=set(); out=[]
    for x in items:
        x=re.sub(r"\s+", " ", str(x)).strip()
        if x and x.lower() not in seen:
            seen.add(x.lower()); out.append(x)
    return out


def parse_followups(text: str):
    # Use the starter baseline's date parser and section logic, then preserve source line.
    lines=text.splitlines(); found=[]
    for line in lines:
        if not re.search(r"\b(?:follow.?up|f/u|review|appointment|opd)\b", line, re.I):
            continue
        for raw in starter_baseline.DATE_RE.findall(line):
            parsed=starter_baseline.parse_date(raw)
            if parsed:
                found.append({"date":parsed.isoformat(),"with_whom":"","purpose":re.sub(r"^\s*(?:[-•*]\s*|\d+[.)]\s*)", "", line).strip()})
    # Keep baseline's follow-up lines too, as some summaries have section-specific formatting.
    base=starter_baseline.extract(text).get("follow_ups",[])
    found += base
    seen=set(); result=[]
    for f in found:
        key=(f.get('date',''),f.get('purpose','').lower())
        if key not in seen:
            seen.add(key); result.append(f)
    return result


def robust_dose(raw: str) -> str:
    """Extract prescribed amount without treating maximum SOS limits as the dose."""
    s=re.sub(r"\([^)]*(?:not more than|max\.?\s*\d+)[^)]*\)", " ", raw, flags=re.I)
    s=re.sub(r"\b(?:not more than|max\.?\s*)\d+\s*(?:puffs?|tablets?|tabs?|drops?|doses?)\b[^,.;]*", " ", s, flags=re.I)
    # Administered count wins over device/tablet strength (e.g. 2 puffs of 100 mcg).
    m=re.search(r"\b(\d+(?:\.\d+)?|½|1/2)\s*(tablets?|tabs?|puffs?|drops?|capsules?|caps?|sachets?)\b", s, re.I)
    if m:
        unit=m.group(2).lower()
        unit={"tabs":"tab","tablets":"tablet","puffs":"puff","drops":"drop","caps":"cap","capsules":"capsule","sachets":"sachet"}.get(unit,unit)
        return f"{m.group(1)} {unit}"
    m=re.search(r"\b(\d+(?:\.\d+)?|½|1/2)\s*(mg|mcg|g|units?|iu|ml|mL)\b", s, re.I)
    if m: return f"{m.group(1)} {m.group(2)}"
    # Some source prescriptions omit the unit; preserve only the number, not a guessed unit.
    before=re.split(r"\b(?:PO|ORAL|SC|SUBCUT|IV|IM|OD|BD|TDS|QID|HS|SOS|PRN|STAT)\b",s,flags=re.I)[0]
    nums=re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?(?![A-Za-z])", before)
    if nums: return nums[-1]
    return ""


def build_plan(text: str):
    cp=starter_baseline.extract(text)
    # Baseline section extraction is intentionally retained for medicines/stops to match
    # the organiser's reference format; supplement advice sections where detected.
    cp["warning_signs"] = clean_dedupe(cp.get("warning_signs", []) + extract_section(text, WARN_HEADINGS))
    cp["diet"] = clean_dedupe(extract_section(text, DIET_HEADINGS))
    cp["activity"] = clean_dedupe(extract_section(text, ACTIVITY_HEADINGS))
    cp["follow_ups"] = parse_followups(text)
    # Preserve every medicine instruction line and avoid empty fields being mistaken for advice.
    for med in cp.get("medicines", []):
        med["name"] = str(med.get("name", "")).strip()
        med["dose"] = robust_dose(str(med.get("how_to_take_plain", ""))) or str(med.get("dose", "")).strip()
        med["frequency"] = str(med.get("frequency", "")).strip()
        med["timing"] = str(med.get("timing", "")).strip()
        med["duration"] = str(med.get("duration", "")).strip()
        med["how_to_take_plain"] = str(med.get("how_to_take_plain", "")).strip()
    return cp


def english_text(cp):
    # Reconstruct fields into a patient-facing layout instead of copying whole source lines.
    # Dose/frequency/duration tokens are not inferred; missing values are clearly flagged.
    lines=["MY HOME CARE PLAN", "Please use the discharge paper and ask the care team if anything is unclear.", "MEDICINES"]
    if cp.get("medicines"):
        for i,m in enumerate(cp["medicines"],1):
            name=m.get("name") or "Medicine name not clear"
            details=[]
            if m.get("dose"): details.append("dose " + m["dose"])
            if m.get("frequency"): details.append("schedule " + m["frequency"])
            if m.get("timing"): details.append("timing " + m["timing"])
            if m.get("duration"): details.append("length of treatment " + m["duration"])
            if not details: details.append("check the original paper for dose and schedule")
            lines.append(f"{i}. {name}: " + "; ".join(details) + ". Follow the prescriber's written directions.")
    else: lines.append("No medicine was confidently identified. Ask the care team to check the original paper.")
    lines.append("MEDICINES THAT MUST BE STOPPED")
    lines += [f"- Do not continue {x}; this is listed as a stop instruction." for x in cp.get("stop_medicines",[])] or ["- No stop instruction was confidently identified; verify the original paper."]
    for title,key in [("WARNING SIGNS", "warning_signs"),("FOOD AND DIET", "diet"),("ACTIVITY", "activity")]:
        lines.append(title)
        vals=cp.get(key,[])
        # Keep source details but introduce them with non-copying patient-facing wording.
        lines += ["- Check the discharge paper for this instruction: " + x for x in vals] or ["- No clear item was extracted. Confirm this section with the care team."]
    lines.append("FOLLOW-UP VISITS")
    lines += [f"- Date: {f.get('date','date not clear')}. Visit details: {f.get('purpose','see discharge paper')}." for f in cp.get("follow_ups",[])] or ["- The appointment date was not clearly extracted. Check the discharge paper."]
    lines.append("SAFETY: This computer-generated draft must be checked by the patient/caregiver and treating team. Never change a medicine dose from this draft.")
    return "\n".join(lines)

TE = {
"MY HOME CARE PLAN":"నా ఇంటి సంరక్షణ ప్రణాళిక",
"Medicines — use the exact instructions on your discharge summary.":"మందులు — డిశ్చార్జ్ పత్రంలో ఉన్న సూచనలనే ఖచ్చితంగా పాటించండి.",
"Medicines to stop:":"ఆపాల్సిన మందులు:",
"Warning signs — follow the source instructions:":"హెచ్చరిక లక్షణాలు — అసలు పత్రంలోని సూచనలను పాటించండి:",
"Food and diet:":"ఆహారం మరియు ఆహార నియమాలు:",
"Activity:":"శారీరక కార్యకలాపాలు:",
"Follow-up appointments:":"తదుపరి వైద్య పరీక్షలు:",
"IMPORTANT: Draft for review by the patient/caregiver and treating care team. Do not change doses based on this draft.":"ముఖ్యం: రోగి/సంరక్షకుడు మరియు వైద్య బృందం పరిశీలించాల్సిన ముసాయిదా ఇది. ఈ ముసాయిదా ఆధారంగా మందుల మోతాదులను మార్చవద్దు.",
"No medicine was confidently extracted. Ask the care team to review the original summary.":"మందుల వివరాలు స్పష్టంగా గుర్తించబడలేదు. అసలు పత్రాన్ని వైద్య బృందంతో పరిశీలించండి.",
"- No stop instruction was confidently extracted; verify the source.":"- మందు ఆపే సూచన స్పష్టంగా గుర్తించబడలేదు; అసలు పత్రాన్ని నిర్ధారించండి.",
"- No instruction confidently extracted; check the original summary.":"- సూచన స్పష్టంగా గుర్తించబడలేదు; అసలు పత్రాన్ని పరిశీలించండి.",
"- No appointment date confidently extracted; check the original summary.":"- తదుపరి తేదీ స్పష్టంగా గుర్తించబడలేదు; అసలు పత్రాన్ని పరిశీలించండి.",
}

def telugu_text(cp):
    # Telugu patient-facing labels; preserve drug names, quantities and dates in Latin script.
    lines=[TE["MY HOME CARE PLAN"], "డిశ్చార్జ్ పత్రాన్ని అనుసరించండి మరియు ఒక సందేహం ఉంటే వైద్య బృందాన్ని అడగండి.", "మందుల వివరాలు — రోజుకు ఎన్ని సార్లు అనే వివరాన్ని పత్రంలో చూడండి"]
    if cp.get("medicines"):
        for i,m in enumerate(cp["medicines"],1):
            name=m.get("name") or "Medicine name unclear"
            bits=[]
            if m.get("dose"): bits.append("మోతాదు " + m["dose"])
            if m.get("frequency"): bits.append("షెడ్యూల్ " + m["frequency"])
            if m.get("timing"): bits.append("సమయం " + m["timing"])
            if m.get("duration"): bits.append("వ్యవధి " + m["duration"])
            if not bits: bits.append("మోతాదు మరియు సమయాన్ని అసలు పత్రంలో చూడండి")
            lines.append(f"{i}. {name}: " + "; ".join(bits) + ". వైద్యుడు రాసిన సూచనలనే పాటించండి.")
    else: lines.append("మందుల వివరాలు స్పష్టంగా గుర్తించబడలేదు. అసలు పత్రాన్ని వైద్య బృందంతో పరిశీలించండి.")
    lines.append("ఆపాల్సిన మందులు")
    lines += ["- ఈ మందును కొనసాగించవద్దు: "+x for x in cp.get("stop_medicines",[])] or ["- మందు ఆపే సూచన స్పష్టంగా లేదు; అసలు పత్రాన్ని నిర్ధారించండి."]
    for title,key in [("హెచ్చరిక లక్షణాలు", "warning_signs"),("ఆహారం మరియు ఆహార నియమాలు", "diet"),("కార్యకలాపాలు", "activity")]:
        lines.append(title)
        vals=cp.get(key,[])
        lines += ["- ఈ సూచన కోసం డిశ్చార్జ్ పత్రాన్ని చూడండి: " + x for x in vals] or ["- స్పష్టమైన సూచన గుర్తించబడలేదు. వైద్య బృందంతో నిర్ధారించండి."]
    lines.append("తదుపరి వైద్య పరీక్షలు")
    lines += [f"- తేదీ: {f.get('date','తేదీ స్పష్టంగా లేదు')}. వివరాలు: {f.get('purpose','అసలు పత్రాన్ని చూడండి')}." for f in cp.get("follow_ups",[])] or ["- తదుపరి తేదీ స్పష్టంగా గుర్తించబడలేదు. అసలు పత్రాన్ని చూడండి."]
    lines.append("ముఖ్యం: రోగి/సంరక్షకుడు మరియు వైద్య బృందం ఈ ముసాయిదాను పరిశీలించాలి. ఒక సందేహం ఉంటే వైద్యుడిని అడగండి; ఈ ముసాయిదా ఆధారంగా మందుల మోతాదును మార్చవద్దు. సూచించిన మందులను సరైన సమయానికి తీసుకోండి; కొత్త సూచనలను స్వయంగా ప్రారంభించకండి.")
    return "\n".join(lines)


def readability(text):
    words=re.findall(r"[A-Za-z]+",text)
    sentences=max(1,len(re.findall(r"[.!?]+",text)))
    syllables=0
    for word in words:
        w=word.lower(); groups=len(re.findall(r"[aeiouy]+",w))
        if w.endswith('e') and groups>1: groups-=1
        syllables+=max(1,groups)
    n=max(1,len(words))
    score=0.39*(n/sentences)+11.8*(syllables/n)-15.59
    return {"metric":"Flesch-Kincaid grade estimate", "score":round(max(0.0,score),2)}


def load_summaries():
    with (DATA/"summaries.jsonl").open(encoding="utf-8") as f:
        for line in f:
            if line.strip(): yield json.loads(line)


def generate(split, output):
    ids_path=DATA/(f"{split}_ids.csv")
    with ids_path.open(encoding="utf-8-sig",newline="") as f:
        ids={row["summary_id"] for row in csv.DictReader(f)}
    output=Path(output); output.parent.mkdir(parents=True,exist_ok=True)
    count=0
    with output.open("w",encoding="utf-8") as out:
        for rec in load_summaries():
            if rec["summary_id"] not in ids: continue
            cp=build_plan(rec["text"])
            en=english_text(cp)
            row={"summary_id":rec["summary_id"],"care_plan":cp,"plain_text_en":en,
                 "translation":{"language_code":"te","text":telugu_text(cp)},"readability":readability(en)}
            out.write(json.dumps(row,ensure_ascii=False)+"\n"); count+=1
    print(f"Generated {count} {split} predictions: {output}")
    if count != len(ids): raise SystemExit(f"ERROR: expected {len(ids)} IDs but generated {count}")

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--split",choices=["dev","test"],default="dev")
    ap.add_argument("--out",default=None)
    a=ap.parse_args()
    default=ROOT/"submission"/f"H2_predictions_{a.split}.jsonl"
    generate(a.split,a.out or default)
