# The Seal: supplier onboarding agent

HUMAIN hackathon, Challenge 3 (Autonomous Enterprise).

An agent that onboards Saudi suppliers from a plain email, then keeps guarding them.

- **Onboard:** reads the supplier's PDFs (commercial registration, VAT certificate, bank letter, GOSI/Nitaqat),
  in English or Arabic, scanned or digital; checks them against the Wathq and ZATCA registries (mocked) and against
  each other; emails the supplier to fix routine problems; creates the vendor record.
- **Guard:** freezes any bank-detail change request and asks a human to call the number on file; watches document
  expiry dates, asks for renewals 30 days ahead and puts lapsed vendors on payment hold.
- **A human is involved only for fraud risk.**

"Ariba onboards suppliers. We onboard them, then guard them."

**Try it in two minutes, free, no API key** (needs [uv](https://docs.astral.sh/uv/) or Python 3.11):

```bash
git clone https://github.com/aliaziz36/supplier-onboarding-agent.git && cd supplier-onboarding-agent
uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements.txt
REPLAY=1 ANTHROPIC_API_KEY= .venv/bin/uvicorn app.main:app --port 8000
```

Open http://localhost:8000, click **Open The Seal**, then press `N` to bring in each supplier email (`H` shows the
narration). To check the published numbers: `REPLAY=1 .venv/bin/python -m eval.run --split heldout --frozen --no-log`.
To run the real agent on new suppliers with your own key, see [Run it yourself](#run-it-yourself).

## How it works

The model reads; code checks; the agent decides and acts.

| Layer | What | Where |
|---|---|---|
| Read | Claude (`claude-sonnet-5-5`) turns each PDF into a fixed JSON schema. Code converts Hijri dates and Arabic-Indic digits. | `app/extract.py` |
| Check | Deterministic rules driven by `policy.yaml`: required documents, expiry, Wathq CR status, ZATCA VAT, cross-document names and numbers, IBAN checksum, embedded instructions, extraction confidence. | `app/checks.py`, `app/bank_guard.py` |
| Verify | When a number disagrees with the registry or another document, code triggers one careful second read of that document before anyone acts. | `app/agent.py` (`_reread_disagreements`) |
| Act | A Claude tool-use loop (max 12 tool calls per turn) picks the action and writes the emails. Action tools refuse what the checks do not allow: `create_vendor` needs a clean `run_checks`; a fix-request email cannot go out when there is fraud risk; bank changes can only be frozen. | `app/agent.py` |
| Watch | Daily expiry scan against the demo clock: renewal email at 30 days, payment hold on lapse. Pure code. | `app/watcher.py`, `app/clock.py` |
| Audit | Every tool call, model call and human decision is an event row. The dashboard and the metrics read only the store. | `app/db.py` |

Document and email text is data, never instruction. Policy lives in `policy.yaml`, not in code or the prompt.

## Results

All numbers come from files in `results/`.

**Held-out exam** (`results/heldout_summary.md`): 57 cases generated with a different seed, two document layouts
and one name style that never appear in dev. Run once after freezing the system (commit `f738fee`); never used for tuning.

| Variant | Run id | Decision acc | Fraud recall | False escalation | Field acc | Digital | Scanned | Arabic | $/case |
|---|---|---|---|---|---|---|---|---|---|
| **hybrid** | heldout-hybrid-1030-101142 | **100.0%** | **100.0%** | **0.0%** | 100.0% | 100.0% | 100.0% | 100.0% | 0.0689 |
| rules | heldout-rules-1030-101143 | 52.6% | 100.0% | 48.5% | 71.2% | 66.7% | 0.0% | 44.4% | 0.0 |
| model | heldout-model-1030-101257 | 98.2% | 100.0% | 0.0% | 100.0% | 97.4% | 100.0% | 100.0% | 0.0669 |
| hybrid − crossdoc | heldout-hybrid-no-crossdoc-1030-101326 | 100.0% | 100.0% | 0.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.069 |
| hybrid − registry | heldout-hybrid-no-registry-1030-101357 | 93.0% | 76.5% | 0.0% | 100.0% | 92.3% | 90.9% | 88.9% | 0.0703 |

Rules only catches every fraud but by flagging almost half of the honest suppliers (48.5%) and reads no scans.
Without the registry check, all 4 inactive-CR frauds are onboarded. Without the cross-document check the hybrid
still scores 100% on the exam: the model's own judgment caught the bank-name frauds (98.2% on dev, where it
wrongly flagged one honest supplier). The code check makes that guarantee explicit instead of relying on the model.

**Dev set** (57 generated cases, 10 scenarios, 6 perturbations; used for tuning):

| Variant | Run id | Decision acc | Fraud recall | False escalation | Field acc | Digital | Scanned | Arabic | $/case |
|---|---|---|---|---|---|---|---|---|---|
| hybrid | dev-hybrid-1030-095358 | 100.0% | 100.0% | 0.0% | 99.6% | 100.0% | 100.0% | 100.0% | 0.0699 |
| rules | dev-rules-1030-100509 | 77.2% | 100.0% | 0.0% | 79.2% | 100.0% | 7.1% | 57.1% | 0.0 |
| model | dev-model-1030-100615 | 94.7% | 100.0% | 3.0% | 99.3% | 94.4% | 92.9% | 92.9% | 0.0667 |
| hybrid − crossdoc | dev-hybrid-no-crossdoc-1030-100537 | 98.2% | 100.0% | 3.0% | 99.4% | 100.0% | 92.9% | 92.9% | 0.0691 |
| hybrid − registry | dev-hybrid-no-registry-1030-100605 | 93.0% | 76.5% | 0.0% | 99.6% | 91.7% | 92.9% | 100.0% | 0.0713 |
| rules − crossdoc | dev-rules-no-crossdoc-1030-100511 | 70.2% | 76.5% | 0.0% | 79.2% | 91.7% | 7.1% | 50.0% | 0.0 |
| rules − registry | dev-rules-no-registry-1030-100512 | 70.2% | 76.5% | 0.0% | 79.2% | 91.7% | 7.1% | 50.0% | 0.0 |

What the variants show (dev):
- **Rules only** (pdfplumber + regex, no model) is perfect on digital documents and fails on scans (7.1%) and
  Arabic (57.1%): the model is needed to read.
- **Model only** (no code checks) is close on dev but got bank-change flags wrong in one of four samples
  (it cannot compute the IBAN checksum) and has no guard stopping it from applying a bank change.
- **No registry check:** all 4 inactive-CR frauds were onboarded (fraud recall 76.5%).
- **No cross-document check:** in rules mode 4/5 bank-name frauds get through; in hybrid the model's own judgment
  still caught them, a second, independent line of defence.
- **Stability**, 3 runs with the cache off: hybrid 100/100/100, model-only 98.2/98.2/98.2.
- **Policy change** (Zakat required, config only): 100% on 57 new cases; all old suppliers correctly asked for it.

Iteration log (one row per change): `results/LOG.md`. Robustness (scans, Arabic, policy change, injection,
stability): `results/robustness.md`.

## Run it yourself

Python 3.11.

```bash
uv venv --python 3.11 .venv          # or: python3.11 -m venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env                 # put your ANTHROPIC_API_KEY here for live runs
```

There are two ways to run it. **Replay** is free and needs no key: every model response behind the published
results is committed in `cache/llm/`, so you can check every number and click through the demo exactly as recorded.
**Live** calls the Anthropic API with your key, on the same code: about $0.07 per supplier email.

### Live: run the real agent with your own key

Run one case from the terminal. `NO_CACHE=1` forces real API calls instead of the recorded ones; `-v` prints every
tool call, check and decision:

```bash
NO_CACHE=1 .venv/bin/python -m app.agent data/cases/heldout/heldout_001_clean -v
```

Generate brand-new suppliers that nobody has run before (new seed, new companies, new documents, so nothing can
come from the cache), then run the full evaluation on them:

```bash
CASES_DIR=data/fresh .venv/bin/python -m scripts.generate --split dev --seed 7
CASES_DIR=data/fresh .venv/bin/python -m eval.run --split dev --no-log              # 57 cases, about $4
CASES_DIR=data/fresh .venv/bin/python -m eval.run --split dev --only clean --no-log # a handful, cents
```

Process an email live in the app: start the server without `REPLAY`, open the dashboard, press `H`, pick a case
and click **Process a new email**. It runs through the API step by step, marked **Live**. `LIVE_CASES=<folder>`
offers your own case folders instead of the held-out set.

```bash
.venv/bin/uvicorn app.main:app --port 8000        # key read from .env
```

Change the rules: edit `policy.yaml` (or use `POLICY_PATH=policies/policy_zakat.yaml`) and rerun. No code or
prompt changes needed.

A case is a folder (`email.eml`, the PDFs, `world.json` with the registry records for the mocked Wathq and ZATCA,
`label.json` with the expected outcome); see **Data** below to make your own.

### Replay: reproduce every result without a key

`REPLAY=1` serves only from the cache and fails loudly on a miss.

```bash
REPLAY=1 .venv/bin/python -m eval.run --split dev --mode hybrid --no-log
REPLAY=1 .venv/bin/python -m eval.run --split dev --mode model --no-log
.venv/bin/python -m eval.run --split dev --mode rules --no-log          # rules mode never calls a model
REPLAY=1 .venv/bin/python -m eval.run --split dev --ablate crossdoc --no-log
REPLAY=1 .venv/bin/python -m eval.run --split dev --ablate registry --no-log
REPLAY=1 POLICY_PATH=policies/policy_zakat.yaml .venv/bin/python -m eval.run --split dev_zakat --no-log
REPLAY=1 .venv/bin/python -m eval.run --split heldout --frozen --no-log
.venv/bin/python -m eval.compare --split dev
.venv/bin/python -m pytest -q
```

Stability runs (`NO_CACHE=1`) deliberately bypass the cache, so they need a key.

### The demo

```bash
REPLAY=1 ANTHROPIC_API_KEY= .venv/bin/uvicorn app.main:app --port 8000   # free; open http://localhost:8000/dashboard
```

The dashboard is the product screen a procurement manager would use: inbox, suppliers, approved vendors, bank
change requests, audit log and the rules. The demo plays five supplier emails over a working week on a demo clock.
Presenter keys (nothing presenter-related is visible unless you press `H`): `N` or right arrow = next event,
`B` = back, `R` = start over, `H` = show or hide the narration. `scripts/demo_play.py` plays the same steps from
the terminal. The recording script is `docs/DEMO_SCRIPT.html`; a plain-English guide is `docs/EXPLAINED.html`.

| Step | What happens | What the agent does |
|---|---|---|
| Sun 09:12 | Al Noor Trading sends clean documents (CR in Arabic only) | Reads 4 documents, checks registry, creates the vendor, sends a welcome email |
| Sun 10:40 | Rawabi Logistics' VAT certificate has expired | Emails the supplier for exactly that document |
| Tue 14:05 | Rawabi replies with a renewed certificate | Reads only the new document, re-runs every check, onboards |
| Tue 15:30 | Gulf Steel's bank letter is in another company's name | Stops, does not email the supplier, raises a decision card; the manager rejects |
| Wed 08:47 | A look-alike domain asks to move Al Noor's payments to a new bank | Freezes the change, holds payments, flags domain and bank, asks the manager to call the number on file; the manager rejects |
| 11 months later | Daily expiry scan | Renewal requests to Al Noor and Rawabi; Rawabi's lapsed GOSI certificate puts it on payment hold |

Clicking a document shows the page, why it was identified as that type, and where each field was found. Each
"Ran 17 checks" line opens the full checklist with the values compared and their source (Wathq, ZATCA,
cross-document, policy.yaml).

## Data

`scripts/generate.py` is a seeded generator. A case is a folder: `email.eml` (MIME, attachments embedded), the PDFs,
`world.json` (mock registry records and any vendor already on file) and `label.json` (expected decision, documents
to request, fraud flags, and the ground truth for every field of every document).

```bash
.venv/bin/python -m scripts.generate --split dev --seed 1
.venv/bin/python -m scripts.generate --split demo
POLICY_PATH=policies/policy_zakat.yaml .venv/bin/python -m scripts.generate --split dev_zakat --seed 1
```

Perturbations: scanned look (rasterised, rotated 1–3°, blurred, noise, no text layer), Arabic-only documents,
company-name variants, Hijri and long-form dates, irrelevant extra attachments, instructions embedded in PDFs.
The held-out split uses seed 2 plus two layouts and one name style that never appear in dev.

## Layout

```
policy.yaml, policies/        onboarding rules as config
app/                          agent, extraction, checks, bank guard, watcher, registry mock, store, server
eval/                         run.py (one command per number), metrics.py, compare.py
scripts/                      generate.py, demo_play.py
data/cases/{dev,demo,...}     generated cases
cache/llm/                    committed model responses for replay
results/                      results files, LOG.md, comparison and robustness reports
tests/                        rules oracle, watcher, regression replay
web/                          dashboard (index.html), start page, logo
```

## Limits

Synthetic data; mocked Wathq and ZATCA; no real ERP; the API does not accept `temperature`, so repeatability is
measured (stability runs) and replay comes from the cache.
