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
| 2026-10-30 09:50 | dev-hybrid-1030-095043 | fix: decide Hijri vs Gregorian from the year range in code, not the model's label | dev | hybrid | - | 98.2% | 100.0% | 3.0% | 99.4% | 100.0% | 0.3684 | 0.0683 |
| 2026-10-30 09:51 | dev-hybrid-1030-095134 | fix: extraction prompt states Saudi DD/MM/YYYY date convention | dev | hybrid | - | 98.2% | 100.0% | 3.0% | 99.3% | 100.0% | 0.3684 | 0.0683 |
| 2026-10-30 09:52 | dev-hybrid-1030-095245 | fix: code-triggered careful re-read when a number disagrees with registry/other docs | dev | hybrid | - | 100.0% | 100.0% | 0.0% | 99.4% | 100.0% | 0.3509 | 0.0698 |
| 2026-10-30 09:53 | dev-hybrid-1030-095334 | fix: IBAN checksum check on bank letter (re-read, then ask for clearer copy) | dev | hybrid | - | 98.2% | 100.0% | 3.0% | 99.6% | 100.0% | 0.3684 | 0.0699 |
| 2026-10-30 09:53 | dev-hybrid-1030-095358 | fix: run_checks reports re-read corrections so the agent does not act on the stale first read | dev | hybrid | - | 100.0% | 100.0% | 0.0% | 99.6% | 100.0% | 0.3509 | 0.0699 |
| 2026-10-30 09:57 | dev_zakat-hybrid-1030-095713 | robustness: policy change (Zakat required), config only, no code change | dev_zakat | hybrid | - | 100.0% | 100.0% | 0.0% | 99.7% | 100.0% | 0.3509 | 0.0794 |
| 2026-10-30 10:00 | dev-model-1030-100017 | stability run 1 (cache off) | dev | model | - | 98.2% | 100.0% | 3.0% | 99.3% | 100.0% | 0.3684 | 0.0664 |
| 2026-10-30 10:00 | dev-hybrid-1030-100029 | stability run 1 (cache off) | dev | hybrid | - | 100.0% | 100.0% | 0.0% | 99.6% | 100.0% | 0.3509 | 0.0699 |
| 2026-10-30 10:02 | dev-model-1030-100224 | stability run 2 (cache off) | dev | model | - | 98.2% | 100.0% | 3.0% | 99.5% | 100.0% | 0.3684 | 0.0669 |
| 2026-10-30 10:02 | dev-hybrid-1030-100242 | stability run 2 (cache off) | dev | hybrid | - | 100.0% | 100.0% | 0.0% | 99.6% | 100.0% | 0.3509 | 0.0699 |
| 2026-10-30 10:04 | dev-model-1030-100422 | stability run 3 (cache off) | dev | model | - | 98.2% | 100.0% | 3.0% | 99.3% | 100.0% | 0.3684 | 0.0667 |
| 2026-10-30 10:04 | dev-hybrid-1030-100448 | stability run 3 (cache off) | dev | hybrid | - | 100.0% | 100.0% | 0.0% | 99.6% | 100.0% | 0.3509 | 0.0697 |
| 2026-10-30 10:05 | dev-rules-1030-100509 | rules baseline rerun on final code | dev | rules | - | 77.2% | 100.0% | 0.0% | 79.2% | 66.7% | 0.3158 | 0.0 |
| 2026-10-30 10:05 | dev-rules-no-crossdoc-1030-100511 | rules mode, no crossdoc (final code) | dev | rules | crossdoc | 70.2% | 76.5% | 0.0% | 79.2% | 66.7% | 0.2456 | 0.0 |
| 2026-10-30 10:05 | dev-rules-no-registry-1030-100512 | rules mode, no registry (final code) | dev | rules | registry | 70.2% | 76.5% | 0.0% | 79.2% | 66.7% | 0.2456 | 0.0 |
| 2026-10-30 10:05 | dev-hybrid-no-crossdoc-1030-100537 | ablation: no cross-document check (final code) | dev | hybrid | crossdoc | 98.2% | 100.0% | 3.0% | 99.4% | 100.0% | 0.3684 | 0.0691 |
| 2026-10-30 10:06 | dev-hybrid-no-registry-1030-100605 | ablation: no registry check (final code) | dev | hybrid | registry | 93.0% | 76.5% | 0.0% | 99.6% | 100.0% | 0.2807 | 0.0713 |
| 2026-10-30 10:06 | dev-model-1030-100615 | model-only baseline rerun on final extractor | dev | model | - | 94.7% | 100.0% | 3.0% | 99.3% | 100.0% | 0.3684 | 0.0667 |
