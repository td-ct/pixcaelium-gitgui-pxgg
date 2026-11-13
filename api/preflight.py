import os

from . import completion


def run_preflight(backend, state):
    checks = []

    def add(cid, label_key, ok, detail="", install=None, optional=False):
        checks.append({
            "id": cid, "label_key": label_key, "ok": bool(ok),
            "detail": detail, "install": install, "optional": optional,
        })

    r = backend.raw(["git", "--version"])
    add("git", "pf.git", r.exit_code == 0,
        (r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr).strip() else "",
        install="git" if r.exit_code != 0 else None)

    r = backend.raw(["bash", "-c", "echo ok"])
    add("bash", "pf.bash", r.exit_code == 0 and r.stdout.strip() == "ok",
        "", install="bash" if r.exit_code != 0 else None)

    if backend.name == "termux":
        r = backend.raw(["bash", "-c",
                         "for f in $PREFIX/share/bash-completion/completions/git $PREFIX/share/git-core/git-completion.bash; do [ -f \"$f\" ] && echo \"$f\" && exit 0; done; exit 1"])
        add("completion", "pf.completion", r.exit_code == 0, r.stdout.strip(),
            install="bash-completion" if r.exit_code != 0 else None, optional=True)
    else:
        found = next((p for p in completion._probe_paths() if os.path.exists(p)), "")
        add("completion", "pf.completion", bool(found), found,
            install="bash-completion" if not found else None, optional=True)

    r = backend.raw(["bash", "-c", "command -v man || true"])
    add("man", "pf.man", r.stdout.strip() != "", r.stdout.strip(), optional=True)

    if backend.name == "termux":
        r = backend.raw(["echo", "ok"], timeout=20)
        add("termux_connection", "pf.termux_connection", r.exit_code == 0 and r.stdout.strip() == "ok",
            (r.stderr or "RUN_COMMAND failed").strip()[:200])
        r = backend.raw(["bash", "-c",
                         "grep -Eq '^allow-external-apps[[:space:]]*=[[:space:]]*true' \"$HOME/.termux/termux.properties\" && echo yes || echo no"])
        add("allow_external_apps", "pf.allow_external_apps", r.stdout.strip() == "yes",
            "setze allow-external-apps = true in ~/.termux/termux.properties" if r.stdout.strip() != "yes" else "")
        add("storage", "pf.storage", True,
            "Termux braucht Storage-Zugriff fuer Repos auf /storage/emulated/0; Akku-Optimierung fuer Termux abschalten",
            optional=True)

    return {
        "backend": backend.name,
        "ok": all(c["ok"] for c in checks if not c["optional"]),
        "checks": checks,
    }


def install_packages(backend, packages):
    packages = [str(p) for p in packages if str(p).strip()]
    if not packages:
        return {"ok": False, "output": "no packages given"}
    if backend.name == "termux":
        r = backend.raw(["pkg", "install", "-y"] + packages, timeout=600)
        return {"ok": r.exit_code == 0, "output": (r.stdout + r.stderr)[-4000:]}
    return {"ok": False, "output": "automatic install only supported for the termux backend; locally use: apt install " + " ".join(packages)}
