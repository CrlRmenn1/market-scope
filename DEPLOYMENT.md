# Deployment Guide

## Backend on Render

1. Create a new Render Web Service from this repo.
2. Set the root directory to `marketscope-backend`.
3. Use these settings:
   - Build command: `pip install -r requirements.txt`
   - Start command: `python main.py`
4. Add environment variables:
   - `DATABASE_URL` = your Render Postgres connection string
   - `DB_SSLMODE` = `require`
   - `MARKETSCOPE_HOST` = `0.0.0.0`
5. Deploy the service.

## Frontend on Vercel

1. Create a new Vercel project from the same repo.
2. Set the root directory to `marketscope-frontend`.
3. Add an environment variable:
   - `VITE_API_BASE_URL` = your Render backend URL
4. Deploy the frontend.

## Local Development

- Backend: run `python main.py` inside `marketscope-backend`
- Frontend: run `npm run dev` inside `marketscope-frontend`

## Notes

- The frontend now reads its API base URL from `VITE_API_BASE_URL` and falls back to `http://localhost:8000` locally.
- The backend now reads database settings from `DATABASE_URL` or the `DB_*` environment variables.
