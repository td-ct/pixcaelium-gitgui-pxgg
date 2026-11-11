from abc import ABC, abstractmethod
from dataclasses import dataclass

from .manpage import man_text, short_help, parse_help_a
from .util import truncate


@dataclass
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    truncated: bool = False


class Backend(ABC):
    name = "abstract"

    def __init__(self, state):
        self.state = state

    def base_args(self, extra=None):
        args = ["-c", "core.quotepath=false"]
        args += self.state.credential_store.git_args()
        if extra:
            args += list(extra)
        return args

    @abstractmethod
    def run(self, repo, args, timeout=60):
        ...

    @abstractmethod
    def complete(self, repo, words, cword):
        ...

    def list_dirs(self, path):
        return []

    def man(self, cmd, cwd=None):
        return man_text(self, cmd, cwd)

    def short_help(self, cmd, cwd=None):
        return short_help(self, cmd, cwd)

    def help_a(self, cwd=None):
        return parse_help_a(self, cwd)

    def run_trunc(self, repo, args, timeout=60):
        r = self.run(repo, args, timeout)
        out, t1 = truncate(r.stdout)
        err, t2 = truncate(r.stderr)
        return ExecResult(r.exit_code, out, err, t1 or t2)
