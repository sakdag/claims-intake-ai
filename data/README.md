# Data layout

| Path | Purpose | Git |
| --- | --- | --- |
| `raw/` | Downloaded GNOTHEIA parquet + `VERSION.json` | ignored (large) |
| `fixtures/` | Tiny committed samples for CI / smoke tests | committed |
| `derived/` | Ground-truth labels + locked splits | ignored (regenerate) |

Download:

```bash
pip install -e '.[data]'
claims-download-data
```
