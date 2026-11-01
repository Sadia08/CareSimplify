from __future__ import annotations
import io
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
import json
import hashlib
from datetime import date, timedelta
from pypdf import PdfReader
from care_plan import extract_candidate_plan, build_plain_text, readability_score, translate_telugu_conservative
from timetable import build_timetable, duration_to_days, dose_slots, seven_day_dates
from medication_log import is_dose_taken, set_dose_taken
from exports import make_fridge_pdf, make_full_pdf, make_csv

st.set_page_config(page_title="CareSimplify | H2", page_icon="🩺", layout="wide")
st.markdown("""
<style>
:root { --cs-navy:#163A5F; --cs-teal:#087E8B; --cs-slate:#334155; --cs-text:#475569; --cs-bg:#F8FAFC; --cs-border:#DCE5ED; }
.stApp { background:var(--cs-bg); color:var(--cs-text); }
[data-testid="stAppViewContainer"] .main .block-container { max-width:1440px; padding-top:1.35rem; padding-bottom:2.5rem; }
html, body, [class*="css"] { font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
h1, h2, h3 { color:var(--cs-navy) !important; font-weight:750 !important; letter-spacing:-.025em; }
h4, h5, h6 { color:var(--cs-slate) !important; font-weight:650 !important; }
p, label, .stMarkdown, [data-testid="stCaptionContainer"] { color:var(--cs-text); }
.hero { padding:1.65rem 1.85rem; border-radius:20px; background:linear-gradient(120deg,#163A5F 0%,#087E8B 100%); color:#fff; margin:0 0 1.25rem; box-shadow:0 10px 26px rgba(22,58,95,.14); }
.hero h1 { color:#fff !important; margin:0; font-size:2.15rem; }
.hero p { color:#E5F5F6; margin:.4rem 0 0; font-size:1rem; }
[data-testid="stMetric"] { background:#fff; border:1px solid var(--cs-border); border-radius:15px; padding:1rem 1.1rem; box-shadow:0 2px 8px rgba(15,23,42,.035); }
[data-testid="stMetricLabel"] p { color:var(--cs-teal) !important; font-weight:650 !important; }
[data-testid="stMetricValue"] { color:var(--cs-navy) !important; font-weight:750; }
[data-testid="stExpander"] { background:#fff; border:1px solid var(--cs-border); border-radius:15px; overflow:hidden; margin:.65rem 0; box-shadow:0 2px 8px rgba(15,23,42,.025); }
[data-testid="stExpander"] summary { color:var(--cs-teal) !important; font-weight:700; padding:.8rem 1rem; }
[data-testid="stExpander"] [data-testid="stExpanderDetails"] { padding:.8rem 1rem 1.15rem; }
[data-testid="stTabs"] [data-baseweb="tab-list"] { gap:.45rem; border-bottom:1px solid var(--cs-border); }
[data-testid="stTabs"] button[role="tab"] { background:#E9EFF5; border:1px solid #D8E2EC; border-radius:10px 10px 0 0; color:var(--cs-slate); padding:.65rem 1rem; font-weight:650; }
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] { background:var(--cs-navy); color:#fff !important; border-color:var(--cs-navy); }
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] p { color:#fff !important; }
[data-testid="stAlert"] { border-radius:12px; }
[data-testid="stAlert"] p { color:inherit; }
.stButton > button, .stDownloadButton > button { border-radius:10px; font-weight:650; border:1px solid var(--cs-teal); }
.stButton > button[kind="primary"], .stDownloadButton > button { background:var(--cs-teal); color:white; }
.stProgress > div > div > div > div { background:var(--cs-teal); }
[data-testid="stVerticalBlockBorderWrapper"] { border-radius:15px; border-color:var(--cs-border); background:#fff; padding:.25rem; }
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea, [data-testid="stSelectbox"] > div { border-radius:9px; }
hr { border-color:var(--cs-border); }
@media (max-width: 760px) {
  [data-testid="stAppViewContainer"] .main .block-container { padding-left:1rem; padding-right:1rem; }
  .hero { padding:1.2rem; border-radius:15px; }
  .hero h1 { font-size:1.7rem; }
  [data-testid="stTabs"] [data-baseweb="tab-list"] { flex-wrap:wrap; }
}
</style>
<div class="hero"><h1>CareSimplify</h1><p>Your discharge instructions, transformed into a clearer home-care plan</p></div>
""", unsafe_allow_html=True)

