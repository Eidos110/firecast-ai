# Security Policy — FireCast

> Catatan keamanan & rotasi secret untuk engineer (manusia & agen).

## 1. Secret yang harus di-rotasi (audit 2026-07-24)

| Secret | Lokasi (working tree) | Status |
|--------|----------------------|--------|
| `OPENWEATHER_API_KEY` plaintext | `.env` (di-gitignore, **tidak** pernah masuk history) | ROTASI di dashboard OpenWeatherMap lalu update `.env` & secret manager deploy |
| `API_SECRET_KEY` placeholder | `.env` (`your_secure_api_secret_key_here`) | Ganti dengan 64-char acak: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| Service-account GEE email | `frontend/utils/gee_data.py:27-28` | Sudah di-track git. Email service-account tidak sama lewat leak secret, tapi rotate di GCP Console bila ragu |
| Key file GEE | `add_new_model/firecast-001-db06a187f9f4.json` | Di-gitignore (`.gitignore:154`). JANGAN commit. Jika pernah ter-commit, rotate key di GCP |

## 2. Blacklist placeholder (sudah diterapkan di kode)

- `src/auth.py:_PLACEHOLDER_API_KEYS` — server menolak 500 bila `API_SECRET_KEY` kosong/placeholder literal.
- `src/config.py:WeatherAPIConfig._OWM_PLACEHOLDER_KEYS` — `has_openweather_key` False bila key placeholder, sehingga frontend fallback ke demo weather bukan 401/429 upstream.

Tambahkan placeholder baru bila ada pattern default di deployment baru (Render/HF Spaces secret manager).

## 3. CI: detect-secrets hook

`.pre-commit-config.yaml` sudah wired hook `detect-secrets` dengan baseline `.secrets.baseline`. Hook akan menolak commit yang mengandung string yang mirip secret (high-entropy, AWS/GitHub token, dll).

Baseline regenerate:
```powershell
& "E:\C.TSUBASA\miniconda\envs\FIREvCPU\Scripts\detect-secrets.exe" scan src tests main.py start_api.py | Out-File .secrets.baseline -Encoding utf8 -NoNewline
# Strip BOM jika perlu:
$bytes = [System.IO.File]::ReadAllBytes(".secrets.baseline")
if ($bytes[0] -eq 0xEF) { [System.IO.File]::WriteAllBytes(".secrets.baseline", $bytes[3..($bytes.Length-1)]) }
```

CI (`.github/workflows/ci.yml`) menjalankan `detect-secrets` pada setiap PR meskipun pre-commit di-skip (`--no-verify`).

## 4. Filter-repo history — TIDAK DIPERLUKAN

Audit `git log --all -S "REDACTED_OPENWEATHER_KEY"` menunjukkan `OPENWEATHER_API_KEY` real TIDAK pernah masuk history apapun (`.env` selalu di-gitignore sejak commit pertama). Jadi **`git filter-repo` tidak diperlukan**. Jika engineer menemukan kebocoran baru, langkah:

```powershell
# 1. Rotasi key di provider (OpenWeatherMap/GCP) SEBELUM rewrite history.
# 2. Backup repo: git clone --mirror <remote> firecast.bak
# 3. Jalankan filter-repo:
pip install git-filter-repo
git filter-repo --invert-paths --path .env --force
# 4. Force-push (koordinasi dengan tim: semua orang perlu re-clone)
```

## 5. Reporting

Laporkan kerentanan security ke maintainer via private channel (jangan buka public issue langsung) bila terkait:
- Authentication bypass
- Remote code execution via model artifact (.pkl/.pth)
- SSRF via parameter URL endpoint

Diberitahukan 90 hari untuk disclosure coordinate.
