# Evaluation

Locked split: `data/derived/splits.json` (seed **42**, 50 dev / **150** test).

Gold labels are derived from GNOTHEIA structured fields (document types, claim
header fields, policy gate statuses). Metrics:

| Metric | Definition |
| --- | --- |
| Classification accuracy / macro-F1 | Predicted `document_type` vs gold per document |
| Extraction field accuracy | Exact match on claim header fields; `damagedItems` scored by **normalized risk-set equality** (subjects are free-form inventory names) |
| Per-field accuracy | Same match, reported per field. Gold includes `claimant` |
| Citation rate | Share of extracted fields that include at least one source quote |
| Policy-check status accuracy | Deterministic gates on **AI-extracted** claim fields (+ policy record as the policy DB) vs gold; reported **per check** and as a mean |

Amount-conflict detection is a heuristic over document text. It is **not** graded
against independent labels and is omitted from the headline table.

Default model: `eu.amazon.nova-micro-v1:0`.

## Eval-driven fixes

1. **Pipe-collapsed fields** — Nova Micro sometimes joined several field names /
   values with `|`. Deterministic repair in `pipeline/extract.py`.
2. **Truncated JSON** — long citation strings could hit `maxTokens` mid-object.
   JSON repair + one retry with a higher token budget in `llm/client.py`; extract
   prompts ask for short quotes (≤20 words).
3. **Honest gates** — policy checks and required-doc rules use extracted /
   classified outputs, not gold claim fields / gold document types.
4. **No claimId hint** — extraction must find claimId in the documents when present.
5. **Gold `claimant`** — `extraction_gold()` now includes `claimant` (was missing → fake 0.0).
6. **`damagedItems` parsing** — accept JSON-encoded list strings from the model;
   score by risk set (not free-form subject strings).
7. **Peril gate** — match extracted risks against the union of policy covered risks
   (extracted subjects rarely equal coarse policy subject names).

## Locked test numbers (published)

Run: `2026-11-23T23:32:05Z` · full **150** claims of the locked test split ·
**0** claim-level errors · artifact `eval/results/published_test_summary.json`.

| Split | n claims | Model | Classify acc | Classify macro-F1 | Extract field acc | Citation rate | Policy-check mean |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| test | 150 | `eu.amazon.nova-micro-v1:0` | 0.970 | 0.948 | 0.803 | 0.957 | 0.909 |

Per-field extract accuracy:

| claimId | policyId | dateOfLoss | dateOfReported | lossEvent | claimant | product | damagedItems (risk set) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.833 | 0.607 | 1.000 | 0.807 | 0.720 | 0.907 | 0.820 | 0.733 |

Policy-check status accuracy (per check):

| coverage_period | policy_status | peril_covered |
| ---: | ---: | ---: |
| 1.000 | 1.000 | 0.727 |

Tokens: **1,542,244** in / **190,001** out — on the order of **~$0.08** at Nova Micro list rates
(excl. infra).

```bash
claims-eval --split test --limit 20   # smoke
claims-eval --split test --limit 150  # published table
```
