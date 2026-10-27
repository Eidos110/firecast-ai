# Security Policy — FireCast

This document defines how security vulnerabilities are handled in this
repository and records the current status of secrets management.

## 1. Supported versions

Only the latest `master` branch receives security fixes. There are no
backported release branches.

## 2. Reporting a vulnerability

**Do not open a public issue for a suspected vulnerability.**

Report privately to the maintainer through a private channel (GitHub security
advisory or direct contact). Please include:

- A description of the issue and its impact
- Reproduction steps or a proof of concept
- The affected endpoint, file or commit range (if known)

Areas of particular interest:

- Authentication bypass on `X-API-Key`-protected routes
- Remote code execution via model artifacts (`.pkl` / `.pth`)
- SSRF via URL-taking parameters
- Path traversal in the SPA static fallback (`src/geo_api_spa.py`)

We will acknowledge reports within 7 days and coordinate a disclosure window
of up to **90 days**.

## 3. Secrets management

### Rules

- `.env` and `secrets/` are gitignored and excluded from Docker builds
  (`.dockerignore`).
- Service-account key files (`*.json` credentials) must never be committed.
  If one ever is, rotate the key at the provider immediately.
- Deployed environments receive secrets through the platform secret manager
  (e.g. HF Spaces encrypted secrets) — never through repository files.

### Placeholder rejection (enforced in code)

- `src/auth.py` → `_PLACEHOLDER_API_KEYS`: the server rejects an empty or
  placeholder `API_SECRET_KEY` instead of serving protected routes.
- `src/config.py` → `WeatherAPIConfig._OWM_PLACEHOLDER_KEYS`: a placeholder
  OpenWeatherMap key is treated as "no key" so callers fall back gracefully
  instead of receiving upstream 401/429 errors.

Add new placeholder patterns whenever a new deployment template introduces a
default value.

## 4. Secret scanning in CI

`.github/workflows/ci.yml` runs [`detect-secrets`](https://github.com/Yelp/detect-secrets)
against the tree on every push and pull request, using the baseline in
`.secrets.baseline`. Commits containing credential-like strings
(high-entropy tokens, provider key formats) are rejected — including commits
made with `--no-verify` that bypass local pre-commit hooks.

To regenerate the baseline:

```bash
detect-secrets scan src tests start_api.py launch_prototype.py \
  > .secrets.baseline
```

## 5. History purge record (2026-10-23)

A real `OPENWEATHER_API_KEY` was found in git history: committed as a
"test key" in `tests/test_config.py` (commit era 2026-07-25) and copied into
this document. GitHub secret-scanning rejected the branch push because of it.

Remediation performed:

1. Created a local backup branch before rewriting.
2. Replaced the literal key with a `REDACTED_OPENWEATHER_KEY` token across
   all commits via `git filter-branch` (the branch had never been pushed, so
   the rewrite was safe).
3. Corrected this document, re-pushed, then removed the backup branch, the
   `filter-branch` backup ref and stale reflog entries so no local ref
   retained the pre-purge lineage.

**Still required (owner action):** rotate the OpenWeatherMap key in the OWM
dashboard. It existed in plaintext locally and must be considered
compromised regardless of the history rewrite.

## 6. If a new secret leaks

1. **Rotate the key at the provider first** — history rewriting does not
   un-leak anything.
2. Back up the repository: `git clone --mirror <remote> firecast.bak`
3. Purge the file or rewrite the string:

   ```bash
   pip install git-filter-repo
   git filter-repo --invert-paths --path .env --force
   ```

4. Force-push only with team coordination — everyone must re-clone.
5. Notify GitHub Support to clear cached views of the secret if the repo is
   public or has forks.