SAMPLE = """DISCHARGE SUMMARY
Diagnosis: Sample post-discharge recovery
DISCHARGE MEDICATIONS:
1. Tab. Example medicine 500 mg PO BD for 5 days
2. Tab. Example medicine B 1 tablet PO OD after dinner for 7 days
MEDICINES TO BE STOPPED:
- STOP Example medicine C 10 mg
Instructions:
Diet:
- Follow the diet instructions given by the treating team.
Activity:
- Rest as advised in the discharge summary.
RETURN TO HOSPITAL IMMEDIATELY IF:
- Severe or worsening symptoms described by the treating team.
FOLLOW-UP:
- Review on 05/11/2026 with the treating clinic.
"""
st.caption("Prototype only · clinician/patient-care-team review is required before use. Do not use the sample for real treatment.")
with st.sidebar:
    st.header("1 · Add discharge summary")
    mode = st.radio("Input source", ["Upload PDF or TXT", "Try built-in demo"], index=1)
    uploaded = None
    if mode == "Upload PDF or TXT":
        uploaded = st.file_uploader("Choose a discharge summary", type=["pdf", "txt"])
    st.divider()
    st.header("2 · Output settings")
    language = st.selectbox("Patient language", ["Telugu (conservative draft)", "English only"])
    st.info("No Gemini key or paid AI API is required. Extraction is rule-based and uncertain fields are flagged.")
    st.caption("Scanned/image-only PDFs need OCR before text can be extracted.")

    with st.expander("3. Health Goal Settings", expanded=True):
        goal_type = st.selectbox("Health goal", [
            "Weight management", "Blood sugar management", "Blood pressure management",
            "Physical rehabilitation", "Medication adherence", "Other"
        ], key="cs_goal_type")
        goal_col1, goal_col2 = st.columns(2)
        with goal_col1:
            current_weight = st.number_input("Current weight (kg)", min_value=0.0, max_value=500.0, value=0.0, step=0.5, key="cs_current_weight")
            height_cm = st.number_input("Height (cm)", min_value=0.0, max_value=300.0, value=0.0, step=0.5, key="cs_height")
            patient_age = st.number_input("Patient age", min_value=0, max_value=120, value=0, key="cs_patient_age")
        with goal_col2:
            target_weight = st.number_input("Target weight (kg)", min_value=0.0, max_value=500.0, value=0.0, step=0.5, key="cs_target_weight")
            timeline_weeks = st.number_input("Goal timeline (weeks)", min_value=1, max_value=104, value=4, key="cs_goal_timeline")
        doctor_goal_instructions = st.text_area(
            "Doctor's instructions / approved target",
            placeholder="Copy the clinician's goal, restrictions, activity limits, and approved measurements here.",
            height=100, key="cs_doctor_goal_instructions"
        )
        if goal_type == "Blood sugar management":
            st.text_input("Clinician-approved glucose target (optional)", key="cs_glucose_target")
        elif goal_type == "Blood pressure management":
            st.text_input("Clinician-approved blood pressure target (optional)", key="cs_bp_target")
        elif goal_type == "Physical rehabilitation":
            st.text_input("Movement restrictions / rehabilitation instructions", key="cs_rehab_limits")
        elif goal_type == "Medication adherence":
            st.caption("Medication timing and doses will only be taken from the discharge summary/prescription.")
        elif goal_type == "Other":
            st.text_input("Describe the goal", key="cs_other_goal")
        if st.button("Generate Goal Plan", type="primary", use_container_width=True, key="cs_generate_goal"):
            st.session_state["cs_generate_goal_requested"] = True


def extract_upload(file):
    if file is None:
        return ""
    raw = file.getvalue()
    if file.name.lower().endswith(".txt"):
        return raw.decode("utf-8", errors="replace")
    reader = PdfReader(io.BytesIO(raw))
    return "\n".join(page.extract_text() or "" for page in reader.pages)

if mode == "Try built-in demo":
    source_text = SAMPLE
elif uploaded:
    source_text = extract_upload(uploaded)
else:
    source_text = ""

with st.expander("View extracted source text", expanded=False):
    st.text_area("Extracted text (editable for prototype testing)", value=source_text, height=220, key="source_preview")
source_text = st.session_state.get("source_preview", source_text)

if not source_text.strip():
    st.warning("Upload a PDF/TXT file or select the built-in demo to continue.")
    st.stop()

