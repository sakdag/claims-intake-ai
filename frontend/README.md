# Adjuster review UI

React + TypeScript (Vite).

## Hosted API (Cognito)

```bash
cd ../infra/terraform
AWS_PROFILE=personal terraform output -raw frontend_env_hint > ../../frontend/.env.local
cd ../../frontend
npm install
npm run dev   # sign in with Cognito adjuster user
```

## Local API fallback

Omit Cognito `VITE_*` vars (or use `.env.example` with only `VITE_API_BASE=http://127.0.0.1:8000`)
and run FastAPI locally with AWS credentials.
