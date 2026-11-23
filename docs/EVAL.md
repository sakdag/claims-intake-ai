# Evaluation

Locked split: `data/derived/splits.json` (seed **42**, 50 dev / **150** test).

Gold labels are derived from GNOTHEIA structured fields (document types, claim
header fields, policy gate statuses). Metrics:

| Metric | Definition |
| --- | --- |
| Classification accuracy / macro-F1 | Predicted `document_type` vs gold per document |
| Extraction field accuracy | Exact match on claim header fields + `damagedItems` (set equality). `claimId` is **not** hinted in the prompt |
| Per-field accuracy | Same exact-match, reported per field |
| Citation rate | Share of extracted fields that include at least one source quote |
| Policy-check status accuracy | Deterministic gates run on **AI-extracted** claim fields (+ policy record as the policy DB) vs gold gate statuses |

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

## Locked test numbers (published)

Run: `2026-11-23T18:14:14Z` · full **150** claims of the locked test split ·
**0** claim-level errors · artifact `eval/results/published_test_summary.json`.

| Split | n claims | Model | Classify acc | Classify macro-F1 | Extract field acc | Citation rate | Policy-check status acc |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| test | 150 | `eu.amazon.nova-micro-v1:0` | 0.971 | 0.949 | 0.597 | 0.969 | 0.667 |

Per-field extract accuracy (same run):

| claimId | policyId | dateOfLoss | dateOfReported | lossEvent | claimant | product | damagedItems |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.827 | 0.607 | 1.000 | 0.800 | 0.707 | 0.000 | 0.833 | 0.000 |

`claimant` / `damagedItems` are weak on Nova Micro with the current prompt (policy-check
score is capped by empty `damagedItems` → peril gate often `UNRESOLVABLE` vs gold `PASSED`).

Tokens: **1,542,244** in / **190,001** out — on the order of **~$0.08** at Nova Micro list rates
(excl. infra).

```bash
claims-eval --split test --limit 20   # smoke
claims-eval --split test --limit 150  # published table
```