st.markdown("## Review Extracted Information")
plan = extract_candidate_plan(source_text)

# Patient-facing dashboard: keep only relevant care-plan metrics.
c1, c2 = st.columns(2)
c1.metric("Candidate medicines", len(plan["medicines"]))
c2.metric("Follow-up dates found", len(plan["follow_ups"]))

st.warning("Review every field against the original discharge summary. The parser is a candidate extractor, not a medical validator.")
# Medication review: inclusion controls apply to the generated plan and timetable.
# A removed row is excluded from this generated plan; it does NOT discontinue a prescription.
source_id = hashlib.sha256(source_text.encode("utf-8")).hexdigest()[:12]

def _exclude_medicine(widget_key):
    """Streamlit callback: exclude a medicine from the generated care plan."""
    st.session_state[widget_key] = False

with st.expander("Medication list — verify before use", expanded=True):
    if not plan["medicines"]:
        st.info(
            "No medication rows confidently detected. Add them manually only by "
            "copying the source instruction exactly."
        )

    edited_meds = []
    excluded_count = 0

    for i, med in enumerate(plan["medicines"]):
        include_key = f"cs_include_{source_id}_{i}"
        remove_key = f"cs_remove_{source_id}_{i}"

        # Default each newly detected medicine to included.
        if include_key not in st.session_state:
            st.session_state[include_key] = True

        with st.container(border=True):
            medicine_title = med.get("name") or "Review extracted medicine"
            st.markdown(f"**Medicine {i + 1} · {medicine_title}**")

            control_col, remove_col = st.columns([4, 1])
            with control_col:
                st.checkbox(
                    "Include in generated care plan and timetable",
                    key=include_key,
                )
            with remove_col:
                st.button(
                    "Remove",
                    key=remove_key,
                    help="Exclude this extracted row from the generated care plan. "
                         "This does not stop a prescribed medicine.",
                    on_click=_exclude_medicine,
                    args=(include_key,),
                    use_container_width=True,
                )

            if not st.session_state[include_key]:
                excluded_count += 1
                st.warning(
                    "Excluded from the generated care plan and timetable. "
                    "If this is an actual prescribed medicine, confirm any change "
                    "with the treating clinician."
                )
                continue

            cols = st.columns([2, 1.1, 1.1, 1.2, 1.4, 2])
            vals = {}
            labels = [
                ("name", "Medicine"),
                ("dose", "Dose"),
                ("frequency", "Frequency"),
                ("timing", "Timing"),
                ("duration", "Duration"),
                ("how_to_take_plain", "Source instruction / plain wording"),
            ]
            for col, (key, label) in zip(cols, labels):
                vals[key] = col.text_input(
                    label,
                    value=str(med.get(key, "")),
                    key=f"cs_med_{source_id}_{i}_{key}",
                )
            edited_meds.append(vals)

    # Downstream care-plan generation, export and timetable use this filtered list.
    plan["medicines"] = edited_meds

    included_col, excluded_col = st.columns(2)
    included_col.metric("Included medicines", len(edited_meds))
    excluded_col.metric("Excluded medicines", excluded_count)
    if excluded_count:
        st.info(
            f"{excluded_count} medicine(s) excluded from this generated plan. "
            "The uploaded discharge summary remains unchanged."
        )

with st.expander("Stop medicines, warnings, diet, activity and follow-up", expanded=True):
    def edit_lines(label, key):
        joined = "\n".join(plan.get(key, []))
        raw = st.text_area(label, joined, height=100, key=f"edit_{key}")
        return [x.strip(" •-\t") for x in raw.splitlines() if x.strip()]
    plan["stop_medicines"] = edit_lines("Medicines to stop (one per line)", "stop_medicines")
    plan["warning_signs"] = edit_lines("Warning signs copied from source (one per line)", "warning_signs")
    plan["diet"] = edit_lines("Diet instructions (one per line)", "diet")
    plan["activity"] = edit_lines("Activity instructions (one per line)", "activity")
    plan["other_advice"] = edit_lines("Other advice (one per line)", "other_advice")
    fu_text = st.text_area("Follow-up instructions (one per line; keep exact dates)", "\n".join(
        f'{f.get("date","")} | {f.get("with_whom","")} | {f.get("purpose","")}' for f in plan["follow_ups"]), height=90)
    plan["follow_ups"] = []
    for line in fu_text.splitlines():
        parts = [p.strip() for p in line.split("|", 2)]
        if any(parts):
            parts += [""] * (3-len(parts))
            plan["follow_ups"].append({"date":parts[0], "with_whom":parts[1], "purpose":parts[2]})

