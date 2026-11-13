#!/bin/sh
# download-artifact.sh — laedt das neueste erfolgreiche gitgui-android-Artefakt (APK + AAB)
# von GitHub Actions. Umgeht den "gh run download: path traversal"-Bug via curl.
#
# Voraussetzung: gh eingeloggt (gh auth login) -> Token aus `gh auth token`.
# Nutzung:  sh scripts/download-artifact.sh [ ziel-verzeichnis ]
set -eu

REPO="td-ct/pixcaelium-gitgui-pxgg"
OUT="${1:-.}"

RUN_ID=$(gh api "repos/$REPO/actions/runs?per_page=30" \
  --jq '[.workflow_runs[] | select(.conclusion=="success" and .head_branch=="main")][0].id // empty')
if [ -z "$RUN_ID" ]; then
  RUN_ID=$(gh api "repos/$REPO/actions/runs?per_page=30" \
    --jq '[.workflow_runs[] | select(.conclusion=="success")][0].id')
fi
echo "Run: $RUN_ID"

ART_ID=$(gh api "repos/$REPO/actions/runs/$RUN_ID/artifacts" \
  --jq '.artifacts[] | select(.name=="gitgui-android") | .id')
if [ -z "$ART_ID" ]; then
  echo "kein gitgui-android-Artefakt in Run $RUN_ID" >&2
  exit 1
fi

cd "$OUT"
curl -sL -H "Authorization: Bearer $(gh auth token)" \
     -H "Accept: application/vnd.github+json" \
     -o gitgui-android.zip \
     "https://api.github.com/repos/$REPO/actions/artifacts/$ART_ID/zip"

rm -rf gitgui-android && mkdir gitgui-android
unzip -o gitgui-android.zip -d gitgui-android
echo "entpackt nach $OUT/gitgui-android:"
ls -la gitgui-android
