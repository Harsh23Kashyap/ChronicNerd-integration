#!/usr/bin/env bash
# Build the static site for S3 + CloudFront. Never bake API keys or credentials into it.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
out=${1:-"$root/dist/site"}
api_url=${API_URL:-/api}
case "$api_url" in
  /api|https://*) ;;
  *) echo 'API_URL must be /api or an https:// URL' >&2; exit 2 ;;
esac
if [[ "$api_url" =~ [\"\'\\[:space:]] || "$api_url" == *"<"* || "$api_url" == *">"* || "$api_url" == *"&"* ]]; then
  echo 'API_URL has unsafe characters' >&2; exit 2
fi
mkdir -p "$out"
# Copy only deployable assets. Avoid OS metadata and future local dotfiles.
find "$root/dietnerd-website" -maxdepth 1 -type f \( -name '*.html' -o -name '*.css' -o -name '*.js' \) -exec cp {} "$out/" \;
mkdir -p "$out/assets"
find "$root/dietnerd-website/assets" -maxdepth 1 -type f \( -name '*.png' -o -name '*.jpg' -o -name '*.jpeg' -o -name '*.svg' -o -name '*.webp' \) -exec cp {} "$out/assets/" \;
cat > "$out/env.js" <<CONFIG
// Public configuration only; do not add keys or secrets.
window.env = { API_URL: '$api_url' };
CONFIG
printf 'Static site built at %s (API_URL=%s)\n' "$out" "$api_url"