plain = build_plain_text(plan)
te_text = translate_telugu_conservative(plain) if language.startswith("Telugu") else ""
score = readability_score(plain)


# Phase 2: conservative, source-grounded goal plan builder.
# This version deliberately does not invent clinical targets or medication changes.
def build_goal_plan(goal_type, source, care_plan, current_weight, target_weight, height_cm,
                    patient_age, timeline_weeks, doctor_instructions):
    instructions = (doctor_instructions or "").strip()
    approved = bool(instructions)
    if goal_type == "Weight management":
        start = f"{current_weight:g} kg" if current_weight else "Not entered"
        target = f"{target_weight:g} kg" if target_weight else "Not supplied by clinician"
    elif goal_type == "Blood sugar management":
        start = "Record the latest value using the clinician's specified method"
        target = st.session_state.get("cs_glucose_target", "").strip() or "Not supplied by clinician"
    elif goal_type == "Blood pressure management":
        start = "Record latest blood pressure as instructed by care team"
        target = st.session_state.get("cs_bp_target", "").strip() or "Not supplied by clinician"
    elif goal_type == "Physical rehabilitation":
        start = "Record current ability only if the care team says it is appropriate"
        target = st.session_state.get("cs_rehab_limits", "").strip() or "Not supplied by clinician"
    elif goal_type == "Medication adherence":
        start = "Track prescribed doses using the existing 7-day medicine tracker"
        target = "Follow the prescription exactly; no dose changes"
    else:
        start = "Record a baseline with the care team"
        target = st.session_state.get("cs_other_goal", "").strip() or "Not supplied by clinician"

    # Daily actions are limited to the discharge instructions and safe tracking tasks.
    actions = []
    if care_plan.get("activity"):
        actions.extend([f"Activity: {x}" for x in care_plan["activity"]])
    else:
        actions.append("Do not start or increase exercise until the care team confirms what activity is safe for your condition.")
    if care_plan.get("diet"):
        actions.extend([f"Food / diet: {x}" for x in care_plan["diet"]])
    else:
        actions.append("Follow the diet recommended by your treating team; no new diet restriction has been inferred.")
    actions.append("Take medicines exactly as prescribed in the discharge summary. Do not change a dose or stop a medicine yourself.")
    actions.append("At the end of the day, tick only the activities you actually completed and record measurements only as your clinician instructed.")
    actions.append("If you miss an activity, do not double it or push harder the next day; resume the approved plan when safe and ask your care team if unsure.")
    if instructions:
        actions.insert(0, f"Doctor-provided instruction: {instructions}")
    else:
        actions.insert(0, "CLINICIAN REVIEW NEEDED: add the doctor's approved target and restrictions before using this as an action plan.")

    week = []
    routine = [
        "Confirm the approved plan and record a starting measurement if instructed.",
        "Repeat only the approved activities; note symptoms or difficulty.",
        "Continue at the same approved level; do not increase intensity without approval.",
        "Continue the approved routine and record completion.",
        "Review comfort, symptoms and any measurements requested by the care team.",
        "Continue only if tolerated and permitted by your discharge instructions.",
        "Review the week's record with the care team; agree any next steps with them."
    ]
    for i, text in enumerate(routine, 1):
        week.append({"day": f"Day {i}", "task": text})
    warnings = care_plan.get("warning_signs") or ["Seek urgent medical advice for severe or rapidly worsening symptoms; follow the emergency instructions in your discharge summary."]
    return {
        "goal_type": goal_type, "starting": start, "target": target,
        "review": f"Review in {int(timeline_weeks)} week(s), or on the earlier date stated by your clinician.",
        "age": patient_age, "height": height_cm, "actions": actions, "week": week,
        "warnings": warnings, "doctor_instructions": instructions, "approved": approved
    }

goal_plan = None
if st.session_state.get("cs_generate_goal_requested"):
    goal_plan = build_goal_plan(
        st.session_state.get("cs_goal_type", "Other"), source_text, plan,
        st.session_state.get("cs_current_weight", 0.0), st.session_state.get("cs_target_weight", 0.0),
        st.session_state.get("cs_height", 0.0), st.session_state.get("cs_patient_age", 0),
        st.session_state.get("cs_goal_timeline", 4), st.session_state.get("cs_doctor_goal_instructions", "")
    )
    st.session_state["cs_goal_plan"] = goal_plan
    st.session_state["cs_generate_goal_requested"] = False
