import json
import mimetypes
import os
import urllib.parse

from . import commands as commands_mod
from . import jobs as jobs_mod
from . import preflight as preflight_mod
from . import repos as repos_mod
from . import workflows as workflows_mod

MAX_BODY = 2 * 1024 * 1024


class Api:
    def __init__(self, backend, state, gui_dir, token=None):
        self.backend = backend
        self.state = state
        self.gui_dir = os.path.abspath(gui_dir)
        self.token = token

    def authorized(self, query, headers):
        if not self.token:
            return True
        if query.get("token", [None])[0] == self.token:
            return True
        auth = headers.get("authorization", "")
        return auth == "Bearer " + self.token

    def route(self, method, raw_path, query, headers, body):
        if not self.authorized(query, headers):
            return 401, {"error": "unauthorized"}, "application/json"
        parsed = urllib.parse.urlparse(raw_path)
        path = parsed.path
        if path.startswith("/api/"):
            return self.api_route(method, path[len("/api/"):], query, body)
        if method != "GET":
            return 405, {"error": "method not allowed"}, "application/json"
        return self.static(path)

    def static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        norm = os.path.normpath(path).lstrip("/")
        full = os.path.abspath(os.path.join(self.gui_dir, norm))
        if not full.startswith(self.gui_dir + os.sep) and full != self.gui_dir:
            return 403, {"error": "forbidden"}, "application/json"
        if not os.path.isfile(full):
            return 404, {"error": "not found"}, "application/json"
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as f:
            return 200, f.read(), ctype

    def api_route(self, method, path, query, body):
        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            return 400, {"error": "invalid json"}, "application/json"
        b = self.backend
        st = self.state

        if path == "meta" and method == "GET":
            langs = []
            i18n_dir = os.path.join(self.gui_dir, "i18n")
            if os.path.isdir(i18n_dir):
                langs = sorted(f[:-5] for f in os.listdir(i18n_dir) if f.endswith(".json"))
            return 200, {
                "name": "gitgui", "backend": b.name, "langs": langs,
                "auth_required": bool(self.token),
            }, "application/json"

        if path.startswith("i18n/") and method == "GET":
            lang = path[len("i18n/"):]
            fp = os.path.join(self.gui_dir, "i18n", lang + ".json")
            if os.path.isfile(fp):
                with open(fp, "rb") as f:
                    return 200, f.read(), "application/json"
            return 404, {"error": "unknown lang"}, "application/json"

        if path == "commands" and method in ("GET", "POST"):
            catalog = commands_mod.load_catalog(self.gui_dir)
            return 200, commands_mod.commands_with_live_help(b, data.get("repo"), catalog), "application/json"

        if path == "man" and method in ("GET", "POST"):
            cmd = (query.get("cmd", [""])[0] or "").strip()
            if not cmd or not cmd.replace("-", "").replace("_", "").isalnum():
                return 400, {"error": "invalid cmd"}, "application/json"
            return 200, b.man(cmd, query.get("repo", [None])[0]), "application/json"

        if path == "help" and method in ("GET", "POST"):
            cmd = (query.get("cmd", [""])[0] or "").strip()
            return 200, {"cmd": cmd, "text": b.short_help(cmd, query.get("repo", [None])[0])}, "application/json"

        if path == "workflows" and method == "GET":
            return 200, {"workflows": workflows_mod.list_workflows()}, "application/json"

        if path == "workflow/run" and method == "POST":
            wf_id = str(data.get("id", ""))
            repo = data.get("repo") or None
            res = workflows_mod.run_workflow(b, st, repo, wf_id, data.get("params") or {}, job_id=data.get("job_id"))
            return 200, res, "application/json"

        if path == "exec" and method == "POST":
            args = data.get("args")
            if not isinstance(args, list) or not all(isinstance(a, str) for a in args) or len(args) > 200:
                return 400, {"error": "args must be a list of strings (max 200)"}, "application/json"
            repo = data.get("repo") or None
            timeout = data.get("timeout", 60)
            r = b.run_trunc(repo, args, timeout, job_id=data.get("job_id"))
            return 200, {
                "exit_code": r.exit_code, "stdout": r.stdout, "stderr": r.stderr,
                "truncated": r.truncated, "args": args,
            }, "application/json"

        if path == "stop" and method == "POST":
            job_id = str(data.get("job_id", ""))
            if not job_id:
                return 400, {"error": "job_id required"}, "application/json"
            stopped = jobs_mod.stop(job_id) or b.stop(job_id)
            return 200, {"stopped": stopped, "job_id": job_id}, "application/json"

        if path == "preflight" and method in ("GET", "POST"):
            import time as _time
            cache = getattr(st, "_preflight_cache", None)
            if cache and _time.time() - cache[0] < 60:
                return 200, cache[1], "application/json"
            res = preflight_mod.run_preflight(b, st)
            st._preflight_cache = (_time.time(), res)
            return 200, res, "application/json"

        if path == "preflight/install" and method == "POST":
            packages = data.get("packages")
            if not isinstance(packages, list) or not all(isinstance(p, str) for p in packages) or len(packages) > 20:
                return 400, {"error": "packages must be a list of strings (max 20)"}, "application/json"
            res = preflight_mod.install_packages(b, packages)
            st._preflight_cache = None
            return 200, res, "application/json"

        if path == "complete" and method == "POST":
            words = data.get("words")
            if not isinstance(words, list) or not all(isinstance(w, str) for w in words) or len(words) > 100:
                return 400, {"error": "words must be a list of strings (max 100)"}, "application/json"
            cword = int(data.get("cword", len(words) - 1))
            repo = data.get("repo") or None
            return 200, b.complete(repo, words, cword), "application/json"

        if path == "repos" and method == "GET":
            repos = st.repo_store.list()
            return 200, {"repos": [repos_mod.repo_info(b.run_trunc, r["path"]) for r in repos]}, "application/json"

        if path == "repos/add" and method == "POST":
            p = str(data.get("path", ""))
            if not p:
                return 400, {"error": "path required"}, "application/json"
            return 200, {"repos": st.repo_store.add(p)}, "application/json"

        if path == "repos/remove" and method == "POST":
            p = str(data.get("path", ""))
            return 200, {"repos": st.repo_store.remove(p)}, "application/json"

        if path == "fs/list" and method == "POST":
            p = str(data.get("path", "")) or None
            return 200, b.list_dirs(p), "application/json"

        if path == "credentials" and method == "GET":
            return 200, {"credentials": st.credential_store.list()}, "application/json"

        if path == "credentials/set" and method == "POST":
            proto = str(data.get("protocol", "https"))
            host = str(data.get("host", "")).strip()
            user = str(data.get("username", ""))
            pw = str(data.get("password", ""))
            if not host:
                return 400, {"error": "host required"}, "application/json"
            st.credential_store.set(proto, host, user, pw)
            return 200, {"credentials": st.credential_store.list()}, "application/json"

        if path == "credentials/delete" and method == "POST":
            st.credential_store.delete(str(data.get("protocol", "https")), str(data.get("host", "")))
            return 200, {"credentials": st.credential_store.list()}, "application/json"

        return 404, {"error": "unknown endpoint"}, "application/json"
