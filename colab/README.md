# gitgui in Google Colab

`gitgui.ipynb` startet `server.py` in der Colab-Runtime (Port 8765, loopback, mit Token)
und zeigt die GUI per `google.colab.output.serve_kernel_port_as_iframe` im Notebook an.

Ablauf:

1. Notebook öffnen, `REPO_URL` und `TOKEN` in Zelle 2 setzen.
2. Zellen der Reihe nach ausführen.
3. Die GUI erscheint im IFrame (URL enthält `?token=…`).

Die gleiche Session lässt sich von der Android-App fernsteuern (Backend `http`,
Server = Colab-URL, Token = gesetztes Token) — siehe `android/README.md`.

Alternativ lokal/desktop: `python3 server.py` starten und `http://127.0.0.1:8765/` öffnen.