goal_plan = st.session_state.get("cs_goal_plan", goal_plan)

st.markdown("## Patient-friendly Care Plan")
tab1, tab2, tab3, tab4, tab5 = st.tabs(["English care plan", "Telugu draft", "7-day timetable", "Goal-Based Care Plan", "My Progress"])
with tab1:
    st.text_area("English output", plain, height=360)
    st.metric("Estimated readability", f"Flesch-Kincaid grade ≈ {score['grade']:.1f}", help="Approximate English readability estimate; not a clinical quality score.")
with tab2:
    if te_text:
        st.text_area("Telugu-labelled conservative draft", te_text, height=360)
        st.caption("Unknown medical phrases are retained from the source in English rather than guessed. Have a fluent Telugu speaker and clinician verify all translated instructions.")
    else:
        st.info("Choose Telugu in the sidebar to create a Telugu-labelled draft.")
with tab3:
    st.subheader("7-day medicine tracker" if language.startswith("English") else "7 రోజుల మందుల పట్టిక")
    is_telugu = language.startswith("Telugu")
    st.caption(
        "Tick a box only after the dose has actually been given. Your selections are saved on this computer."
        if not is_telugu
        else "మందు ఇచ్చిన తర్వాత మాత్రమే పెట్టెను టిక్ చేయండి. మీ ఎంపికలు ఈ కంప్యూటర్‌లో సేవ్ అవుతాయి."
    )
    telugu_slots = {
        "Morning": "ఉదయం", "Afternoon": "మధ్యాహ్నం",
        "Evening": "సాయంత్రం", "Night": "రాత్రి",
        "Dose 1": "మోతాదు 1", "Dose 2": "మోతాదు 2",
        "Dose 3": "మోతాదు 3", "Dose 4": "మోతాదు 4",
    }
    start_date = st.date_input(
        "మొదటి రోజు తేదీ" if is_telugu else "Day 1 date",
        value=date.today(),
        key="tracker_start_date",
    )
    dates = seven_day_dates(start_date)
    document_id = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    total_planned = 0
    total_taken = 0
    tracker_items = []

    for medicine_index, medicine in enumerate(plan["medicines"]):
        frequency = str(medicine.get("frequency") or "").strip()
        duration_text = str(medicine.get("duration") or "")
        duration_days = duration_to_days(duration_text)
        slots = dose_slots(medicine)
        name = medicine.get("name") or f"Medicine {medicine_index + 1}"
        dose = medicine.get("dose") or "Dose not confidently extracted"
        timing = medicine.get("timing") or "Timing not specified — check prescription"

        with st.container(border=True):
            st.markdown(f"**💊 {name}**")
            st.caption(f"Dose: {dose} · Frequency: {frequency or 'Not specified'} · Timing: {timing} · Duration: {duration_text or 'Not specified'}")

            if frequency.upper() in {"SOS", "PRN"}:
                st.info("As-needed medicine: do not create fixed daily checkboxes. Record each use according to the care team's instructions.")
                continue
            if duration_days is None:
                st.warning("Duration is unclear or not in days/weeks/months. No daily checkboxes are enabled until the duration is verified from the source.")
                continue
            if not slots:
                st.warning("Frequency is unclear. No dose checkboxes are enabled until the schedule is verified.")
                continue

            med_total = 0
            med_taken = 0
            for day_index, dose_date in enumerate(dates):
                day_label = f"రోజు {day_index + 1}" if is_telugu else f"Day {day_index + 1}"
                st.markdown(f"**{day_label} · {dose_date.strftime('%d %b %Y')}**")
                if day_index >= min(duration_days, 7):
                    st.caption("Outside the prescribed duration")
                    continue
                columns = st.columns(min(len(slots), 4))
                for slot_index, slot in enumerate(slots):
                    widget_key = f"dose_{medicine_index}_{document_id[:10]}_{dose_date.isoformat()}_{slot_index}"
                    saved_value = is_dose_taken(document_id, medicine, dose_date, slot)
                    if widget_key not in st.session_state:
                        st.session_state[widget_key] = saved_value
                    with columns[slot_index % len(columns)]:
                        slot_label = telugu_slots.get(slot, slot) if is_telugu else slot
                        checked = st.checkbox(
                            slot_label,
                            key=widget_key,
                            help="Tick only after the dose has actually been given.",
                        )
                    if checked != saved_value:
                        set_dose_taken(document_id, medicine, dose_date, slot, checked)
                    med_total += 1
                    med_taken += int(checked)
            total_planned += med_total
            total_taken += med_taken
            st.progress(med_taken / med_total if med_total else 0.0)
            st.caption(
                f"పూర్తయ్యాయి: {med_taken} / {med_total} మోతాదులు"
                if is_telugu else f"Completed: {med_taken} / {med_total} planned doses"
            )
            tracker_items.append((medicine, med_total, med_taken))

    st.divider()
    st.subheader("మొత్తం పురోగతి" if is_telugu else "Overall progress")
    st.progress(total_taken / total_planned if total_planned else 0.0)
    st.metric("ఇచ్చిన మోతాదులు" if is_telugu else "Doses marked given", f"{total_taken} / {total_planned}")
    st.caption(
        "రికార్డులు ఈ కంప్యూటర్‌లో FULL_CODE/data/medication_log.json ఫైల్‌లో సేవ్ అవుతాయి. ఇది స్థానిక నమూనా మాత్రమే; బహుళ రోగుల సురక్షిత వైద్య రికార్డు కాదు."
        if is_telugu else
        "Saved locally in FULL_CODE/data/medication_log.json. This local prototype is intended for one computer/user; it is not a secure multi-patient clinical record."
    )


