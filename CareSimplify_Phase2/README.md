# CareSimplify — TalentAP Mega Hackathon H2

CareSimplify converts a discharge summary into a structured, patient-facing home-care draft. This project has two parts: (1) a Streamlit demonstration app and (2) a separate offline H2 submission pipeline built around the **official starter pack and official evaluator**.

## How this matches the H2 brief

- Structured fields: active medicines, stop instructions, warning signs, diet, activity and follow-up dates.
- English care-plan text plus a Telugu (`te`) draft. Drug names, doses and dates are kept in Latin script/Western digits; Telugu labels and safety wording are provided. Have a fluent Telugu speaker review translations.
- Approximate English readability score.
- One-page fridge-sheet PDF and full care-plan PDF.
- Styled patient care-plan PDF and colourful one-page home-care fridge-sheet PDF.
- Medicine timetable CSV export; no exact clock time is inferred from a frequency code.
- Official-format JSONL predictions for all 300 test summaries, using the supplied `HACKATHON_STARTER_PACK` and `evaluate.py`.
- Human-in-the-loop safety: this is a draft generator, not a diagnostic/prescribing tool.

## Included source materials

`HACKATHON_STARTER_PACK/` is extracted from the supplied official ZIP and includes the synthetic summaries, glossary, drug reference, dev fact key, 50 examples, baseline, `evaluate.py`, and organiser documentation. All dataset records are synthetic. The pack itself notes its gold examples are AI-agent written/reviewed rather than clinician-authored; they are examples, not clinical guidance.

The original problem statement and coding-guidelines PDFs informed the deliverable. No real patient data is included.

## Run the Streamlit demo (Windows)

```bat
py -m venv .venv
.venv\Scripts\activate
pip install -r FULL_CODE\requirements.txt
python -m streamlit run FULL_CODE\app.py
```

Upload a text-based PDF/TXT or choose the built-in demo. Review all extracted fields against the original discharge summary before downloading outputs. Scanned PDFs need OCR, which is not included.

## Validate on the public dev set

From the project root:

```bat
pip install -r FULL_CODE\requirements.txt
python FULL_CODE\hackathon_pipeline.py --split dev
python HACKATHON_STARTER_PACK\evaluate.py --submission submission\H2_predictions_dev.jsonl --truth HACKATHON_STARTER_PACK\data\dev_fact_key.jsonl --out submission\dev_score.json
```

**Recorded local dev result at packaging time:** primary score **0.8676** across 200 public dev summaries; medicine recall 0.9983, dose accuracy 0.9623, frequency accuracy 0.8834, duration accuracy 0.9821, follow-up date recall 1.0000, stop recall 1.0000, and zero translation script-check failures. This is a development score only, not a guarantee of hidden-test performance. Use the included evaluator to reproduce it after installing dependencies.

## Build the 300-row test submission ZIP

```bat
python FULL_CODE\prepare_submission.py
```

This writes `submission/H2_predictions.jsonl`, validates it contains exactly the 300 IDs in `test_ids.csv`, and creates `teamID_H2.zip`. Rename the ZIP to the organiser's required filename using your actual team ID before uploading. The generated predictions are a rules-based baseline and should be reviewed/improved before final submission.

## Files

- `FULL_CODE/app.py` — Streamlit UI and export controls.
- `FULL_CODE/care_plan.py` — UI extractor, readable text, readability estimate, conservative Telugu headings.
- `FULL_CODE/timetable.py` — frequency-aware timetable; does not invent clock times.
- `FULL_CODE/exports.py` — styled PDFs and CSV export.
- `FULL_CODE/hackathon_pipeline.py` — official-format H2 predictions from the starter-pack data.
- `FULL_CODE/prepare_submission.py` — validates and packages the 300 test predictions.
- `FULL_CODE/tests/` — basic app-core tests.
- `HACKATHON_STARTER_PACK/evaluate.py` — official local scorer supplied by organisers.

## Updated visual exports

The app creates colour-coded, structured PDFs from the existing extracted plan data, preserves the original source wording, and offers the two PDF downloads plus the medicine timetable CSV. CSV is plain text by format design.

## Safety and limitations

- The starter pack says the dataset is synthetic and its glossary/drug reference are simplified hackathon resources, not clinical references.
- The pipeline is a transparent regex/rule-based baseline. It can still miss or misread dose, frequency, route, timing or duration; a good dev score is not proof of clinical safety.
- Never use this prototype as a substitute for a clinician. Do not use real patient data in the demo. Escalate unclear or conflicting instructions to the treating team.
- Telugu wording is a draft. Clinical details are retained conservatively; fluent-language and clinician review are required before real-world use.
- This project does not require Gemini, an API key, or an internet connection for the core pipeline.
- Disclose AI-assistant/pre-built-code use as required by the hackathon rules.

### Telugu output note (updated)
The app now embeds a Telugu-capable Noto Sans Telugu font in generated PDFs and translates common patient-facing labels and a small set of standard warning/diet/activity phrases. Drug names, doses, numeric schedules, dates, and source instructions are deliberately preserved to avoid changing medical meaning. This is still a conservative phrase-based translation, not a general-purpose medical translator: any unmatched clinical sentence may remain in English and must be reviewed by a fluent Telugu speaker and the treating clinician. Re-run the app and download a fresh PDF after replacing the old project folder.

### Interactive 7-day medicine tracker
The Streamlit app includes an interactive checkbox tracker in the 7-day timetable tab. It stores dose marks locally in `FULL_CODE/data/medication_log.json` (the `data/` directory is gitignored). Choose the Day 1 date, then tick a dose only after it has actually been given. The tracker is a single-computer prototype, not a secure multi-user clinical record. Unknown durations and SOS/PRN medicines are not turned into fixed daily checkboxes. Numeric `1-0-1`-style patterns use the source's conventional day-part positions; verify each schedule against the original discharge instruction and care team.

Run tests with:

```bat
python -m pytest FULL_CODE\tests -q
```


## Phase 2 goal-based care plan additions

The existing Streamlit application and discharge-summary workflow are preserved. The left sidebar now includes **Health Goal Settings** and the output area includes **Goal-Based Care Plan** and **My Progress** tabs. Progress entries are stored locally in `FULL_CODE/data/goal_progress.json`.

The current repository explicitly states that no Gemini key or paid AI API is required and uses rule-based extraction. Accordingly, the Phase 2 goal-plan builder is a conservative, source-grounded rule-based draft rather than a new generative AI integration. It does not invent clinical targets or medication doses. A clinician must review the draft before patient use.

A backup of the original application is included as `FULL_CODE/app.py.phase2_backup`.
