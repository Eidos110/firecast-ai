#!/bin/bash
set -o errexit
set -o nounset
set -o pipefail

if ! command -v node >/dev/null 2>&1; then
  apt-get update >/dev/null 2>&1 || true
  apt-get install -y --no-install-recommends curl gnupg >/dev/null 2>&1 || true
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >/dev/null 2>&1 || true
  apt-get install -y --no-install-recommends nodejs >/dev/null 2>&1 || true
fi

cd frontend_react
npm install
npm run build
cd ..

pip install --upgrade pip
pip install -r requirements.txt -r requirements-frontend.txt