with tab4:
    st.subheader("Personalized goal-based care plan")
    if not goal_plan:
        st.info("Choose a health goal in the left panel, enter the clinician-approved instructions, then select Generate Goal Plan.")
    else:
        if not goal_plan["approved"]:
            st.warning("Draft only — doctor-approved target/instructions are missing. Please obtain clinician review before following activity, diet, or measurement targets.")
        else:
            st.warning("Clinician review is still required before this AI-assisted draft is treated as medical instructions.")
        st.markdown("### A. My Goal")
        st.write(f"**Goal:** {goal_plan['goal_type']}")
        st.write(f"**Starting measurement:** {goal_plan['starting']}")
        st.write(f"**Doctor-approved target:** {goal_plan['target']}")
        st.write(f"**Expected review:** {goal_plan['review']}")
        st.markdown("### B. My Action Plan")
        for action in goal_plan["actions"]:
            st.markdown(f"- {action}")
        st.markdown("### C. My Weekly Routine")
        st.dataframe(goal_plan["week"], use_container_width=True, hide_index=True)
        st.markdown("### E. My Follow-up")
        st.markdown("- Check in once each week and bring your activity and measurement record.")
        st.markdown(f"- **Review timing:** {goal_plan['review']}")
        st.markdown("**When to contact your doctor**")
        for warning in goal_plan["warnings"]:
            st.markdown(f"- {warning}")
        st.caption("This prototype uses a conservative rule-based draft, not a connected generative AI model. It does not create new clinical targets or change prescriptions. A healthcare professional must review the plan.")
