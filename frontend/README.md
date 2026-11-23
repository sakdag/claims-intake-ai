# Adjuster review UI

React + TypeScript (Vite). Calls the FastAPI operator API directly
(`VITE_API_BASE`, default `http://127.0.0.1:8000`).

```bash
# terminal 1 — API
cd ..
source .venv/bin/activate
export AWS_PROFILE=personal CLAIMS_AWS_REGION=eu-north-1
export CASES_TABLE=… AUDIT_TABLE=…   # from terraform output
export CLAIMS_APPROVAL_HMAC_SECRET=…
export SES_FROM_EMAIL=… SES_TO_EMAIL=…
uvicorn claims_intake.api.app:app --reload --port 8000

# terminal 2 — UI
cd frontend
npm install
npm run dev   # http://localhost:5173
```
