# Deployment Guide

This guide outlines the environment configuration and deployment steps for Provenance.

---

## 1. Backend Deployment (Render / Docker)

- **Runtime / Environment**: Docker
- **Root Directory**: `backend`
- **Docker Command**: Managed by `backend/Dockerfile` (`alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips="*"`)
- **Health Check Path**: `/health`

### Backend Environment Variables

| Variable | Description | Example / Required |
|---|---|---|
| `ENV` | Environment identifier | `production` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:password@host:5432/dbname?sslmode=require` |
| `GITHUB_CLIENT_ID` | GitHub OAuth App Client ID | `your-github-client-id` |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth App Client Secret | `your-github-client-secret` |
| `GITHUB_REDIRECT_URI` | Full OAuth callback URL pointing to frontend | `https://your-frontend.vercel.app/api/auth/github/callback` |
| `SESSION_SECRET` | Random 32+ character key for session JWTs | `generate-random-32-plus-characters-string` |
| `PASSPORT_SIGNING_SECRET` | Random 32+ character key for passport HMAC seals | `generate-random-32-plus-characters-string` |
| `FRONTEND_URL` | Public frontend URL | `https://your-frontend.vercel.app` |
| `PUBLIC_BASE_URL` | Public base URL for shareable passport verification | `https://your-frontend.vercel.app` |
| `REPO_STORAGE_PATH` | Writable directory for bare git clones | `/app/data/repos` |
| `ADMIN_GITHUB_USERNAMES` | Comma-separated list of admin GitHub handles | `octocat,facultyadmin` |
| `ANTHROPIC_API_KEY` | *(Optional)* Anthropic API key for LLM summaries | `sk-ant-...` |
| `GITHUB_API_TOKEN` | *(Optional)* GitHub personal access token for higher API limits | `ghp_...` |

---

## 2. Frontend Deployment (Vercel)

- **Framework Preset**: Next.js
- **Root Directory**: `frontend`
- **Build Command**: `next build`
- **Output Directory**: `.next`

### Frontend Environment Variables

| Variable | Description | Example / Required |
|---|---|---|
| `BACKEND_URL` | Full URL of deployed backend on Render | `https://your-backend.onrender.com` |

---

## 3. Manual Steps Required

1. **GitHub OAuth App**: Set the Authorization callback URL in your GitHub Developer Settings to `https://your-frontend.vercel.app/api/auth/github/callback`.
2. **Secrets Generation**: Generate two distinct 32+ character random strings for `SESSION_SECRET` and `PASSPORT_SIGNING_SECRET`.
3. **Database**: Provision a managed PostgreSQL instance and supply its connection URL in `DATABASE_URL`.

