# gitgui

Eine allgemeine, leichtgewichtige Git-GUI mit **zwei Gesichtern**:

1. **Guided** — typische Abläufe (clone, status, commit, pull, push, Branches, Merge,
   Konflikte, Stash, …) als geführte Workflows inkl. Erkennung typischer Fehler
   (Merge-Konflikt, non-fast-forward, Auth-Fehler, „dubious ownership“ auf Android-Speicher,
   fehlende Identität, divergierte Branches …) mit übersetzten Erklärungen und
   anklickbaren Lösungsvorschlägen.
2. **Alle Befehle (Pro)** — kompletter Funktionsumfang von git, kategorisiert aufgelistet.
   Jeder Befehl: knappe Kurzinfo (übersetzter Tooltip) + Man-Page, die **on the fly** aus Termux
   geholt wird. Felder werden per Vorgaben vorbefüllt, sind aber immer frei eingebbar — mit
   TAB-Completion (Dropdown zeigt alle Kandidaten, z. B. `glass` **und** `glatt` bei `gla`).

Eigenschaften:

- **Verzeichnisse einfach anwählbar** (Repo-Liste + Verzeichnis-Browser), **Zugangsdaten zentral verwaltet**
  (lokaler `credential.store`, wird per `credential.helper` injiziert).
- **Terminal-Drawer** unten: kollabiert nur letzte Zeile, per Tap hochziehbar, klassisch grün auf schwarz;
  loggt jeden ausgeführten Befehl.
- **Sperr-Sanduhr mit Stopp**: während ein Workflow oder Einzelbefehl läuft, ist die App gesperrt (⏳-Overlay),
  laufende Jobs lassen sich per „Stop" killen (`POST /api/stop`, Prozessgruppe via `start_new_session`/`killpg`;
  im Termux-Backend über `exec -a gitgui-job-<id>` + `pkill -f`).
- **System-Check beim Start** (`GET /api/preflight`): prüft Termux-Verbindung (RUN_COMMAND-Ping), git, bash,
  bash-completion, man, `allow-external-apps`; fehlende Pakete können direkt per `pkg install` in Termux
  nachinstalliert werden (`POST /api/preflight/install`).
- **Mehrsprachig** (en/de, erweiterbar): git-Befehle bleiben immer im Original, nur UI/Hilfen/Tooltips werden übersetzt.
- **Backend-unabhängig**: überall laufen nur Texte (JSON) hin und her — lokal (subprocess), Termux
  (`RUN_COMMAND`-Intent), oder remote (HTTP, z. B. Colab). Siehe `docs/ARCHITECTURE.md`.
- **Überall lauffähig**: Linux-Sandbox/Desktop (Python stdlib only), Browser/Web (Colab-Notebook),
  Android (native App, siehe `android/`).
- **Dateitrennung**: `gui/` (allgemeine GUI) und `api/` (allgemeines API-Interface inkl. Termux-Transport).

## Schnellstart (Linux / Sandbox / Desktop / Termux mit Python)

```sh
cd gitgui
python3 server.py                 # http://127.0.0.1:8765
# remote (z. B. Colab): Token Pflicht!
python3 server.py --host 0.0.0.0 --port 8765 --token GEHEIM
```

Dann Browser öffnen: `http://127.0.0.1:8765/` — Repos oben links hinzufügen, loslegen.

Nur Python ≥ 3.8, keine Dependencies. In Termux: `pkg install python git` und dann ebenfalls `python3 server.py`
(im Termux selbst ist das `local`-Backend identisch mit „git in Termux“).

## Colab / Web

`colab/gitgui.ipynb` öffnen, `REPO_URL`/`TOKEN` setzen, Zellen ausführen → GUI im IFrame.

## Android (APK/AAB)

Projekt in `android/` (Kotlin + WebView). GUI wird per `android/sync-gui.sh` in die Assets kopiert.
Die App nutzt Termux' `RUN_COMMAND`-Intent als Backend (`TermuxBackend.kt`) oder einen Remote-Server
(`HttpBackend.kt`). Build: `./gradlew :app:assembleDebug` (APK) / `:app:bundleRelease` (AAB) —
Details und Voraussetzungen (Permission, `allow-external-apps`, …) in `android/README.md` und `docs/TERMUX.md`.
Per GitHub Actions (`.github/workflows/android.yml`) werden APK + AAB automatisch als Artefakte gebaut.

## Tests

```sh
tests/run.sh        # 19 End-to-End-Tests gegen den laufenden Server (echte git-Repos, inkl. glass/glatt-Completion und echtem Merge-Konflikt)
```

## API (Auszug)

| Endpoint | Beschreibung |
|---|---|
| `POST /api/exec {repo, args, timeout}` | git ausführen → `{exit_code, stdout, stderr}` |
| `POST /api/complete {repo, words, cword}` | Completion-Kandidaten + gemeinsames Präfix |
| `GET /api/man?cmd=…&repo=…` | Man-Page on the fly (overstrike-bereinigt) |
| `GET /api/help?cmd=…` | `git <cmd> -h` |
| `POST /api/commands {repo}` | kategorisierter Befehlskatalog + Live-Beschreibungen aus `git help -a` |
| `GET /api/workflows` / `POST /api/workflow/run {repo, id, params}` | geführte Workflows inkl. Fehlererkennung |
| `GET /api/repos`, `POST /api/repos/add\|remove` | Repo-Verwaltung |
| `POST /api/fs/list {path}` | Verzeichnis-Browser |
| `GET/POST /api/credentials…` | Zugangsdaten (credential.store-Format) |
| `GET /api/i18n/<lang>`, `GET /api/meta` | Sprachen, Backend-Info |

## Layout

```
gitgui/
  server.py            # Einstiegspunkt (HTTP-Server, stdlib only)
  api/                 # API-Interface: Backends, Completion, Man, Workflows, Credentials, Repos, Error-Patterns
    local_backend.py   # git via subprocess (Sandbox/Desktop/Termux-python)
    termux_backend.py  # git via Termux RUN_COMMAND (`am` + result dir)
  gui/                 # allgemeine GUI (index.html, app.js, style.css, i18n/, catalog/)
  android/             # native Android-App (Kotlin, TermuxBackend via Intent, HttpBackend)
  colab/               # Colab-Notebook
  tests/               # End-to-End-Tests
  docs/                # ARCHITECTURE.md, TERMUX.md
```

## CI

Artefakt (APK+AAB) lokal holen: `sh scripts/download-artifact.sh`.
