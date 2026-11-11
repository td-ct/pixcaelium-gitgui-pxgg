import os
from urllib.parse import quote, unquote


class CredentialStore:
    def __init__(self, path):
        self.path = path

    def _lines(self):
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip() and not l.startswith("#")]

    def _write(self, lines):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))

    def list(self):
        out = []
        for line in self._lines():
            try:
                proto, rest = line.split("://", 1)
                userinfo, host = rest.rsplit("@", 1)
                user = userinfo.split(":", 1)[0]
                out.append({"protocol": proto, "host": host, "username": unquote(user)})
            except ValueError:
                continue
        return out

    def set(self, protocol, host, username, password):
        lines = [
            l for l in self._lines()
            if not (l.startswith(protocol + "://") and l.endswith("@" + host))
        ]
        lines.append(
            f"{protocol}://{quote(username, safe='')}:{quote(password, safe='')}@{host}"
        )
        self._write(lines)

    def delete(self, protocol, host):
        lines = [
            l for l in self._lines()
            if not (l.startswith(protocol + "://") and l.endswith("@" + host))
        ]
        self._write(lines)

    def is_empty(self):
        return not self._lines()

    def git_args(self):
        if self.is_empty():
            return []
        return [
            "-c", "credential.helper=",
            "-c", f"credential.helper=store --file={self.path}",
        ]