with tab5:
    st.subheader("My Progress")
    if not goal_plan:
        st.info("Generate a goal plan first. Your progress tracker will then be available here.")
    else:
        progress_path = Path(__file__).resolve().parent / "data" / "goal_progress.json"
        try:
            progress_store = json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.exists() else {}
        except (OSError, json.JSONDecodeError):
            progress_store = {}
        progress_key = hashlib.sha256((source_id + goal_plan["goal_type"]).encode("utf-8")).hexdigest()[:20]
        record = progress_store.get(progress_key, {"checks": {}, "measurements": []})
        st.write(f"**Goal:** {goal_plan['goal_type']} · **Target:** {goal_plan['target']}")
        st.markdown("### Daily activity checklist")
        today_key = date.today().isoformat()
        checks_today = record.setdefault("checks", {}).setdefault(today_key, {})
        for idx, task in enumerate(goal_plan["actions"]):
            check_key = f"action_{idx}"
            checks_today[check_key] = st.checkbox(task, value=bool(checks_today.get(check_key, False)), key=f"cs_progress_{progress_key}_{today_key}_{idx}")
        completed = sum(bool(v) for v in checks_today.values())
        total = max(1, len(goal_plan["actions"]))
        st.progress(completed / total)
        st.caption(f"Today's activities completed: {completed} of {len(goal_plan['actions'])}")
        with st.form(f"measurement_form_{progress_key}"):
            st.markdown("### Record a measurement")
            measurement_value = st.number_input("Measurement value (enter only the metric relevant to your goal)", value=0.0, step=0.1, format="%.2f")
            measurement_note = st.text_input("Note (optional, e.g. measurement type or symptoms)")
            save_measurement = st.form_submit_button("Save measurement")
        if save_measurement:
            if measurement_value <= 0:
                st.error("Enter a measurement greater than zero.")
            else:
                record.setdefault("measurements", []).append({"date": today_key, "value": measurement_value, "note": measurement_note})
                progress_store[progress_key] = record
                progress_path.parent.mkdir(parents=True, exist_ok=True)
                progress_path.write_text(json.dumps(progress_store, ensure_ascii=False, indent=2), encoding="utf-8")
                st.success("Measurement saved on this computer.")
                st.rerun()
        # Persist today's checklist state.
        progress_store[progress_key] = record
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        progress_path.write_text(json.dumps(progress_store, ensure_ascii=False, indent=2), encoding="utf-8")
        measurements = record.get("measurements", [])
        if measurements:
            st.markdown("### Progress history")
            st.dataframe(measurements, use_container_width=True, hide_index=True)
            try:
                import pandas as pd
                chart_df = pd.DataFrame(measurements)
                chart_df["date"] = pd.to_datetime(chart_df["date"])
                st.line_chart(chart_df.set_index("date")["value"])
            except Exception:
                st.caption("Chart unavailable; measurement history is shown above.")
            st.write(f"**Starting measurement:** {measurements[0]['value']}")
            st.write(f"**Latest measurement:** {measurements[-1]['value']}")
            st.write(f"**Entries recorded:** {len(measurements)}")
        else:
            st.caption("No measurements recorded yet. Record a value only when appropriate for your goal and as directed by your care team.")
        st.markdown("### Weekly summary")
        st.write(f"Today: {completed}/{len(goal_plan['actions'])} activities marked complete. Measurements logged: {len(measurements)}.")
        st.caption("Progress is stored locally in FULL_CODE/data/goal_progress.json for this prototype. It is not a secure multi-patient medical record.")

# Browser-based text-to-speech: no API key or internet service is required.
# The actual available voices depend on the user's browser and operating system.
audio_language = "te-IN" if language.startswith("Telugu") else "en-IN"
audio_text = te_text if language.startswith("Telugu") and te_text.strip() else plain
st.markdown("## 🔊 Listen to Your Care Plan")
if language.startswith("Telugu") and not te_text.strip():
    st.warning("Telugu text is not available to read aloud yet. The app will not read the English text with a Telugu voice.")
