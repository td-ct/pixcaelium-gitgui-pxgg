import os
import subprocess

from .backend_base import Backend, ExecResult
from . import completion
from .util import base_env, truncate


class LocalBackend(Backend):
    name = "local"

    def run(self, repo, args, timeout=60):
        argv = ["git"] + self.base_args() + [str(a) for a in args]
        try:
            r = subprocess.run(
                argv, cwd=repo or None, env=base_env(),
                capture_output=True, timeout=max(5, min(int(timeout), 300)),
            )
            out, t1 = truncate(r.stdout.decode("utf-8", "replace"))
            err, t2 = truncate(r.stderr.decode("utf-8", "replace"))
            return ExecResult(r.returncode, out, err, t1 or t2)
        except subprocess.TimeoutExpired:
            return ExecResult(124, "", "timeout after %ss" % timeout, True)
        except FileNotFoundError:
            return ExecResult(127, "", "git executable not found", False)

    def complete(self, repo, words, cword):
        return completion.complete(self, repo, words, cword)

    def list_dirs(self, path):
        base = os.path.abspath(os.path.expanduser(path or os.getcwd()))
        try:
            entries = sorted(os.scandir(base), key=lambda e: e.name)
        except OSError:
            return {"path": base, "dirs": [], "error": "cannot list"}
        dirs = [e.name + "/" for e in entries if e.is_dir()][:500]
        parent = os.path.dirname(base.rstrip("/")) or "/"
        return {"path": base, "parent": parent, "dirs": dirs}
