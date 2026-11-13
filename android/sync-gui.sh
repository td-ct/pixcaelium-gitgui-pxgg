#!/bin/sh
set -e
cd "$(dirname "$0")"
rm -rf app/src/main/assets/gui
mkdir -p app/src/main/assets/gui
cp -r ../gui/index.html ../gui/app.js ../gui/style.css ../gui/i18n ../gui/catalog app/src/main/assets/gui/
echo "gui synced to app/src/main/assets/gui"
