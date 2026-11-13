# gitgui für Android

Native Android-App (Kotlin, WebView): dieselbe GUI aus `../gui`, aber das API läuft direkt in der App.

Backends (wählbar über Intent-Extras `backend=http`, `server=…`, `token=…`):

- `TermuxBackend` (Default): führt git über Termux' `RUN_COMMAND`-Intent aus
  (`com.termux.app.RunCommandService`, Action `com.termux.RUN_COMMAND`, Ergebnis über PendingIntent-Bundle).
- `HttpBackend`: spricht einen entfernten gitgui-Server an (z. B. Colab oder Desktop) — damit ist die App auch Fernsteuerung für einen Server.

Voraussetzungen für Termux-Modus:

1. Termux installiert (F-Droid/GitHub, gleiche Signatur wie die Plugins).
2. In der App: Permission `com.termux.permission.RUN_COMMAND` freigeben
   (Android-Einstellungen → Apps → gitgui → Berechtigungen → „Run commands in Termux environment“).
3. In Termux: `allow-external-apps = true` in `~/.termux/termux.properties` setzen.
4. `pkg install git` (und optional `pkg install bash-completion` für exakte TAB-Completion;
   ohne fällt das Backend auf Heuristiken zurück).
5. Storage-Zugriff für Termux, falls Repos auf `/storage/emulated/0` liegen; Akku-Optimierung für Termux abschalten.

GUI in die App kopieren (nach Änderungen in `../gui`):

```sh
./sync-gui.sh
```

## APK / AAB bauen

Lokal (Android Studio oder CLI mit installiertem SDK):

```sh
cd android
gradle wrapper --gradle-version 8.10   # nur beim ersten Mal
./gradlew :app:assembleDebug           # APK: app/build/outputs/apk/debug/app-debug.apk
./gradlew :app:bundleRelease           # AAB: app/build/outputs/bundle/release/app-release.aab (unsigned)
```

Signiertes Release-AAB über Env-Variablen:

```sh
GITGUI_KEYSTORE=/pfad/key.jks GITGUI_KEYSTORE_PASSWORD=… GITGUI_KEY_ALIAS=… GITGUI_KEY_PASSWORD=… \
  ./gradlew :app:bundleRelease
```

Per GitHub Actions (`.github/workflows/android.yml`) entstehen bei jedem Push automatisch
`app-debug.apk` und `app-release-unsigned.aab` als Workflow-Artefakte.
