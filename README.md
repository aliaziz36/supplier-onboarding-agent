# Supplier Onboarding Agent

HUMAIN hackathon, Challenge 3 (Autonomous Enterprise).

An agent that onboards Saudi suppliers from a plain email, then keeps guarding them.

- **Onboard:** reads the supplier's PDFs (commercial registration, VAT certificate, bank letter, GOSI/Nitaqat),
  in English or Arabic, scanned or digital; checks them against the Wathq and ZATCA registries (mocked) and against
  each other; emails the supplier to fix routine problems; creates the vendor record.
- **Guard:** freezes any bank-detail change request and asks a human to call the number on file; watches document
  expiry dates, asks for renewals 30 days ahead and puts lapsed vendors on payment hold.
- **A human is involved only for fraud risk.**

"Ariba onboards suppliers. We onboard them, then guard them."

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

All numbers come from files in `results/`. Dev set: 57 generated cases (10 scenarios, 6 perturbations).
The dev set was used for tuning; **held-out results are added after the freeze** (`results/heldout_summary.md`).

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

## Install

Python 3.11.

```bash
uv venv --python 3.11 .venv          # or: python3.11 -m venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env                 # add ANTHROPIC_API_KEY only if you want live model calls
```

## Reproduce every result without an API key

Every model response used in the results is cached in `cache/llm/`, keyed by a hash of the full request.
`REPLAY=1` serves only from that cache and fails loudly on a miss.

```bash
REPLAY=1 .venv/bin/python -m eval.run --split dev --mode hybrid --no-log
REPLAY=1 .venv/bin/python -m eval.run --split dev --mode model --no-log
.venv/bin/python -m eval.run --split dev --mode rules --no-log          # rules mode never calls a model
REPLAY=1 .venv/bin/python -m eval.run --split dev --ablate crossdoc --no-log
REPLAY=1 .venv/bin/python -m eval.run --split dev --ablate registry --no-log
REPLAY=1 POLICY_PATH=policies/policy_zakat.yaml .venv/bin/python -m eval.run --split dev_zakat --no-log
.venv/bin/python -m eval.compare --split dev
.venv/bin/python -m pytest -q
```

Stability runs (`NO_CACHE=1`) deliberately bypass the cache, so they need a key.

## Run the demo

```bash
.venv/bin/uvicorn app.main:app --port 8000        # open http://localhost:8000
.venv/bin/python -m scripts.demo_play             # plays the 5 scenes with pauses
```

The simulator buttons post a demo case's `.eml` to the same handler a real inbox would use.

| Scene | What happens | What the agent does |
|---|---|---|
| 1 | Al Noor Trading sends clean documents (CR in Arabic only) | Reads 4 documents, checks registry, creates the vendor, sends a welcome email |
| 2 | Rawabi Logistics' VAT certificate has expired | Emails for a renewal; when the reply arrives, re-checks only the new document and onboards |
| 3 | Gulf Steel's bank letter is in another company's name | Stops, does not email the supplier, raises a decision card with the evidence |
| 4 | A look-alike domain asks to move Al Noor's payments to a new bank | Freezes the change, holds payments, flags the domain and bank mismatch, asks the manager to call the number on file |
| 5 | Fast-forward 11 months | Al Noor's CR expires in 20 days: renewal email sent, vendor marked at risk; a lapsed GOSI certificate puts Rawabi on payment hold |

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
web/index.html                dashboard
```

## Limits

Synthetic data; mocked Wathq and ZATCA; no real ERP; the API does not accept `temperature`, so repeatability is
measured (stability runs) and replay comes from the cache.
