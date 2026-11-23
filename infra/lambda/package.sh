#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/build/lambda"
ZIP="$ROOT/build/claims_intake_lambda.zip"

rm -rf "$OUT" "$ZIP"
mkdir -p "$OUT"

# Cross-build Linux x86_64 wheels for Lambda (host may be macOS ARM).
python3.12 -m pip install \
  "pydantic>=2.7,<3" \
  "pydantic-settings>=2.3,<3" \
  "orjson>=3.10" \
  "tenacity>=8.3" \
  "structlog>=24.1" \
  "python-dateutil>=2.9,<3" \
  "httpx>=0.27" \
  "fastapi>=0.115,<1" \
  "mangum>=0.19,<1" \
  "starlette>=0.38,<1" \
  "python-multipart>=0.0.9" \
  -t "$OUT" --quiet \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all:

cp -R "$ROOT/src/claims_intake" "$OUT/claims_intake"

find "$OUT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

(
  cd "$OUT"
  zip -qr "$ZIP" .
)

# Sanity: pydantic_core should be a linux wheel, not macosx
if find "$OUT" -name '*pydantic_core*' | rg -q 'macosx'; then
  echo "ERROR: macOS pydantic_core still in package" >&2
  exit 1
fi

echo "Wrote $ZIP ($(du -h "$ZIP" | cut -f1))"
