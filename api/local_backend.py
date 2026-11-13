import os
import subprocess

from .backend_base import Backend, ExecResult
from . import completion, jobs
from .util import base_env, truncate


class LocalBackend(Backend):
    name = "local"

    def _popen_run(self, argv, cwd, timeout, job_id):
        try:
            p = subprocess.Popen(
                argv, cwd=cwd or None, env=base_env(),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except FileNotFoundError:
            return ExecResult(127, "", "executable not found: " + argv[0])
        if job_id:
            jobs.register(job_id, p)
        try:
            out, err = p.communicate(timeout=max(5, min(int(timeout), 300)))
            o, t1 = truncate(out.decode("utf-8", "replace"))
            e, t2 = truncate(err.decode("utf-8", "replace"))
            return ExecResult(p.returncode, o, e, t1 or t2)
        except subprocess.TimeoutExpired:
            if job_id:
                jobs.stop(job_id)
            else:
                try:
                    p.kill()
                except Exception:
                    pass
            try:
                p.communicate(timeout=5)
            except Exception:
                pass
            return ExecResult(124, "", "timeout after %ss" % timeout, True)
        finally:
            if job_id:
                jobs.unregister(job_id)

    def run(self, repo, args, timeout=60, job_id=None):
        argv = ["git"] + self.base_args() + [str(a) for a in args]
        return self._popen_run(argv, repo, timeout, job_id)

    def raw(self, args, cwd=None, timeout=30, job_id=None):
        return self._popen_run([str(a) for a in args], cwd, timeout, job_id)

    def stop(self, job_id):
        return jobs.stop(job_id)

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
