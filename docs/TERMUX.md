# Termux-Schnittstelle (RUN_COMMAND)

Offizielle Doku: [termux/termux-app Wiki — RUN_COMMAND Intent](https://github.com/termux/termux-app/wiki/RUN_COMMAND-Intent)

## Betriebsmodus: Muss Termux laufen/sichtbar sein?

**Nein — die App arbeitet im Hintergrund-Modus** (`RUN_COMMAND_BACKGROUND = true`): es wird kein Terminal-Fenster geöffnet, der Befehl läuft als Background-Task im Termux-Service. Termux muss dafür nicht sichtbar sein, aber der Termux-Service muss starten dürfen. Konkret:

- Termux mindestens **einmal manuell geöffnet** haben (damit der Service/Prozess starten darf; ab Android 10 blockiert das System sonst Background-Service-Starts — „app is in background“).
- Permission **„Run commands in Termux environment"** für gitgui freigegeben (Systemeinstellungen → Apps → gitgui → Berechtigungen).
- `allow-external-apps = true` in `~/.termux/termux.properties`.
- **Akku-Optimierung für Termux abschalten** (sonst killt Android den Service).
- Nur für *Foreground*-Sessions (nicht genutzt von gitgui): „Draw Over Apps" für Termux erlauben.
- Repos auf `/storage/emulated/0`: Termux braucht Storage-/„Files and media"-Zugriff.

Der Preflight-Check der App (`GET /api/preflight` bzw. „System check" in der GUI) prüft genau das: Verbindung via RUN_COMMAND (Ping), git, bash, bash-completion, man, `allow-external-apps` — und bietet an, fehlende Pakete direkt per `pkg install` in Termux zu installieren.

## Setup (einmalig)

1. Dritt-App deklariert `<uses-permission android:name="com.termux.permission.RUN_COMMAND"/>`
   und `<queries><package android:name="com.termux"/></queries>` (Package Visibility ab targetSdk 30).
2. Nutzer gibt die Permission frei: Android-Einstellungen → Apps → App → Berechtigungen →
   „Run commands in Termux environment“.
3. In Termux: `allow-external-apps = true` in `~/.termux/termux.properties`.
4. `pkg install git` (+ optional `bash-completion` für volle Completion).
5. Storage-Berechtigung für Termux bei Repos auf `/storage/emulated/0`; Akku-Optimierung aus.

## Intent-Protokoll (nur Texte hin und her)

Component `com.termux/com.termux.app.RunCommandService`, Action `com.termux.RUN_COMMAND`:

| Extra | Typ | Bedeutung |
|---|---|---|
| `com.termux.RUN_COMMAND_PATH` | String | absolute Pfad, z. B. `$PREFIX/bin/git` (`$PREFIX/` und `~/` werden expandiert) |
| `com.termux.RUN_COMMAND_ARGUMENTS` | String[] | Argumente; bei `am --esa` komma-getrennt, Komma als `‚` (U+201A) |
| `com.termux.RUN_COMMAND_WORKDIR` | String | Arbeitsverzeichnis (default `~/`) |
| `com.termux.RUN_COMMAND_BACKGROUND` | boolean | `true` = ohne Terminal-Session |
| `com.termux.RUN_COMMAND_STDIN` | String | stdin (ab 0.109) |
| `com.termux.RUN_COMMAND_PENDING_INTENT` | Parcelable | Ergebnis kommt als Bundle `com.termux.service.PLUGIN_RESULT_BUNDLE` mit Keys `…_STDOUT`, `…_STDERR`, `…_EXIT_CODE`, `…_ERR`, `…_ERRMSG` (ab 0.109; >100 KB werden truncatet) |
| `com.termux.RUN_COMMAND_RESULT_DIRECTORY` | String | Ergebnis-Dateien `stdout`, `stderr`, `exit_code` (ab 0.115) — für `am startservice` ohne PendingIntent |

Java (aus der Doku):

```java
Intent intent = new Intent();
intent.setClassName("com.termux", "com.termux.app.RunCommandService");
intent.setAction("com.termux.RUN_COMMAND");
intent.putExtra("com.termux.RUN_COMMAND_PATH", "/data/data/com.termux/files/usr/bin/git");
intent.putExtra("com.termux.RUN_COMMAND_ARGUMENTS", new String[]{"status", "--porcelain"});
intent.putExtra("com.termux.RUN_COMMAND_WORKDIR", "/sdcard/repos/mein-repo");
intent.putExtra("com.termux.RUN_COMMAND_BACKGROUND", true);
intent.putExtra("com.termux.RUN_COMMAND_PENDING_INTENT", pendingIntent);
startService(intent);
```

`am startservice` (z. B. aus adb shell — das nutzt `api/termux_backend.py`):

```sh
am startservice --user 0 -n com.termux/com.termux.app.RunCommandService \
  -a com.termux.RUN_COMMAND \
  --es com.termux.RUN_COMMAND_PATH '/data/data/com.termux/files/usr/bin/git' \
  --esa com.termux.RUN_COMMAND_ARGUMENTS 'status,--porcelain' \
  --es com.termux.RUN_COMMAND_WORKDIR '/sdcard/repos/mein-repo' \
  --ez com.termux.RUN_COMMAND_BACKGROUND true \
  --es com.termux.RUN_COMMAND_RESULT_DIRECTORY /sdcard/.gitgui/run/123
```

## Umsetzung in diesem Projekt

- `api/termux_backend.py` — Server-seitiger Transport via `am` + `EXTRA_RESULT_DIRECTORY` (nutzbar, wenn der Server z. B. auf dem Desktop läuft und per adb in Termux ausführen will). Start: `python3 server.py --backend termux`.
- `android/.../backend/TermuxBackend.kt` — nativer Transport via PendingIntent-Bundle.
- Direkt in Termux (Python in Termux installiert) reicht `python3 server.py` mit `--backend local` —
  dann ist der RUN_COMMAND-Intent gar nicht nötig.
