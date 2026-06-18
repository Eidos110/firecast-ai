# FireCast Railway Deployment Guide

**Project:** FireCast - Fire Risk Prediction System  
**Target Platform:** Railway.app  
**Deployment Type:** Multi-service Docker deployment (Streamlit frontend + FastAPI backend)  
**Maintainer:** Kilo (Senior Software Engineer)  
**Date:** 2026-05-14

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Configuration](#configuration)
3. [Deployment Steps](#deployment-steps)
4. [Post-Deployment](#post-deployment)
5. [Troubleshooting](#troubleshooting)
6. [Alternative Deployment Options](#alternative-deployment-options)

---

## Prerequisites

### Required Accounts
- Railway account (sign up at [railway.app](https://railway.app))
- Verified email and payment method (required after trial period)

### Local Tools
- Docker Desktop (running)
- Railway CLI: `npm i -g @railway/cli`
- Git (for version control)

### System Requirements
- Windows PowerShell (or CMD) with execution policy allowing scripts (or use `railway.cmd`)
- At least 4GB free RAM for local Docker builds (optional)

---

## Configuration

### 1. Environment Variables

**Critical:** Create your `.env` file from the template:

```bash
copy .env.production .env
```

Edit `.env` and set:

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `OPENWEATHER_API_KEY` | Yes (recommended) | OpenWeatherMap API key (get free/paid at openweathermap.org) | `abc123...` |
| `API_SECRET_KEY` | **Yes** | Random secret for API authentication (min 64 chars) | Generate with: `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `ENABLE_DEMO_MODE` | No | Set `false` for production (default), `true` for demo fallback | `false` |

**Note:** Without `OPENWEATHER_API_KEY`, weather data will fall back to BMKG (Indonesian) or demo synthetic data, which may affect prediction accuracy.

### 2. Dockerfile Updates

The Dockerfile has been updated to:
- Build React frontend automatically using a dedicated `react-builder` stage
- Use CPU-optimized PyTorch wheels (automatic conversion from CUDA to CPU during build)
- Include necessary system dependencies for geospatial libraries

No manual changes needed.

### 3. Railway Configuration (`railway.toml`)

Defines two services:
- `firecast-frontend` → Streamlit (port 8501)
- `firecast-api` → FastAPI (port 8000)

Routes automatically configured via Railway's internal routing:
- Frontend: `https://<project>.railway.app/`
- API: `https://<project>.railway.app/api/`

---

## Deployment Steps

### Step 1: Login to Railway

```bash
railway login
```

This opens a browser for OAuth. Complete the login.

### Step 2: Initialize Project (if starting fresh)

**Note:** Your Railway trial appears to have expired. You must upgrade to a paid plan to create new projects or add services. If you have an existing project with available capacity, you can add services to it.

If you have an active paid account or free credits:

```bash
# Create new project and link to current directory
railway init --name firecast --workspace "Your Workspace Name"
```

This creates a new Railway project and links it to this directory.

If you already have a project and want to add FireCast as additional services:

```bash
# Link this directory to existing project
railway link --project <PROJECT_ID>
```

### Step 3: Set Environment Variables (Important!)

**Option A: Dashboard (Recommended)**
1. Go to https://railway.app/dashboard
2. Open your project
3. For each service (`firecast-frontend`, `firecast-api`), go to **Variables** tab
4. Add the following variables:
   - `OPENWEATHER_API_KEY` = your key
   - `API_SECRET_KEY` = your random secret
   - `ENABLE_DEMO_MODE` = `false` (or `true` for testing)
   - Others optional: `LOG_LEVEL=WARNING`, `APP_ENV=production`

**Option B: CLI**
```bash
# Set for frontend
railway variables set --service firecast-frontend OPENWEATHER_API_KEY=your_key API_SECRET_KEY=your_secret

# Set for API
railway variables set --service firecast-api OPENWEATHER_API_KEY=your_key API_SECRET_KEY=your_secret
```

### Step 4: Deploy

**First deployment (creates services):**
```bash
# Deploy frontend
railway up --service firecast-frontend --detach

# Deploy API (in another terminal or after frontend completes)
railway up --service firecast-api --detach
```

**Subsequent deployments (updates):**
```bash
railway up --service firecast-frontend
railway up --service firecast-api
```

The `--detach` flag returns immediately; omit to stream logs.

### Step 5: Verify Deployment

Check status:
```bash
railway status
```

View logs:
```bash
railway logs --service firecast-frontend --tail 100
railway logs --service firecast-api --tail 100
```

Check deployment URL:
```bash
railway open
```

Visit the frontend URL; API docs at `<url>/docs`.

---

## Post-Deployment

### Configure Custom Domain (Optional)
```bash
railway domain add --service firecast-frontend yourdomain.com
```

### Enable HTTPS
Railway automatically provides SSL via Let's Encrypt.

### Set Up Monitoring
- Enable health checks in Railway dashboard (already configured)
- Add uptime monitoring (UptimeRobot, Better Uptime) pointing to `/` and `/health`

### Backup Strategy
Model files are part of the Docker image. For persistent updates, consider:
- Storing models in object storage (S3, GCS) and downloading at container startup
- Using Railway volumes (ephemeral) or external storage

---

## Troubleshooting

### "Your trial has expired"
**Cause:** Railway trial period ended; creating new services requires a paid plan.  
**Solution:** Upgrade to a paid plan on Railway billing page, or deploy to an existing project with available service slots.

### "Service not found" when running `railway up --service <name>`
**Cause:** Service hasn't been created yet.  
**Solution:** Run `railway add --service <name>` interactively, or create via dashboard first.

### Docker build fails on React step
**Cause:** Node.js build errors or missing dependencies.  
**Solution:** Check `frontend_react/` for errors, run `npm install && npm run build` locally to debug.

### PyTorch installation fails (`No matching distribution found for torch==1.10.2+cu102`)
**Cause:** CUDA variant on CPU-only environment.  
**Solution:** Dockerfile includes automatic replacement to `+cpu`. If still failing, ensure base stage runs the `sed` replacement (line ~38-44).

### Health checks failing
**Cause:** Service crashed or port mismatch.  
**Solution:** Check logs with `railway logs`. Ensure `internal_port` in `railway.toml` matches the port your app listens on (8501 for frontend, 8000 for API). Also verify environment variables.

### Frontend shows "Connection error" when calling API
**Cause:** CORS misconfiguration or API not reachable.  
**Solution:** Ensure `ENABLE_CORS=true` in API env. Railway's internal routing should allow `/api` path to the API service. Verify that the frontend's API_BASE_URL is automatically set by Railway via internal DNS (frontend can call `http://firecast-api:8000` within Railway network). In our setup, Railway's router directs `/api` to the API service automatically.

---

## Alternative Deployment Options

If Railway is not suitable, see the comprehensive planning document (`C:\Users\ASUS\.local\share\kilo\plans\1778605533009-brave-harbor.md`) for alternatives:

- **Option 2:** Docker Compose on a single VM (AWS EC2, DigitalOcean)
- **Option 3:** Kubernetes (GKE/EKS) for enterprise scale
- **Option 5:** Hybrid (Cloud Run + Streamlit Cloud)
- **Option 6:** Systemd services on a VM (no Docker)

---

## Quick Reference Commands

```bash
# Login
railway login

# Check status
railway status

# Deploy frontend
railway up --service firecast-frontend --detach

# Deploy API
railway up --service firecast-api --detach

# View logs
railway logs --service firecast-frontend --tail 50
railway logs --service firecast-api --tail 50

# Set environment variable
railway variables set --service firecast-frontend KEY=value

# Restart service (no rebuild)
railway restart --service firecast-frontend

# Open dashboard
railway open

# Get deployment URL
railway logistics:request-url --service firecast-frontend
```

---

## Files Modified/Created

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage build with React auto-build; CPU PyTorch conversion |
| `railway.toml` | Railway service definitions, resources, health checks |
| `.env.production` | Production environment template (DO NOT commit) |
| `deploy.ps1` | PowerShell deployment automation script |
| `.gitignore` | Updated to ignore `frontend_react/build/` and `.env.production` |

---

## Next Steps After Successful Deployment

1. **Secure API Secret:** Rotate `API_SECRET_KEY` periodically via Railway variables.
2. **Add Custom Domain:** Point your domain to Railway and configure in dashboard.
3. **Set Up Alerts:** Connect UptimeRobot or similar to health endpoints.
4. **Enable CI/CD:** Push to GitHub and link repository in Railway for automatic deployments on push (optional).
5. **Scale Resources:** Adjust CPU/memory in Railway dashboard if needed.
6. **Add Database:** If user accounts/prediction history required, add PostgreSQL addon and integrate.

---

## Support

- Railway Docs: https://docs.railway.app
- FireCast Issues: Report at project repository
- Kilo Assistant: Use `/help` for assistance

---

**Last Updated:** 2026-05-14  
**Deployment Status:** Ready (blocked by Railway trial expiration; upgrade required to create services)
