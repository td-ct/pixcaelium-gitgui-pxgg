import os
import shlex
import subprocess
import tempfile
import time

from .backend_base import Backend, ExecResult
from . import completion
from .util import base_env, truncate

TERMUX_PREFIX = "/data/data/com.termux/files/usr"
RUN_COMMAND_SERVICE = "com.termux/com.termux.app.RunCommandService"
ACTION = "com.termux.RUN_COMMAND"


class TermuxBackend(Backend):
    name = "termux"

    def _am(self, script, workdir, timeout):
        result_dir = tempfile.mkdtemp(prefix="gitgui-run-")
        try:
            argv = [
                "am", "startservice", "--user", "0",
                "-n", RUN_COMMAND_SERVICE,
                "-a", ACTION,
                "--es", "com.termux.RUN_COMMAND_PATH", TERMUX_PREFIX + "/bin/bash",
                "--es", "com.termux.RUN_COMMAND_STDIN", script,
                "--es", "com.termux.RUN_COMMAND_WORKDIR", workdir or TERMUX_PREFIX + "/home",
                "--ez", "com.termux.RUN_COMMAND_BACKGROUND", "true",
                "--es", "com.termux.RUN_COMMAND_RESULT_DIRECTORY", result_dir,
            ]
            subprocess.run(argv, capture_output=True, timeout=30, env=base_env())
            deadline = time.time() + max(5, min(int(timeout), 300))
            exit_file = os.path.join(result_dir, "exit_code")
            while time.time() < deadline:
                if os.path.exists(exit_file):
                    break
                time.sleep(0.25)
            def read(name, default=""):
                p = os.path.join(result_dir, name)
                if os.path.exists(p):
                    with open(p, "rb") as f:
                        return f.read().decode("utf-8", "replace")
                return default
            if not os.path.exists(exit_file):
                return ExecResult(124, read("stdout"), read("stderr") or "timeout waiting for termux result", True)
            try:
                code = int(read("exit_code").strip() or "0")
            except ValueError:
                code = 0
            out, t1 = truncate(read("stdout"))
            err, t2 = truncate(read("stderr"))
            return ExecResult(code, out, err, t1 or t2)
        finally:
            for name in os.listdir(result_dir):
                try:
                    os.remove(os.path.join(result_dir, name))
                except OSError:
                    pass
            try:
                os.rmdir(result_dir)
            except OSError:
                pass

    def run(self, repo, args, timeout=60):
        all_args = self.base_args() + [str(a) for a in args]
        argfile = tempfile.NamedTemporaryFile(prefix="gitgui-args-", delete=False)
        argfile.write("\0".join(all_args).encode("utf-8"))
        argfile.close()
        workdir = repo or TERMUX_PREFIX + "/home"
        script = (
            "readarray -d '' -t A < %s; cd %s 2>/dev/null; exec %s/bin/git \"${A[@]}\""
            % (shlex.quote(argfile.name), shlex.quote(workdir), TERMUX_PREFIX)
        )
        try:
            return self._am(script, workdir, timeout)
        finally:
            try:
                os.remove(argfile.name)
            except OSError:
                pass

    def complete(self, repo, words, cword):
        script = completion.build_completion_script(words, cword)
        r = self._am(script, repo or TERMUX_PREFIX + "/home", 30)
        candidates = completion.normalize_candidates(r.stdout)[: completion.MAX_CANDIDATES]
        if not candidates:
            from .completion import fallback_complete
            candidates = fallback_complete(self, repo, words, cword)
        common = os.path.commonprefix(candidates) if candidates else ""
        return {"candidates": candidates, "common_prefix": common, "source": "termux"}

    def list_dirs(self, path):
        r = self.run(None, ["ls", "-1", "-d", (path or TERMUX_PREFIX + "/home") + "/*/"], timeout=30)
        dirs = [l.strip().rstrip("/").split("/")[-1] + "/" for l in r.stdout.splitlines() if l.strip()]
        parent = os.path.dirname((path or TERMUX_PREFIX + "/home").rstrip("/")) or "/"
        return {"path": path, "parent": parent, "dirs": sorted(dirs)[:500]}