else:
    audio_payload = json.dumps(audio_text, ensure_ascii=False).replace("</", "<\\/")
    lang_payload = json.dumps(audio_language)
    components.html(f'''
    <div style="font-family:Arial,sans-serif;padding:10px 2px;color:var(--text-color,#222)">
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <button id="cs-speak" style="padding:10px 16px;border:0;border-radius:8px;background:#176b70;color:white;cursor:pointer;font-size:14px">▶ Listen in {"Telugu" if language.startswith("Telugu") else "English"}</button>
        <button id="cs-pause" style="padding:10px 14px;border:1px solid #aaa;border-radius:8px;background:transparent;cursor:pointer">⏸ Pause / Resume</button>
        <button id="cs-stop" style="padding:10px 14px;border:1px solid #aaa;border-radius:8px;background:transparent;cursor:pointer">⏹ Stop</button>
      </div>
      <p id="cs-status" role="status" style="font-size:12px;margin-top:8px">Uses your browser's built-in speech voice. No audio is uploaded.</p>
    </div>
    <script>
      const textToRead = {audio_payload};
      const targetLang = {lang_payload};
      const statusEl = document.getElementById('cs-status');
      function getVoice() {{
        const voices = window.speechSynthesis.getVoices();
        const base = targetLang.split('-')[0].toLowerCase();
        return voices.find(v => v.lang && v.lang.toLowerCase() === targetLang.toLowerCase())
          || voices.find(v => v.lang && v.lang.toLowerCase().startsWith(base + '-'))
          || null;
      }}
      function speakCarePlan() {{
        if (!('speechSynthesis' in window)) {{
          statusEl.textContent = 'Speech playback is not supported by this browser. Try current Chrome or Edge.';
          return;
        }}
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(textToRead);
        utterance.lang = targetLang;
        utterance.rate = 0.88;
        const voice = getVoice();
        if (targetLang.startsWith('te') && (!voice || !voice.lang.toLowerCase().startsWith('te'))) {{
          statusEl.textContent = 'No Telugu speech voice was found, so playback was not started. Add/install a Telugu voice in Windows speech settings, then refresh this page.';
          return;
        }}
        if (voice) utterance.voice = voice;
        statusEl.textContent = voice ? ('Reading with: ' + voice.name + ' (' + voice.lang + ')') : 'Reading with the browser default English voice.';
        utterance.onerror = (event) => {{ statusEl.textContent = 'Audio could not start (' + event.error + '). Check that your browser has a voice for this language.'; }};
        window.speechSynthesis.speak(utterance);
      }}
      document.getElementById('cs-speak').addEventListener('click', speakCarePlan);
      document.getElementById('cs-pause').addEventListener('click', () => {{
        if (!('speechSynthesis' in window)) return;
        if (window.speechSynthesis.paused) window.speechSynthesis.resume();
        else if (window.speechSynthesis.speaking) window.speechSynthesis.pause();
      }});
      document.getElementById('cs-stop').addEventListener('click', () => {{
        if ('speechSynthesis' in window) window.speechSynthesis.cancel();
        statusEl.textContent = 'Playback stopped.';
      }});
      if ('speechSynthesis' in window) window.speechSynthesis.onvoiceschanged = () => {{}};
    </script>
    ''', height=105)
    st.caption("Audio follows the selected patient language. Telugu playback requires a Telugu voice to be available in your browser/Windows; medical wording should still be verified before patient use.")

st.markdown("## Faithfulness Review")
source_lower = source_text.lower()
checks = []
for med in plan["medicines"]:
    name = str(med.get("name", "")).strip()
    dose = str(med.get("dose", "")).strip()
    if name:
        checks.append(("Medicine name", name, name.lower() in source_lower))
    if dose:
        checks.append(("Dose", dose, dose.lower() in source_lower))
    source_instruction = str(med.get("how_to_take_plain", "")).strip()
    if source_instruction:
        checks.append(("Source instruction", source_instruction, source_instruction.lower() in source_lower))

with st.container(border=True):
    st.markdown("### Source-faithfulness checks")
    st.caption("Exact-string checks compare extracted fields with the uploaded source text. They support review but do not prove clinical correctness.")
    if not checks:
        st.info("No automatic checks available. Review all fields manually against the original discharge summary.")
    else:
        good = sum(1 for _, _, ok in checks if ok)
        total = len(checks)
        metric_col, pass_col, fail_col = st.columns([2, 1, 1])
        metric_col.metric("Exact-string checks passed", f"{good} / {total}")
        pass_col.metric("Passed", sum(1 for _, _, ok in checks if ok))
        fail_col.metric("Missing / failed", sum(1 for _, _, ok in checks if not ok))
        for kind, value, ok in checks:
            icon = "🟢" if ok else "🔴"
            with st.container(border=True):
                st.markdown(f"{icon} **{kind}**")
                st.caption(value)
                st.markdown("**PASS — exact text found in source**" if ok else "**CHECK — exact text not found; compare manually**")

st.caption("These checks are not the official hackathon evaluator and cannot prove clinical faithfulness.")

export_rows = build_timetable(plan["medicines"], plan.get("stop_medicines", []))
col1, col2, col3 = st.columns(3)
with col1:
    st.download_button("Download Patient Care Plan PDF", make_full_pdf(plan, plain, te_text), "caresimplify_care_plan.pdf", "application/pdf", use_container_width=True)
with col2:
    st.download_button("Download Home Care Fridge Sheet PDF", make_fridge_pdf(plan, language), "caresimplify_fridge_sheet.pdf", "application/pdf", use_container_width=True)
with col3:
    st.download_button("Download Medicine Timetable CSV", make_csv(export_rows), "medicine_timetable.csv", "text/csv", use_container_width=True)

st.markdown("---")
st.caption("Safety: This prototype does not diagnose, prescribe, or replace the discharge instructions. If text is unclear, do not guess; confirm with the treating hospital. Emergency warning signs must remain faithful to the source.")
