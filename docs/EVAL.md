# Evaluation

Locked split: `data/derived/splits.json` (seed **42**, 50 dev / 150 test).

Gold labels are derived from GNOTHEIA structured fields (document types, claim
header fields, policy gate statuses, amount-conflict pseudo-labels). Metrics:

| Metric | Definition |
| --- | --- |
| Classification accuracy / macro-F1 | Predicted `document_type` vs gold per document |
| Extraction field accuracy | Exact match on claim header fields (claimId, policyId, dates, lossEvent, claimant, product) |
| Citation rate | Share of extracted fields that include at least one source quote |
| Amount-conflict P/R | Detector vs its own pseudo-label definition (sanity check; tune on dev) |

Default model: `eu.amazon.nova-micro-v1:0`.

## Eval-driven fixes

1. **Pipe-collapsed fields** — Nova Micro sometimes joined several field names /
   values with `|`. Deterministic repair in `pipeline/extract.py`.
2. **Truncated JSON** — long citation strings could hit `maxTokens` mid-object.
   JSON repair + one retry with a higher token budget in `llm/client.py`; extract
   prompts ask for short quotes (≤20 words).

## Locked test numbers (published)

Run: `2026-11-23T14:01:03Z` · first **20** claims of the locked test split ·
**0** claim-level errors · artifact `eval/results/published_test_summary.json`.

| Split | n claims | Model | Classify acc | Classify macro-F1 | Extract field acc | Citation rate | Conflict P | Conflict R |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| test | 20 | `eu.amazon.nova-micro-v1:0` | 0.986 | 0.981 | 0.842 | 1.000 | 1.000 | 1.000 |

Tokens: **202,964** in / **21,042** out. At Nova Micro list rates this is on the
order of **~$0.01** for the 20-claim pass (excl. infra). Dominant extract
confusions in this slice: `photo_evidence` → `site_inspection` (2) /
`police_confirmation` (1).

```bash
claims-eval --split test --limit 20
# optional full locked test:
claims-eval --split test --limit 150
```
