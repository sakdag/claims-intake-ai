# Elm & Stone — AI claims intake

Simulated Forward Deployed / Applied AI engagement for a fictional mid-size
Central European home insurer (**Elm & Stone Home Insurance**).

Adjusters spend early claim time sorting documents, re-keying fields, checking
basics against the policy, and chasing missing paperwork. This project turns
incoming multi-document claims into **ready-to-work cases** with human oversight:
classify → extract (with citations) → reconcile conflicts → apply gate rules →
summarise → draft missing-doc requests (approval required before send).


## Status

See [`PROGRESS.md`](PROGRESS.md) for the MVP checklist and session log.

## Constraints

- Data stays in the customer’s own AWS account / EU region (`eu-north-1`)
- Every automated step is auditable (inputs, decision, component, model version)
- AI may classify, extract, check, summarise, draft, and flag — **never** approve or deny a claim
- Outbound claimant messages require **signed, single-use** adjuster approval

## Stack (planned)

| Layer | Choice |
| --- | --- |
| Core / workers | Python 3.12 |
| API | FastAPI |
| Review UI | React + TypeScript |
| Orchestration | AWS Step Functions + Lambda |
| Models | Amazon Bedrock (configurable; cheapest capable that passes eval) |
| Infra | Terraform, KMS, least-privilege IAM |

## Data

Primary dataset: [GNOTHEIA synthetic insurance dataset v2](https://huggingface.co/datasets/gratex/GNOTHEIA-synthetic-insurance-dataset-v2)
(Apache-2.0). Credit: Gratex International a.s. / InnovAIte.

```bibtex
@dataset{gnotheia_synthetic_insurance_2026,
  title        = {GNOTHEIA Synthetic Insurance Dataset},
  author       = {{Gratex International a.s.}},
  year         = {2026},
  publisher    = {Hugging Face},
  url          = {https://huggingface.co/datasets/gratex/GNOTHEIA-synthetic-insurance-dataset},
  project      = {InnovAIte},
  license      = {Apache-2.0}
}
```

## Local setup

```bash
cd claims-intake-ai
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Dataset download and eval commands will land as MVP items M2–M6 land.

## License

Apache-2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
