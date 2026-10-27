# Security Policy

This document describes how to report vulnerabilities in FireCast, which
issues are in scope, and how the maintainers handle disclosure. It also
records the security controls enforced in the repository.

## Supported versions

Only the latest code on the `master` branch receives security fixes. There
are no maintained release branches or tagged distributions.

| Branch | Support |
|---|---|
| `master` | Supported |
| Feature branches and older commits | Not supported |

## Reporting a vulnerability

Please do **not** open a public issue for a suspected vulnerability.

Report it privately through one of the following channels:

1. A GitHub security advisory (Security tab of this repository), or
2. Direct contact with the repository maintainer.

To help us reproduce and assess the report, please include:

- A description of the vulnerability and its likely impact
- Reproduction steps or a proof of concept
- The affected endpoint, file, or commit range, if known

The maintainers acknowledge reports within **7 days** and will keep you
informed while a fix is prepared.

## Scope

The following areas are of particular interest:

- Authentication bypass on routes protected by `X-API-Key`
- Remote code execution through model artifacts (`.pkl`, `.pth`)
- Server-side request forgery through URL-accepting parameters
- Path traversal in the SPA static file fallback (`src/geo_api_spa.py`)
- SQL or command injection through API parameters
- Exposure of secrets or service-account credentials

Abuse-magnitude testing against rate limits and reports from automated
scanners without a demonstrated impact are considered out of scope.

## Disclosure policy

We follow coordinated disclosure. Once a fix is available on `master`, the
reporter is notified and given credit if desired. Public disclosure occurs
at the latest **90 days** after the initial report, even if a fix has not
yet shipped, unless the reporter requests an extension in writing.

## Security controls

The following controls are implemented in this repository and enforced in
CI:

| Control | Where |
|---|---|
| Secrets and credentials are gitignored and excluded from Docker builds | `.gitignore`, `.dockerignore` |
| Empty or placeholder API keys are rejected instead of serving protected routes | `src/auth.py` (`_PLACEHOLDER_API_KEYS`) |
| Placeholder third-party keys are treated as absent so callers degrade gracefully | `src/config.py` (`WeatherAPIConfig._OWM_PLACEHOLDER_KEYS`) |
| Secret scanning on every push and pull request, including commits made with `--no-verify` | `.github/workflows/ci.yml` with the `.secrets.baseline` file |
| Deployed environments receive secrets through the platform secret manager, never as repository files | e.g. Hugging Face Spaces encrypted secrets |

When a new deployment template introduces a default secret value, register
the pattern in the placeholder lists above so it is rejected the same way.

To regenerate the secret-scanning baseline:

```bash
detect-secrets scan src tests start_api.py launch_prototype.py \
  > .secrets.baseline
```

## Handling a leaked secret

If a credential is ever committed, follow this order:

1. Rotate the credential at the provider **first**. Rewriting history does
   not un-leak a value that has already been observed.
2. Back up the repository: `git clone --mirror <remote> firecast.bak`.
3. Purge the secret from history, for example:

   ```bash
   pip install git-filter-repo
   git filter-repo --invert-paths --path .env --force
   ```

4. Force-push only after coordinating with all collaborators, who must
   re-clone afterwards.
5. If the repository is public or forked, contact GitHub Support to clear
   cached views of the secret.

## Incident log

| Date | Incident | Status |
|---|---|---|
| 2026-10-23 | A real OpenWeatherMap API key was found in git history: committed as a "test key" in `tests/test_config.py` (commit era 2026-07-25) and copied into this document. GitHub secret scanning blocked the branch push as a result. | History rewritten with the key replaced by a redaction token; the literal no longer appears in any commit on `master`. **Remaining owner action: rotate the key in the OpenWeatherMap dashboard**, since it existed in plaintext locally and must be treated as compromised. |
