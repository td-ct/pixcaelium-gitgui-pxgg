import os
import shlex
import subprocess

from .util import base_env

MAX_CANDIDATES = 200

REF_PREV = {
    "checkout", "switch", "merge", "rebase", "reset", "diff", "log", "show",
    "branch", "cherry-pick", "tag", "push", "pull", "fetch", "revert", "blame",
    "describe", "rev-parse", "rm", "restore", "mv",
}
BRANCH_DELETE_OPTS = {"-d", "-D", "-m", "-M", "--delete", "--move", "--copy", "-c", "-C"}


def _git_prefix():
    try:
        r = subprocess.run(
            ["git", "--exec-path"], capture_output=True, text=True, timeout=10,
            env=base_env(),
        )
        p = r.stdout.strip()
        for suffix in ("/libexec/git-core", "/lib/git-core", "/usr/lib/git-core"):
            if p.endswith(suffix):
                return p[: -len(suffix)]
    except Exception:
        pass
    return "/usr"


def _probe_paths():
    prefix = _git_prefix()
    return [
        os.path.join(prefix, "share/git-core/git-completion.bash"),
        os.path.join(prefix, "share/bash-completion/completions/git"),
        "/usr/share/bash-completion/completions/git",
        "/usr/share/git-core/git-completion.bash",
        "/usr/local/share/git-core/git-completion.bash",
        "/data/data/com.termux/files/usr/share/bash-completion/completions/git",
        "/data/data/com.termux/files/usr/share/git-core/git-completion.bash",
    ]


def build_completion_script(words, cword):
    arr = " ".join(shlex.quote(w) for w in words)
    line = " ".join(words)
    probes = " ".join(shlex.quote(p) for p in _probe_paths())
    return f"""
shopt -s progcomp 2>/dev/null
COMP_WORDBREAKS=" "
for f in {probes}; do
  if [ -f "$f" ]; then source "$f" 2>/dev/null; break; fi
done
COMP_WORDS=({arr})
COMP_CWORD={cword}
COMP_LINE={shlex.quote(line)}
COMP_POINT=${{#COMP_LINE}}
words=("${{COMP_WORDS[@]}}")
cword=$COMP_CWORD
cur="${{words[cword]}}"
prev="${{words[cword-1]}}"
COMPREPLY=()
if declare -F __git_main >/dev/null 2>&1; then
  __git_main 2>/dev/null
elif declare -F _git >/dev/null 2>&1; then
  _git 2>/dev/null
fi
if [ ${{#COMPREPLY[@]}} -gt 0 ]; then printf '%s\\0' "${{COMPREPLY[@]}}"; fi
"""


def normalize_candidates(raw):
    out = []
    for c in raw.split("\0"):
        if c.endswith(" ") and len(c) > 1:
            c = c[:-1]
        if c:
            out.append(c)
    return out


def bash_complete(repo, words, cword):
    script = build_completion_script(words, cword)
    try:
        r = subprocess.run(
            ["bash", "-c", script], cwd=repo or None, env=base_env(),
            capture_output=True, timeout=15,
        )
        return normalize_candidates(r.stdout.decode("utf-8", "replace"))
    except Exception:
        return []


def _subcommand(words):
    for w in words[1:]:
        if not w.startswith("-"):
            return w
    return ""


def fallback_complete(backend, repo, words, cword):
    words = list(words) + [""] * (cword + 1 - len(words))
    cur = words[cword] if cword < len(words) else ""
    prev = words[cword - 1] if cword > 0 else ""
    sub = _subcommand(words)
    out = []
    if cword <= 1:
        for cat in backend.help_a(repo):
            for c in cat["commands"]:
                if c["name"].startswith(cur):
                    out.append(c["name"])
        return out
    if cur.startswith("-") and sub:
        r = backend.run(repo, [sub, "-h"], timeout=15)
        import re
        for m in re.findall(r"(?<![\w])-{1,2}[A-Za-z][\w-]*", (r.stdout or "") + (r.stderr or "")):
            if m.startswith(cur):
                out.append(m)
        return out
    if prev in REF_PREV or (sub == "branch" and prev in BRANCH_DELETE_OPTS):
        r = backend.run(
            repo,
            ["for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes", "refs/tags"],
            timeout=15,
        )
        refs = [l.strip() for l in r.stdout.splitlines() if l.strip()]
        out = [x for x in refs + ["HEAD"] if x.startswith(cur)]
        return out
    if sub in ("push", "pull", "fetch", "ls-remote") or (sub == "remote" and prev not in ("add", "set-url")):
        r = backend.run(repo, ["remote"], timeout=15)
        out = [l.strip() for l in r.stdout.splitlines() if l.strip().startswith(cur)]
        return out
    base = repo or os.getcwd()
    try:
        for name in sorted(os.listdir(base)):
            if name.startswith(cur):
                full = os.path.join(base, name)
                out.append(name + ("/" if os.path.isdir(full) else ""))
    except OSError:
        pass
    return out


def complete(backend, repo, words, cword):
    words = [str(w) for w in words]
    if not words:
        words = ["git"]
    cword = max(0, min(int(cword), len(words) - 1))
    candidates = bash_complete(repo, words, cword)
    source = "bash-completion"
    if not candidates:
        candidates = fallback_complete(backend, repo, words, cword)
        source = "fallback"
    candidates = candidates[:MAX_CANDIDATES]
    common = os.path.commonprefix(candidates) if candidates else ""
    return {"candidates": candidates, "common_prefix": common, "source": source}
