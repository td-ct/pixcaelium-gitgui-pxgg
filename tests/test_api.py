import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from api import error_patterns
from api.http_api import Api
from api.local_backend import LocalBackend
from api.state import State
from server import make_handler
from http.server import ThreadingHTTPServer


def git(cwd, *args, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {args} failed: {r.stderr}")
    return r


def start_server(state_dir, token=None):
    state = State(state_dir)
    backend = LocalBackend(state)
    api = Api(backend, state, os.path.join(ROOT, "gui"), token=token)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(api))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}", state


def req(base, method, path, body=None, token=None):
    url = base + path + (f"?token={token}" if token else "")
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw or b"{}")
            except Exception:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b"{}")
        except Exception:
            return e.code, raw


class TestApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="gitgui-test-")
        cls.repo = os.path.join(cls.tmp, "repo")
        os.makedirs(cls.repo)
        git(cls.repo, "init", "-q", "-b", "main", ".")
        git(cls.repo, "config", "user.email", "t@example.com")
        git(cls.repo, "config", "user.name", "Tester")
        with open(os.path.join(cls.repo, "a.txt"), "w") as f:
            f.write("hello\n")
        git(cls.repo, "add", "a.txt")
        git(cls.repo, "commit", "-q", "-m", "init")
        git(cls.repo, "branch", "glass")
        git(cls.repo, "branch", "glatt")

        cls.origin = os.path.join(cls.tmp, "origin.git")
        git(cls.tmp, "init", "-q", "--bare", "-b", "main", "origin.git")
        cls.A = os.path.join(cls.tmp, "A")
        cls.B = os.path.join(cls.tmp, "B")
        git(cls.tmp, "clone", "-q", cls.origin, "A")
        git(cls.A, "config", "user.email", "t@example.com")
        git(cls.A, "config", "user.name", "Tester")
        git(cls.A, "symbolic-ref", "HEAD", "refs/heads/main")
        with open(os.path.join(cls.A, "base.txt"), "w") as f:
            f.write("base\n")
        git(cls.A, "add", "base.txt")
        git(cls.A, "commit", "-q", "-m", "base")
        git(cls.A, "push", "-q", "origin", "HEAD:main")
        git(cls.tmp, "clone", "-q", cls.origin, "B")
        git(cls.B, "config", "user.email", "t@example.com")
        git(cls.B, "config", "user.name", "Tester")
        git(cls.B, "config", "pull.rebase", "false")
        with open(os.path.join(cls.A, "f.txt"), "w") as f:
            f.write("from A\n")
        git(cls.A, "add", "f.txt")
        git(cls.A, "commit", "-q", "-m", "change A")
        git(cls.A, "push", "-q", "origin", "HEAD:main")
        with open(os.path.join(cls.B, "f.txt"), "w") as f:
            f.write("from B\n")
        git(cls.B, "add", "f.txt")
        git(cls.B, "commit", "-q", "-m", "change B")

        cls.srv, cls.base, cls.state = start_server(os.path.join(cls.tmp, "state"))
        req(cls.base, "POST", "/api/repos/add", {"path": cls.repo})
        req(cls.base, "POST", "/api/repos/add", {"path": cls.B})

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_meta(self):
        status, data = req(self.base, "GET", "/api/meta")
        self.assertEqual(status, 200)
        self.assertEqual(data["backend"], "local")
        self.assertIn("en", data["langs"])
        self.assertIn("de", data["langs"])

    def test_static_index(self):
        status, raw = req(self.base, "GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"gitgui", raw)
        status, raw = req(self.base, "GET", "/app.js")
        self.assertEqual(status, 200)
        self.assertIn(b"api(", raw)

    def test_repos(self):
        status, data = req(self.base, "GET", "/api/repos")
        self.assertEqual(status, 200)
        paths = [r["path"] for r in data["repos"]]
        self.assertIn(self.repo, paths)
        info = [r for r in data["repos"] if r["path"] == self.repo][0]
        self.assertTrue(info["is_repo"])
        self.assertEqual(info["branch"], "main")

    def test_exec(self):
        status, data = req(self.base, "POST", "/api/exec", {"repo": self.repo, "args": ["status", "--porcelain"]})
        self.assertEqual(status, 200)
        self.assertEqual(data["exit_code"], 0)
        status, data = req(self.base, "POST", "/api/exec", {"repo": self.repo, "args": ["definitely-not-a-command"]})
        self.assertNotEqual(data["exit_code"], 0)

    def test_complete_branches_glass_glatt(self):
        status, data = req(self.base, "POST", "/api/complete",
                           {"repo": self.repo, "words": ["git", "checkout", "gla"], "cword": 2})
        self.assertEqual(status, 200)
        self.assertIn("glass", data["candidates"])
        self.assertIn("glatt", data["candidates"])
        self.assertEqual(data["common_prefix"], "gla")

    def test_complete_subcommand(self):
        status, data = req(self.base, "POST", "/api/complete",
                           {"repo": self.repo, "words": ["git", "mer"], "cword": 1})
        self.assertIn("merge", data["candidates"])

    def test_complete_files(self):
        status, data = req(self.base, "POST", "/api/complete",
                           {"repo": self.repo, "words": ["git", "add", ""], "cword": 2})
        self.assertIn("a.txt", data["candidates"])

    def test_man_checkout(self):
        status, data = req(self.base, "GET", "/api/man?cmd=checkout&repo=" + self.repo)
        self.assertEqual(status, 200)
        self.assertGreater(len(data["text"]), 200)
        self.assertIn("checkout", data["text"].lower())
        self.assertTrue(any(k in data["text"].lower() for k in ("usage", "synopsis", "name")))

    def test_help_short(self):
        status, data = req(self.base, "GET", "/api/help?cmd=log")
        self.assertEqual(status, 200)
        self.assertIn("usage", data["text"].lower())

    def test_commands_catalog(self):
        status, data = req(self.base, "POST", "/api/commands", {"repo": self.repo})
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(data["categories"]), 8)
        names = [c["name"] for cat in data["categories"] for c in cat["commands"]]
        for n in ("clone", "pull", "push", "checkout", "merge", "stash", "log"):
            self.assertIn(n, names)
        clone = [c for cat in data["categories"] for c in cat["commands"] if c["name"] == "clone"][0]
        self.assertTrue(clone.get("live_desc"))

    def test_workflows_list(self):
        status, data = req(self.base, "GET", "/api/workflows")
        ids = [w["id"] for w in data["workflows"]]
        for w in ("clone", "status", "commit", "pull", "push", "merge", "conflicts", "stash_push"):
            self.assertIn(w, ids)
        with open(os.path.join(ROOT, "gui", "catalog", "workflows.json")) as f:
            static = json.load(f)["workflows"]
        self.assertEqual(sorted(ids), sorted(w["id"] for w in static))
        with open(os.path.join(ROOT, "gui", "catalog", "error_patterns.json")) as f:
            static_pats = json.load(f)["patterns"]
        self.assertEqual(
            sorted(p["id"] for p in error_patterns.PATTERNS),
            sorted(p["id"] for p in static_pats),
        )

    def test_workflow_status_and_commit(self):
        with open(os.path.join(self.repo, "b.txt"), "w") as f:
            f.write("new\n")
        status, res = req(self.base, "POST", "/api/workflow/run",
                          {"repo": self.repo, "id": "status", "params": {}})
        self.assertEqual(status, 200)
        self.assertEqual(res["data"]["branch"], "main")
        paths = [f["path"] for f in res["data"]["files"]]
        self.assertIn("b.txt", paths)
        status, res = req(self.base, "POST", "/api/workflow/run",
                          {"repo": self.repo, "id": "commit",
                           "params": {"files": ["b.txt"], "message": "add b"}})
        self.assertTrue(res["ok"], res["output"])
        status, data = req(self.base, "POST", "/api/exec", {"repo": self.repo, "args": ["log", "--oneline"]})
        self.assertIn("add b", data["stdout"])

    def test_workflow_pull_conflict_and_resolve(self):
        status, push_res = req(self.base, "POST", "/api/exec", {"repo": self.B, "args": ["push"]})
        self.assertNotEqual(push_res["exit_code"], 0)
        status, res = req(self.base, "POST", "/api/workflow/run",
                          {"repo": self.B, "id": "pull", "params": {}})
        self.assertFalse(res["ok"])
        self.assertIsNotNone(res["error"])
        self.assertEqual(res["error"]["id"], "merge_conflict")
        self.assertTrue(any(s["type"] == "workflow" and s["workflow"] == "conflicts"
                            for s in res["error"]["suggestions"]))
        status, res = req(self.base, "POST", "/api/workflow/run",
                          {"repo": self.B, "id": "conflicts", "params": {"action": "list"}})
        self.assertIn("f.txt", res["data"]["files"])
        with open(os.path.join(self.B, "f.txt"), "w") as f:
            f.write("resolved\n")
        status, res = req(self.base, "POST", "/api/workflow/run",
                          {"repo": self.B, "id": "conflicts", "params": {"action": "resolve", "file": "f.txt"}})
        self.assertTrue(res["ok"], res["output"])
        status, res = req(self.base, "POST", "/api/workflow/run",
                          {"repo": self.B, "id": "conflicts", "params": {"action": "continue"}})
        self.assertTrue(res["ok"], res["output"])
        status, data = req(self.base, "POST", "/api/exec", {"repo": self.B, "args": ["log", "--oneline", "-1"]})
        self.assertIn("Merge", data["stdout"])

    def test_error_patterns_unit(self):
        self.assertEqual(error_patterns.match("fatal: detected dubious ownership in repository at '/x'")["id"], "dubious_ownership")
        self.assertEqual(error_patterns.match("error: failed to push some refs; hint: Updates were rejected because the tip of your current branch is behind")["id"], "non_fast_forward")
        self.assertEqual(error_patterns.match("Already up to date.")["id"], "already_up_to_date")
        self.assertEqual(error_patterns.match("Authentication failed for 'https://github.com/x/y.git/'")["id"], "auth_failed")
        self.assertEqual(error_patterns.match("Please tell me who you are.")["id"], "no_identity")
        self.assertEqual(error_patterns.match("fatal: Need to specify how to reconcile divergent branches.")["id"], "divergent_branches")
        self.assertIsNone(error_patterns.match("everything fine"))

    def test_credentials(self):
        status, data = req(self.base, "POST", "/api/credentials/set",
                           {"protocol": "https", "host": "github.com", "username": "me", "password": "s3cret"})
        self.assertEqual(status, 200)
        hosts = [(c["protocol"], c["host"], c["username"]) for c in data["credentials"]]
        self.assertIn(("https", "github.com", "me"), hosts)
        self.assertTrue(self.state.credential_store.git_args())
        with open(self.state.credential_store.path) as f:
            content = f.read()
        self.assertIn("github.com", content)
        status, data = req(self.base, "POST", "/api/credentials/delete", {"protocol": "https", "host": "github.com"})
        self.assertEqual(data["credentials"], [])
        self.assertEqual(self.state.credential_store.git_args(), [])

    def test_i18n_de(self):
        status, data = req(self.base, "GET", "/api/i18n/de")
        self.assertEqual(status, 200)
        self.assertEqual(data["ui.tab.guided"], "Geführt")
        self.assertEqual(data["cmd.pull"], "Laden und mit anderem Repository integrieren")

    def test_fs_list(self):
        status, data = req(self.base, "POST", "/api/fs/list", {"path": self.tmp})
        self.assertEqual(status, 200)
        self.assertIn("repo/", data["dirs"])

    def test_init_endpoints(self):
        for path, method, body in [
            ("/api/meta", "GET", None),
            ("/api/i18n/en", "GET", None),
            ("/api/repos", "GET", None),
            ("/api/workflows", "GET", None),
            ("/api/commands", "POST", {"repo": self.repo}),
            ("/api/preflight", "GET", None),
        ]:
            status, _ = req(self.base, method, path, body)
            self.assertEqual(status, 200, path)

    def test_preflight(self):
        status, data = req(self.base, "GET", "/api/preflight")
        self.assertEqual(status, 200)
        self.assertEqual(data["backend"], "local")
        ids = {c["id"]: c for c in data["checks"]}
        self.assertTrue(ids["git"]["ok"])
        self.assertIn("git version", ids["git"]["detail"])

    def test_exec_with_job_id(self):
        status, data = req(self.base, "POST", "/api/exec",
                           {"repo": self.repo, "args": ["status", "--porcelain"], "job_id": "j-ok-1"})
        self.assertEqual(status, 200)
        self.assertEqual(data["exit_code"], 0)

    def test_stop_unknown_job(self):
        status, data = req(self.base, "POST", "/api/stop", {"job_id": "does-not-exist"})
        self.assertEqual(status, 200)
        self.assertFalse(data["stopped"])

    def test_stop_running_job(self):
        import threading
        import time
        from api import jobs
        backend = LocalBackend(self.state)
        result = {}
        def do_run():
            result["r"] = backend.raw(["sleep", "30"], job_id="j-stop-1")
        th = threading.Thread(target=do_run)
        th.start()
        time.sleep(1.0)
        t0 = time.time()
        stopped = jobs.stop("j-stop-1")
        th.join(timeout=15)
        elapsed = time.time() - t0
        self.assertTrue(stopped)
        self.assertIn("r", result)
        self.assertNotEqual(result["r"].exit_code, 0)
        self.assertLess(elapsed, 10)

    def test_branch_switch_workflow(self):
        status, res = req(self.base, "POST", "/api/workflow/run",
                          {"repo": self.repo, "id": "branch_switch", "params": {"name": "glass"}})
        self.assertTrue(res["ok"], res["output"])
        status, data = req(self.base, "POST", "/api/exec", {"repo": self.repo, "args": ["rev-parse", "--abbrev-ref", "HEAD"]})
        self.assertEqual(data["stdout"].strip(), "glass")
        req(self.base, "POST", "/api/workflow/run", {"repo": self.repo, "id": "branch_switch", "params": {"name": "main"}})


class TestAuth(unittest.TestCase):
    def test_token_required(self):
        tmp = tempfile.mkdtemp(prefix="gitgui-auth-")
        try:
            srv, base, _ = start_server(os.path.join(tmp, "state"), token="secret")
            status, _ = req(base, "GET", "/api/meta")
            self.assertEqual(status, 401)
            status, data = req(base, "GET", "/api/meta", token="secret")
            self.assertEqual(status, 200)
            self.assertTrue(data["auth_required"])
            srv.shutdown()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
