import json
import os
import time


class RepoStore:
    def __init__(self, path):
        self.path = path

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, repos):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(repos, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    def list(self):
        return self._load()

    def add(self, path):
        p = os.path.abspath(os.path.expanduser(path))
        repos = self._load()
        if not any(r["path"] == p for r in repos):
            repos.append({"path": p, "added": time.time()})
            self._save(repos)
        return repos

    def remove(self, path):
        p = os.path.abspath(os.path.expanduser(path))
        repos = [r for r in self._load() if r["path"] != p]
        self._save(repos)
        return repos


def repo_info(run, path):
    info = {"path": path, "is_repo": False}
    r = run(path, ["rev-parse", "--is-inside-work-tree"])
    if r.exit_code == 0 and r.stdout.strip() == "true":
        info["is_repo"] = True
        b = run(path, ["rev-parse", "--abbrev-ref", "HEAD"])
        info["branch"] = b.stdout.strip() or "HEAD"
        s = run(path, ["status", "--porcelain"])
        info["dirty"] = len([l for l in s.stdout.splitlines() if l.strip()])
        rem = run(path, ["remote"])
        info["remotes"] = rem.stdout.split()
    return info
