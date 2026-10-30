#!/usr/bin/env bash
# Prompt 9 (Checkpoint C). Run ONCE, only after "freeze": no tuning on held-out, ever.
# Generates the held-out set (seed 2, plus held-out-only layouts and name style), runs every
# mode and ablation once, and writes results/heldout_summary.md.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
git diff --quiet || { echo "Commit first: the frozen system must be a commit." >&2; exit 1; }
FROZEN=$(git rev-parse --short HEAD)
$PY -m scripts.generate --split heldout --seed 2
for args in "--mode hybrid" "--mode rules" "--mode model" "--ablate crossdoc" "--ablate registry"; do
  $PY -m eval.run --split heldout --frozen $args --note "held-out, frozen at $FROZEN"
done
{ $PY -m eval.compare --split heldout; echo; echo "Frozen commit: $FROZEN. Run once; any later change is logged and both scores reported."; } > results/heldout_summary.md
cat results/heldout_summary.md
