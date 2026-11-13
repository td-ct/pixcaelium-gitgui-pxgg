import os

from .credentials import CredentialStore
from .repos import RepoStore


class State:
    def __init__(self, root):
        self.root = os.path.abspath(os.path.expanduser(root))
        os.makedirs(self.root, exist_ok=True)
        self.credential_store = CredentialStore(os.path.join(self.root, "credentials.store"))
        self.repo_store = RepoStore(os.path.join(self.root, "repos.json"))
