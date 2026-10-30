# Iteration log

One row per change. Dev set unless noted. Numbers come from `results/<run-id>.json`.

| Date | Run id | Change | Split | Mode | Ablate | Decision acc | Fraud recall | False escalation | Field acc | Follow-up precision | Human touches/case | $/case |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-30 09:41 | dev-hybrid-1030-094122 | first dev run (baseline) | dev | hybrid | - | 96.5% | 100.0% | 6.1% | 99.3% | 100.0% | 0.386 | 0.0683 |
| 2026-10-30 09:46 | dev-rules-1030-094653 | rules-only baseline (pdfplumber + regex, no model) | dev | rules | - | 77.2% | 100.0% | 0.0% | 79.2% | 66.7% | 0.3158 | 0.0 |
| 2026-10-30 09:48 | dev-model-1030-094836 | model-only baseline (no code checks) | dev | model | - | 96.5% | 100.0% | 0.0% | 99.3% | 100.0% | 0.3509 | 0.0666 |
| 2026-10-30 09:49 | dev-hybrid-no-crossdoc-1030-094903 | ablation: no cross-document check | dev | hybrid | crossdoc | 96.5% | 100.0% | 6.1% | 99.3% | 100.0% | 0.386 | 0.0684 |
| 2026-10-30 09:49 | dev-hybrid-no-registry-1030-094933 | ablation: no registry check | dev | hybrid | registry | 89.5% | 76.5% | 6.1% | 99.3% | 100.0% | 0.3158 | 0.0697 |
| 2026-10-30 09:49 | dev-rules-no-crossdoc-1030-094950 | rules mode, ablation: no crossdoc (isolates the code check) | dev | rules | crossdoc | 70.2% | 76.5% | 0.0% | 79.2% | 66.7% | 0.2456 | 0.0 |
| 2026-10-30 09:49 | dev-rules-no-registry-1030-094952 | rules mode, ablation: no registry (isolates the code check) | dev | rules | registry | 70.2% | 76.5% | 0.0% | 79.2% | 66.7% | 0.2456 | 0.0 |
