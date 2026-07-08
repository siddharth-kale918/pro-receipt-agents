# pro-receipt-agents — data_generate scripts

Python scripts for running the pro-receipt lifecycle locally: DB reset, seed, create → submit → approve.

## Setup

```bash
cd /path/to/pro-receipt-agents
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Configure .env.prime

Copy and fill in both env files (gitignored):

**`scripts/data_generate/.env.prime`** — synced to `pro-receipt/.env` on every run:

```dotenv
PRO_RECEIPT_CODEBASE_PATH=/Users/you/Documents/workspace/pro-receipt

# API
API_PORT=3003
ENTITY_ID=04eb277c-f9cd-42b0-9610-0f068f6aaea1

# Database
DB_HOST=127.0.0.1
DB_PORT=5443
DB_USERNAME=pro-receipts
DB_PASSWORD=pro-receipts
DB_DATABASE=receipts_local
DB_SSL=false

# Auth (stub mode — no real Auth0 needed)
AUTH_MODE=stub

# Platform API (for submit/approve PO validation)
PLATFORM_API_HOST=controlpanel.ogintegration.us
PLATFORM_API_KEY=<your-key>
ERP_FMS_HOST=https://erp.fms.ogintegration.us
PO_API_BASE_URL=https://controlpanel.ogintegration.us/api/v1/po

# Kafka
KAFKA_SKIP_PUBLISH=true
KAFKA_BROKERS=localhost:9392
KAFKA_CLIENT_ID=pro-receipts-api
KAFKA_RECEIPT_SUBMITTED_TOPIC=opengov.procurement.receipt.v1
KAFKA_SSL=false

# S3 / Localstack
LOCALSTACK_PORT=4577
S3_ENDPOINT_URL=http://localhost:4577
S3_BUCKET=og-receipts-local-attachments
S3_REGION=us-east-1
S3_ACCESS_KEY_ID=test
S3_SECRET_ACCESS_KEY=test

# Observability
OTEL_SERVICE_NAME=pro-receipts-api
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4319

# CORS
CORS_ENABLED=true
CORS_ALLOWED_ORIGINS=http://localhost:3006,https://procurement.loc.ogintegration.us
CORS_ALLOWED_METHODS=GET,POST,PUT,DELETE,OPTIONS,PATCH
CORS_ALLOWED_HEADERS=Content-Type,Authorization,Token,traceparent
CORS_CREDENTIALS=true
CORS_MAX_AGE=86400
```

**`scripts/data_generate/.env.prime.e2e`** — synced to `pro-receipt/apps/e2e/.env` manually when running E2E tests:

```dotenv
E2E_USER_EMAIL=your-email@example.com
E2E_USER_PASSWORD=your-password
E2E_WORKERS=4
E2E_FRONTEND_URL=https://procurement.loc.ogintegration.us
E2E_API_URL=http://localhost:3003
E2E_LOGIN_STRATEGY=local-harness
E2E_TARGET_MODE=local
E2E_PO_NUMBER=PO-2026-001259
E2E_PO_LINE_DESCRIPTION=Pencils
E2E_PO_VENDOR_NAME=E2E Playwright - PO Receipt
E2E_AUTO_APPROVE_ENABLED=false
E2E_MENTION_NAME_PREFIX=playwright
```

## Env files in pro-receipt (2 total)

| agents file | synced to |
|---|---|
| `.env.prime` | `pro-receipt/.env` (API config) |
| `.env.prime.e2e` | `pro-receipt/apps/e2e/.env` (E2E test config) |

## Usage

### Full lifecycle (stop → cleanup → start → seed → create → submit → approve)

```bash
cd scripts/data_generate
python run_lifecycle.py --scenario s1
```

### Individual steps

```bash
python stop_pro_receipt_api.py
python clean_up_data.py --yes
python start_pro_receipt_api.py
python seed_data.py
python create_receipts.py --scenario s1
python submit_receipts.py --scenario s1
python approve_receipts.py --scenario s1
```

### Partial runs

```bash
# Skip infrastructure (already running), just run data steps
python run_lifecycle.py --scenario s1 --from create

# Only create drafts, skip submit/approve
python run_lifecycle.py --scenario s3 --stop-after create

# Run all scenarios
python run_lifecycle.py --all
```

### List available scenarios

```bash
python run_lifecycle.py --list
```

## Scenarios

| Scenario | Description |
|---|---|
| s1 | Single receipt — draft, submit, approve against a real integration PO |
| s2 | Multi-receipt batch — two receipts against different PO lines |
| s3 | Draft-only — create receipts but skip submit/approve (useful for UI testing) |
| s4 | Partial receipt — received quantity less than PO quantity |

## State files (gitignored)

Each step writes a state JSON into `data/`:

| File | Written by |
|---|---|
| `{scenario}_state_create.json` | `create_receipts.py` |
| `{scenario}_state_submit.json` | `submit_receipts.py` |
| `{scenario}_state_approve.json` | `approve_receipts.py` |

## Notes

- **Stub auth**: the API runs with `AUTH_MODE=stub`, so any Bearer token is accepted. Scripts send `Bearer stub-token`.
- **PO validation**: `submit` and `approve` call the real PO API at `PO_API_BASE_URL`. Ensure your `PLATFORM_API_KEY` is valid and the PO numbers in `scenarios.yml` exist in the integration environment.
- **E2E env**: `.env.prime.e2e` must be manually copied to `pro-receipt/apps/e2e/.env` before running `bun run test:e2e`.
