# FastAPI service

Source: `packages/examwatch/api`. Install from the repository root with `uv sync --frozen`.

Development: copy `.env.example` to `.env`, generate a random signing secret, set an explicit demo token, then run `uv run examwatch-api`.

Production: `render.yaml` starts the same API with Postgres and Supabase. No SQLite fallback or demo authentication is allowed in production. Configure the database URL and Supabase server key directly in Render's secret environment fields.

Retention runs at startup and every hour while the service is awake. Expired evidence is immediately denied by the API even before physical deletion. A paid always-on instance or scheduled `examwatch-cleanup` job is needed for predictable physical deletion while free instances sleep.
