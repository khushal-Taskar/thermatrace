# Cost and free-deployment guide

## Zero-cost project mode

The complete evaluated project can run locally at no service cost. Next.js, React, FastAPI, SQLite, scikit-learn, pandas, NumPy, Leaflet, Recharts, and the local assistant are open-source or locally executed dependencies. The simulator creates its own telemetry, so no IoT hardware, SIM card, GPS subscription, commercial map key, or paid LLM is required.

The current map uses OpenStreetMap's public raster tile service. It is suitable for a modest, interactive final-year demonstration when its attribution and usage policy are followed. It requires internet access, is best-effort, has no uptime guarantee, and must not be bulk downloaded. The application retains route and vehicle overlays and displays a notice if tiles fail.

## Optional costs

| Item | Needed for the project demo? | When it can cost money |
|---|---:|---|
| Local frontend, backend, SQLite and AI | No cost | Electricity and the developer's existing computer only |
| GitHub repository | No cost | Optional paid organization/team features |
| Frontend hosting | No cost for an eligible personal/non-commercial free tier | Commercial use, higher traffic, team controls or extra compute |
| FastAPI hosting | No cost on a limited free service | Always-on compute, faster cold starts, more memory or traffic |
| Managed PostgreSQL | Not required | Persistent production database, backups, higher storage or connections |
| Domain name | Not required | A custom public domain usually has an annual registrar fee |
| HTTPS certificate | Usually no cost | Most hosts provide Let's Encrypt or managed TLS; specialist certificates are optional |
| Production map tiles/routing | Not required for the demo | SLA-backed tiles, geocoding, traffic, road routing, offline maps or heavy usage |
| Email/SMS/WhatsApp alerts | Not required | Provider messages after any free allowance |
| External LLM | Not required | Token/API usage if a cloud model is plugged into the local assistant interface |
| Real devices and connectivity | Not required | Sensors, gateways, GPS hardware, IoT platform and cellular data in a real deployment |

## Recommended free presentation setup

Run the frontend, backend, simulator, SQLite database and ML models on the presentation laptop. Keep internet access available only for OpenStreetMap tiles. This avoids hosting sleep delays, cloud quotas and database expiry. For a public portfolio deployment, use an eligible frontend free tier and a limited backend free tier, while retaining SQLite only for an ephemeral demonstration or moving to a free managed Postgres tier with its retention limits understood.

Current policy references:

- [OpenStreetMap tile usage policy](https://operations.osmfoundation.org/policies/tiles/)
- [Vercel Hobby plan](https://vercel.com/docs/plans/hobby)
- [Render free services](https://render.com/docs/free)

