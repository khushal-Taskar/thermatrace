# Free-tier deployment runbook

## Target architecture

```mermaid
flowchart LR
    U[Browser] -->|HTTPS, same-origin API| V[Vercel: Next.js]
    V -->|REST proxy| R[Render: FastAPI]
    U -->|WSS telemetry| R
    R -->|TLS PostgreSQL| S[Supabase]
    R -->|Public routing requests| O[OSRM]
    U -->|Map tiles| M[OpenStreetMap]
```

This layout keeps the public demo within eligible free tiers and preserves persistent database state. Render can spin down after inactivity, so the first request after a quiet period may take roughly a minute. Vercel and Render provide HTTPS subdomains; a purchased domain is optional.

## 1. Publish the repository

Create an empty GitHub repository named `thermatrace` and push this project root. Do not publish `backend/.env`, `backend/data`, voice models, generated reports, or build output; all are excluded by `.gitignore`.

## 2. Create PostgreSQL on Supabase

1. Create a free Supabase project in the nearest region.
2. Open **Connect** and copy the **Session pooler** URI. Render uses IPv4, so the pooler is safer than an IPv6-only direct connection.
3. Change the URI scheme from `postgresql://` to `postgresql+psycopg://`.
4. Keep `sslmode=require` in the query string.

Example shape only:

```text
postgresql+psycopg://postgres.PROJECT_REF:PASSWORD@REGION.pooler.supabase.com:5432/postgres?sslmode=require
```

Never commit this value.

## 3. Deploy FastAPI and WebSocket on Render

1. In Render, choose **New > Blueprint** and select the GitHub repository.
2. Render discovers `/render.yaml` and creates `thermatrace-api` on the free plan.
3. Supply the prompted secret values:
   - `DATABASE_URL`: the Supabase URI from step 2.
   - `ADMIN_PASSWORD`: a new demo password with at least 12 characters.
   - `FRONTEND_ORIGINS`: initially `https://placeholder.invalid`; replace it after Vercel assigns the final domain.
4. Wait for `/api/health` to return an HTTP 200 response.

The start command applies all Alembic migrations before starting Uvicorn. The backend seeds five demonstration vehicles on the first empty database.

## 4. Deploy Next.js on Vercel

1. Import the same GitHub repository into Vercel.
2. Set **Root Directory** to `frontend`.
3. Keep the detected Next.js build settings.
4. Add production environment variables:

```text
BACKEND_URL=https://YOUR-RENDER-SERVICE.onrender.com
NEXT_PUBLIC_WS_URL=wss://YOUR-RENDER-SERVICE.onrender.com/ws/telemetry
```

5. Deploy and copy the assigned `https://PROJECT.vercel.app` URL.

## 5. Lock the backend to the frontend origin

In Render, replace `FRONTEND_ORIGINS` with the exact Vercel origin, without a trailing slash:

```text
https://PROJECT.vercel.app
```

Save the variable and let Render restart. Additional trusted origins can be comma separated.

## 6. Acceptance checks

1. Open the Vercel URL and sign in with `admin@thermatrace.local` plus the Render `ADMIN_PASSWORD`.
2. Confirm that Dashboard shows five vehicles and the status changes from **Connecting** to **Live**.
3. Open Live Tracking and verify that speed, marker position, delivery progress, and risk values update without refreshing.
4. Trigger **LOW BATTERY** from the demo controls and verify that an alert and risk explanation appear.
5. Acknowledge the alert, download a PDF report, and reload the site to verify PostgreSQL persistence.
6. Open Voice Center. Typed questions and browser speech work in cloud mode. Use the local project for microphone transcription and the complete Ollama/Whisper/Piper stack.

## Environment ownership

| Variable | Service | Secret |
|---|---|---:|
| `DATABASE_URL` | Render | Yes |
| `ADMIN_PASSWORD` | Render | Yes |
| `ADMIN_EMAIL` | Render | No |
| `FRONTEND_ORIGINS` | Render | No |
| `COOKIE_SECURE` | Render | No |
| `SMTP_HOST` | Render | No |
| `SMTP_PORT` | Render | No |
| `SMTP_USERNAME` | Render | Yes |
| `SMTP_PASSWORD` | Render | Yes |
| `SMTP_FROM` | Render | No |
| `SMTP_STARTTLS` / `SMTP_USE_SSL` | Render | No |
| `BACKEND_URL` | Vercel | No |
| `NEXT_PUBLIC_WS_URL` | Vercel | No |

The seeded admin password is read only while creating the first database user. Changing the environment variable later does not replace the password stored in an existing database.
