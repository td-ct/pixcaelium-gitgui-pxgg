# Architektur

## Überblick

```
┌──────────────┐   HTTP/JSON (/api/*)   ┌──────────────────────────────┐
│  gui/        │ ◄────────────────────► │  server.py  (stdlib only)    │
│  index.html  │   statische Dateien    │  └─ api/http_api.py  (Routes) │
│  app.js      │                        │     └─ api/workflows.py      │
│  style.css   │                        │     └─ api/commands.py       │
│  i18n/       │                        │  Backends (austauschbar):     │
│  catalog/    │                        │   ├─ api/local_backend.py    │
└──────────────┘                        │   │   subprocess git        │
                                        │   └─ api/termux_backend.py   │
Android-App:                            │       RUN_COMMAND via `am`   │
WebView(gui/) ──JavascriptInterface──►  ├──────────────────────────────┤
  ApiRouter ──► Backend (Kotlin)        │  State: ~/.gitgui/           │
   ├─ TermuxBackend (RUN_COMMAND)      │   ├─ repos.json              │
   └─ HttpBackend (→ server.py)        │   └─ credentials.store       │
                                        └──────────────────────────────┘
```

„Irgendwo laufen nur Texte hin und her“: Kern ist `POST /api/exec {repo, args}` →
`{exit_code, stdout, stderr}`. Alles andere (Completion, Man-Pages, Workflows) baut darauf auf.

## Dateitrennung

- `gui/` — die allgemeine GUI (vanilla JS, kein Build-Step, läuft im Browser, in Colab und in der Android-WebView).
- `api/` — das allgemeine API-Interface (Python, stdlib only) inkl. Termux-Transport (`api/termux_backend.py`).
- `android/` — native App: gleiche GUI als Asset + Kotlin-`Backend`-Implementierungen (`TermuxBackend` via RUN_COMMAND-Intent, `HttpBackend` für Remote-Server).
- `colab/` — Notebook für die Web-/Colab-Variante.
- `tests/` — End-to-End-Tests gegen den laufenden Server (Sandbox-/Desktop-tauglich).

## Backend-Interface (Python)

```python
class Backend:
    def run(repo, args, timeout) -> ExecResult      # git ausführen
    def complete(repo, words, cword) -> {...}        # TAB-Completion (COMPREPLY + Fallback)
    def man(cmd, cwd) -> {...}                       # Man-Page on the fly
    def list_dirs(path) -> {...}                     # Verzeichniswahl
```

Dasselbe Interface existiert in Kotlin (`android/.../backend/Backend.kt`).

## Completion (die glass/glatt-Frage)

Interaktives TAB fügt nur das gemeinsame Präfix ein (`gla`), die Kandidatenliste liegt aber
vollständig in `COMPREPLY`. Trick: bash non-interaktiv mit gesetzten Completion-Variablen fahren:

```bash
source <git-completion.bash>
COMP_WORDS=(git checkout gla); COMP_CWORD=2; COMP_LINE="git checkout gla"; COMP_POINT=16
words=("${COMP_WORDS[@]}"); cword=$COMP_CWORD; cur="${words[cword]}"; prev="${words[cword-1]}"
__git_main
printf '%s\0' "${COMPREPLY[@]}"   # -> glass, glatt
```

Die GUI zeigt daraus ein Dropdown mit **allen** Kandidaten; TAB übernimmt gemeinsames Präfix
bzw. bei eindeutigem Kandidaten den vollen Namen. Ohne `bash-completion` (z. B. nacktes Termux)
fällt `api/completion.py` auf Heuristiken zurück (Refs via `for-each-ref`, Remotes, Dateien,
Optionen aus `git <cmd> -h`, Unterbefehle aus `git help -a`).

## Man-Pages on the fly

`GET /api/man?cmd=checkout` → `git help checkout` mit `PAGER=cat MANPAGER=cat MANWIDTH=100`,
Overstrike (`X\bX`, `_\bX`) und ANSI-Codes werden entfernt. Fallback-Kette, falls `man`/Manpages
fehlen (z. B. nacktes Termux): `git <cmd> -h`. Kurzinfos kommen zusätzlich live aus `git help -a`.

## Credentials

`credentials.store` im `git-credential-store`-Format (`https://user:pass@host`). Sobald Einträge
existieren, hängt jedes git-Kommando `-c credential.helper= -c credential.helper=store --file=…`
an — ohne globale Config zu verändern. Funktioniert identisch lokal und in Termux.

## Sicherheit

- Default-Bindung `127.0.0.1`; non-loopback nur mit `--token` (Bearer oder `?token=`), sonst verweigert der Server den Start.
- API-Limits: Body ≤ 2 MB, args ≤ 200, Output getrimmt auf 512 KB.
- Token-Prüfung vor jedem Request (`api/http_api.py`).

## i18n

`gui/i18n/<lang>.json`. git-Befehle bleiben immer im Original; nur UI, Kurzinfos (`cmd.*`),
Workflow-Texte (`wf.*`), Fehlertitel/-details (`err.*`) und Vorschlags-Buttons (`sugg.*`)
sind übersetzt (Tooltips/Infos). Neue Sprache = neue JSON-Datei; `GET /api/meta` listet verfügbare Sprachen.
