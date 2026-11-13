import threading

from . import error_patterns

WORKFLOWS = {}
_CTX = threading.local()


def wf(wf_id, title_key, desc_key, params):
    def deco(fn):
        WORKFLOWS[wf_id] = {
            "id": wf_id, "title_key": title_key, "desc_key": desc_key,
            "params": params, "run": fn,
        }
        return fn
    return deco


def step(backend, repo, args, timeout=60):
    r = backend.run_trunc(repo, args, timeout, job_id=getattr(_CTX, "job_id", None))
    return {
        "args": list(args), "exit_code": r.exit_code,
        "stdout": r.stdout, "stderr": r.stderr, "truncated": r.truncated,
    }


def result(steps, ok=None, data=None, error=None):
    combined = "\n".join((s["stderr"] + s["stdout"]) for s in steps)
    if ok is None:
        ok = all(s["exit_code"] == 0 for s in steps)
    return {
        "ok": ok, "steps": steps, "output": combined,
        "error": error or error_patterns.match(combined), "data": data or {},
    }


def parse_status(backend, repo):
    s = step(backend, repo, ["status", "--porcelain=v1", "-b"])
    branch = ""
    files = []
    for line in s["stdout"].splitlines():
        if line.startswith("##"):
            branch = line[2:].strip().split("...")[0]
        elif line.strip():
            code = line[:2]
            path = line[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            files.append({"code": code.strip() or code, "path": path, "x": code[0], "y": code[1]})
    return branch, files


@wf("clone", "wf.clone.title", "wf.clone.desc", [
    {"key": "url", "type": "text", "required": True, "label_key": "wf.clone.param.url"},
    {"key": "dir", "type": "path", "label_key": "wf.clone.param.dir"},
])
def wf_clone(backend, state, repo, p):
    args = ["clone", p.get("url", "")]
    if p.get("dir"):
        args.append(p["dir"])
    steps = [step(backend, None, args, timeout=300)]
    return result(steps)


@wf("init", "wf.init.title", "wf.init.desc", [
    {"key": "path", "type": "path", "label_key": "wf.init.param.path"},
])
def wf_init(backend, state, repo, p):
    args = ["init"]
    if p.get("path"):
        args.append(p["path"])
    steps = [step(backend, p.get("path") or repo, args)]
    return result(steps)


@wf("status", "wf.status.title", "wf.status.desc", [])
def wf_status(backend, state, repo, p):
    branch, files = parse_status(backend, repo)
    s = step(backend, repo, ["status", "--porcelain=v1", "-b"])
    return result([s], data={"branch": branch, "files": files})


@wf("commit", "wf.commit.title", "wf.commit.desc", [
    {"key": "files", "type": "files", "required": True, "label_key": "wf.commit.param.files"},
    {"key": "message", "type": "text", "required": True, "label_key": "wf.commit.param.message"},
])
def wf_commit(backend, state, repo, p):
    files = p.get("files") or []
    if isinstance(files, str):
        files = [f for f in files.splitlines() if f.strip()]
    steps = []
    if files:
        steps.append(step(backend, repo, ["add", "--"] + files))
    steps.append(step(backend, repo, ["commit", "-m", p.get("message", "")]))
    return result(steps)


@wf("pull", "wf.pull.title", "wf.pull.desc", [
    {"key": "rebase", "type": "bool", "label_key": "wf.pull.param.rebase"},
    {"key": "allow_unrelated", "type": "bool", "label_key": "wf.pull.param.allow_unrelated"},
])
def wf_pull(backend, state, repo, p):
    args = ["pull"]
    if p.get("rebase"):
        args.append("--rebase")
    if p.get("allow_unrelated"):
        args.append("--allow-unrelated-histories")
    steps = [step(backend, repo, args, timeout=300)]
    return result(steps)


@wf("push", "wf.push.title", "wf.push.desc", [
    {"key": "set_upstream", "type": "bool", "label_key": "wf.push.param.set_upstream"},
    {"key": "force", "type": "bool", "label_key": "wf.push.param.force", "danger": True},
])
def wf_push(backend, state, repo, p):
    branch_r = step(backend, repo, ["rev-parse", "--abbrev-ref", "HEAD"])
    branch = branch_r["stdout"].strip() or "HEAD"
    args = ["push"]
    if p.get("force"):
        args.append("--force-with-lease")
    if p.get("set_upstream"):
        args += ["-u", "origin", branch]
    steps = [branch_r, step(backend, repo, args, timeout=300)]
    return result(steps)


@wf("branch_list", "wf.branch_list.title", "wf.branch_list.desc", [])
def wf_branch_list(backend, state, repo, p):
    s = step(backend, repo, ["for-each-ref", "--format=%(refname:short) %(objectname:short) %(subject)", "refs/heads"])
    cur = step(backend, repo, ["rev-parse", "--abbrev-ref", "HEAD"])
    branches = [
        {"name": l.split(" ", 1)[0], "rest": l.split(" ", 1)[1] if " " in l else ""}
        for l in s["stdout"].splitlines() if l.strip()
    ]
    return result([s, cur], data={"current": cur["stdout"].strip(), "branches": branches})


@wf("branch_create", "wf.branch_create.title", "wf.branch_create.desc", [
    {"key": "name", "type": "text", "required": True, "label_key": "wf.branch_create.param.name"},
    {"key": "start_point", "type": "text", "complete": "branch", "label_key": "wf.branch_create.param.start_point"},
])
def wf_branch_create(backend, state, repo, p):
    args = ["branch", p.get("name", "")]
    if p.get("start_point"):
        args.append(p["start_point"])
    steps = [step(backend, repo, args)]
    return result(steps)


@wf("branch_switch", "wf.branch_switch.title", "wf.branch_switch.desc", [
    {"key": "name", "type": "text", "required": True, "complete": "branch", "label_key": "wf.branch_switch.param.name"},
])
def wf_branch_switch(backend, state, repo, p):
    name = p.get("name", "")
    s = step(backend, repo, ["switch", name])
    steps = [s]
    if s["exit_code"] != 0 and "'switch' is not a git command" in s["stderr"].lower():
        s2 = step(backend, repo, ["checkout", name])
        steps.append(s2)
    return result(steps)


@wf("branch_delete", "wf.branch_delete.title", "wf.branch_delete.desc", [
    {"key": "name", "type": "text", "required": True, "complete": "branch", "label_key": "wf.branch_delete.param.name"},
    {"key": "force", "type": "bool", "label_key": "wf.branch_delete.param.force", "danger": True},
])
def wf_branch_delete(backend, state, repo, p):
    args = ["branch", "-D" if p.get("force") else "-d", p.get("name", "")]
    steps = [step(backend, repo, args)]
    return result(steps)


@wf("merge", "wf.merge.title", "wf.merge.desc", [
    {"key": "branch", "type": "text", "required": True, "complete": "branch", "label_key": "wf.merge.param.branch"},
])
def wf_merge(backend, state, repo, p):
    steps = [step(backend, repo, ["merge", p.get("branch", "")], timeout=300)]
    return result(steps)


@wf("conflicts", "wf.conflicts.title", "wf.conflicts.desc", [
    {"key": "action", "type": "select", "required": True, "label_key": "wf.conflicts.param.action",
     "options": ["list", "resolve", "continue", "abort"]},
    {"key": "file", "type": "text", "complete": "file", "label_key": "wf.conflicts.param.file"},
])
def wf_conflicts(backend, state, repo, p):
    action = p.get("action", "list")
    steps = []
    data = {}
    if action == "list":
        s = step(backend, repo, ["diff", "--name-only", "--diff-filter=U"])
        steps.append(s)
        data["files"] = [l for l in s["stdout"].splitlines() if l.strip()]
    elif action == "resolve":
        steps.append(step(backend, repo, ["add", "--", p.get("file", "")]))
    elif action == "continue":
        steps.append(step(backend, repo, ["merge", "--continue"], timeout=300))
    elif action == "abort":
        steps.append(step(backend, repo, ["merge", "--abort"]))
    return result(steps, data=data)


@wf("stash_push", "wf.stash_push.title", "wf.stash_push.desc", [
    {"key": "message", "type": "text", "label_key": "wf.stash_push.param.message"},
    {"key": "include_untracked", "type": "bool", "label_key": "wf.stash_push.param.include_untracked"},
])
def wf_stash_push(backend, state, repo, p):
    args = ["stash", "push"]
    if p.get("include_untracked"):
        args.append("-u")
    if p.get("message"):
        args += ["-m", p["message"]]
    steps = [step(backend, repo, args)]
    return result(steps)


@wf("stash_list", "wf.stash_list.title", "wf.stash_list.desc", [])
def wf_stash_list(backend, state, repo, p):
    steps = [step(backend, repo, ["stash", "list"])]
    return result(steps)


@wf("stash_pop", "wf.stash_pop.title", "wf.stash_pop.desc", [
    {"key": "index", "type": "int", "label_key": "wf.stash_pop.param.index"},
])
def wf_stash_pop(backend, state, repo, p):
    args = ["stash", "pop"]
    idx = p.get("index")
    if idx not in (None, "", 0):
        args.append("stash@{%s}" % idx)
    steps = [step(backend, repo, args, timeout=300)]
    return result(steps)


@wf("log", "wf.log.title", "wf.log.desc", [
    {"key": "n", "type": "int", "label_key": "wf.log.param.n"},
    {"key": "graph", "type": "bool", "label_key": "wf.log.param.graph"},
])
def wf_log(backend, state, repo, p):
    args = ["log", "--oneline", "--decorate", "-n", str(p.get("n") or 50)]
    if p.get("graph"):
        args.append("--graph")
    steps = [step(backend, repo, args)]
    return result(steps)


@wf("diff", "wf.diff.title", "wf.diff.desc", [
    {"key": "staged", "type": "bool", "label_key": "wf.diff.param.staged"},
    {"key": "file", "type": "text", "complete": "file", "label_key": "wf.diff.param.file"},
])
def wf_diff(backend, state, repo, p):
    args = ["diff"]
    if p.get("staged"):
        args.append("--cached")
    if p.get("file"):
        args += ["--", p["file"]]
    steps = [step(backend, repo, args)]
    return result(steps)


@wf("remote_list", "wf.remote_list.title", "wf.remote_list.desc", [])
def wf_remote_list(backend, state, repo, p):
    steps = [step(backend, repo, ["remote", "-v"])]
    return result(steps)


@wf("remote_add", "wf.remote_add.title", "wf.remote_add.desc", [
    {"key": "name", "type": "text", "required": True, "label_key": "wf.remote_add.param.name"},
    {"key": "url", "type": "text", "required": True, "label_key": "wf.remote_add.param.url"},
])
def wf_remote_add(backend, state, repo, p):
    steps = [step(backend, repo, ["remote", "add", p.get("name", ""), p.get("url", "")])]
    return result(steps)


@wf("remote_remove", "wf.remote_remove.title", "wf.remote_remove.desc", [
    {"key": "name", "type": "text", "required": True, "complete": "remote", "label_key": "wf.remote_remove.param.name"},
])
def wf_remote_remove(backend, state, repo, p):
    steps = [step(backend, repo, ["remote", "remove", p.get("name", "")])]
    return result(steps)


@wf("set_identity", "wf.set_identity.title", "wf.set_identity.desc", [
    {"key": "name", "type": "text", "required": True, "label_key": "wf.set_identity.param.name"},
    {"key": "email", "type": "text", "required": True, "label_key": "wf.set_identity.param.email"},
])
def wf_set_identity(backend, state, repo, p):
    scope = [] if repo else ["--global"]
    steps = [
        step(backend, repo, ["config"] + scope + ["user.name", p.get("name", "")]),
        step(backend, repo, ["config"] + scope + ["user.email", p.get("email", "")]),
    ]
    return result(steps)


@wf("fix_safe_directory", "wf.fix_safe_directory.title", "wf.fix_safe_directory.desc", [
    {"key": "path", "type": "path", "label_key": "wf.fix_safe_directory.param.path"},
])
def wf_fix_safe_directory(backend, state, repo, p):
    path = p.get("path") or repo or "*"
    steps = [step(backend, repo, ["config", "--global", "--add", "safe.directory", path])]
    return result(steps)


@wf("undo_last_commit", "wf.undo_last_commit.title", "wf.undo_last_commit.desc", [])
def wf_undo_last_commit(backend, state, repo, p):
    steps = [step(backend, repo, ["reset", "--soft", "HEAD~1"])]
    return result(steps)


def list_workflows():
    return [
        {"id": k, "title_key": v["title_key"], "desc_key": v["desc_key"], "params": v["params"]}
        for k, v in WORKFLOWS.items()
    ]


def coerce_params(spec, params):
    out = {}
    for p in spec["params"]:
        key = p["key"]
        val = (params or {}).get(key)
        t = p.get("type")
        if t == "bool":
            out[key] = bool(val)
        elif t == "int":
            try:
                out[key] = int(val) if val not in (None, "") else 0
            except (TypeError, ValueError):
                out[key] = 0
        elif t == "files":
            out[key] = val or []
        else:
            out[key] = "" if val is None else str(val)
    return out


def run_workflow(backend, state, repo, wf_id, params, job_id=None):
    spec = WORKFLOWS.get(wf_id)
    if not spec:
        return {"ok": False, "error": {"id": "unknown_workflow", "title_key": "err.unknown_workflow.title", "detail_key": "err.unknown_workflow.detail", "suggestions": []}, "steps": [], "output": "", "data": {}}
    coerced = coerce_params(spec, params)
    _CTX.job_id = job_id
    try:
        return spec["run"](backend, state, repo, coerced)
    finally:
        _CTX.job_id = None
