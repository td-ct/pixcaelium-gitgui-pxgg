from .util import base_env, strip_overstrike, truncate, MAX_OUTPUT


def _git(run, cwd, args, timeout=30):
    return run(cwd, args, timeout)


def man_text(backend, cmd, cwd=None):
    env_note = None
    r = backend.run(cwd, ["help", cmd], timeout=30)
    text = strip_overstrike(r.stdout or "")
    if r.exit_code == 0 and text.strip():
        out, tr = truncate(text)
        return {"cmd": cmd, "source": "man", "text": out, "truncated": tr}
    r = backend.run(cwd, [cmd, "-h"], timeout=30)
    text = strip_overstrike((r.stdout or "") + (r.stderr or ""))
    if text.strip():
        out, tr = truncate(text)
        return {"cmd": cmd, "source": "usage", "text": out, "truncated": tr}
    return {"cmd": cmd, "source": "none", "text": "", "error": "no help available", "truncated": False}


def short_help(backend, cmd, cwd=None):
    r = backend.run(cwd, [cmd, "-h"], timeout=30)
    return strip_overstrike((r.stdout or "") + (r.stderr or ""))[:MAX_OUTPUT]


def parse_help_a(backend, cwd=None):
    r = backend.run(cwd, ["help", "-a"], timeout=30)
    categories = []
    current = None
    for line in (r.stdout or "").splitlines():
        if not line.strip():
            continue
        if not line.startswith(" ") and line.strip().endswith("Commands"):
            current = {"name": line.strip(), "commands": []}
            categories.append(current)
        elif line.startswith("   ") and current is not None:
            parts = line.strip().split(None, 1)
            if parts:
                current["commands"].append(
                    {"name": parts[0], "desc": parts[1] if len(parts) > 1 else ""}
                )
    return categories
