import re

PATTERNS = [
    {
        "id": "merge_conflict",
        "pattern": r"Automatic merge failed|CONFLICT \(|Merge conflict in|Unmerged paths",
        "title_key": "err.merge_conflict.title",
        "detail_key": "err.merge_conflict.detail",
        "suggestions": [
            {"label_key": "sugg.resolve_conflicts", "type": "workflow", "workflow": "conflicts", "params": {"action": "list"}},
        ],
    },
    {
        "id": "divergent_branches",
        "pattern": r"Need to specify how to reconcile divergent branches|divergent branches",
        "title_key": "err.divergent_branches.title",
        "detail_key": "err.divergent_branches.detail",
        "suggestions": [
            {"label_key": "sugg.pull_merge", "type": "workflow", "workflow": "pull", "params": {}},
            {"label_key": "sugg.pull_rebase", "type": "workflow", "workflow": "pull", "params": {"rebase": True}},
        ],
    },
    {
        "id": "dubious_ownership",
        "pattern": r"dubious ownership",
        "title_key": "err.dubious_ownership.title",
        "detail_key": "err.dubious_ownership.detail",
        "suggestions": [
            {"label_key": "sugg.add_safe_directory", "type": "workflow", "workflow": "fix_safe_directory", "params": {}},
        ],
    },
    {
        "id": "local_changes_overwritten",
        "pattern": r"would be overwritten by (merge|checkout|pull|rebase)|Your local changes",
        "title_key": "err.local_changes_overwritten.title",
        "detail_key": "err.local_changes_overwritten.detail",
        "suggestions": [
            {"label_key": "sugg.stash_changes", "type": "workflow", "workflow": "stash_push", "params": {}},
            {"label_key": "sugg.discard_changes", "type": "exec", "args": ["checkout", "--", "."], "danger": True},
        ],
    },
    {
        "id": "need_commit_or_stash",
        "pattern": r"Please commit your changes or stash them",
        "title_key": "err.need_commit_or_stash.title",
        "detail_key": "err.need_commit_or_stash.detail",
        "suggestions": [
            {"label_key": "sugg.stash_changes", "type": "workflow", "workflow": "stash_push", "params": {}},
            {"label_key": "sugg.commit_changes", "type": "workflow", "workflow": "commit", "params": {}},
        ],
    },
    {
        "id": "non_fast_forward",
        "pattern": r"Updates were rejected|non-fast-forward|tip of your current branch is behind|fetch first",
        "title_key": "err.non_fast_forward.title",
        "detail_key": "err.non_fast_forward.detail",
        "suggestions": [
            {"label_key": "sugg.pull_first", "type": "workflow", "workflow": "pull", "params": {}},
            {"label_key": "sugg.force_push", "type": "workflow", "workflow": "push", "params": {"force": True}, "danger": True},
        ],
    },
    {
        "id": "auth_failed",
        "pattern": r"Authentication failed|could not read Username|Permission denied \(publickey\)|Invalid username or password|403|terminal prompts disabled",
        "title_key": "err.auth_failed.title",
        "detail_key": "err.auth_failed.detail",
        "suggestions": [
            {"label_key": "sugg.open_credentials", "type": "open", "target": "credentials"},
        ],
    },
    {
        "id": "repo_not_found",
        "pattern": r"Repository not found|fatal: repository .* not found|404",
        "title_key": "err.repo_not_found.title",
        "detail_key": "err.repo_not_found.detail",
        "suggestions": [
            {"label_key": "sugg.open_credentials", "type": "open", "target": "credentials"},
        ],
    },
    {
        "id": "not_a_repo",
        "pattern": r"not a git repository",
        "title_key": "err.not_a_repo.title",
        "detail_key": "err.not_a_repo.detail",
        "suggestions": [
            {"label_key": "sugg.select_repo", "type": "open", "target": "repo"},
            {"label_key": "sugg.init_repo", "type": "workflow", "workflow": "init", "params": {}},
        ],
    },
    {
        "id": "no_identity",
        "pattern": r"Please tell me who you are|empty ident|user\.name|Committer identity unknown",
        "title_key": "err.no_identity.title",
        "detail_key": "err.no_identity.detail",
        "suggestions": [
            {"label_key": "sugg.set_identity", "type": "workflow", "workflow": "set_identity", "params": {}},
        ],
    },
    {
        "id": "no_upstream",
        "pattern": r"no upstream|has no upstream branch|no tracking information|The current branch .* has no upstream",
        "title_key": "err.no_upstream.title",
        "detail_key": "err.no_upstream.detail",
        "suggestions": [
            {"label_key": "sugg.push_set_upstream", "type": "workflow", "workflow": "push", "params": {"set_upstream": True}},
        ],
    },
    {
        "id": "branch_exists",
        "pattern": r"already exists",
        "title_key": "err.branch_exists.title",
        "detail_key": "err.branch_exists.detail",
        "suggestions": [
            {"label_key": "sugg.switch_to_branch", "type": "workflow", "workflow": "branch_switch", "params": {}},
        ],
    },
    {
        "id": "branch_not_merged",
        "pattern": r"not fully merged|Cannot delete|not merged into",
        "title_key": "err.branch_not_merged.title",
        "detail_key": "err.branch_not_merged.detail",
        "suggestions": [
            {"label_key": "sugg.force_delete_branch", "type": "workflow", "workflow": "branch_delete", "params": {"force": True}, "danger": True},
        ],
    },
    {
        "id": "unrelated_histories",
        "pattern": r"refusing to merge unrelated histories",
        "title_key": "err.unrelated_histories.title",
        "detail_key": "err.unrelated_histories.detail",
        "suggestions": [
            {"label_key": "sugg.pull_allow_unrelated", "type": "workflow", "workflow": "pull", "params": {"allow_unrelated": True}},
        ],
    },
    {
        "id": "nothing_to_commit",
        "pattern": r"nothing to commit|no changes added to commit",
        "title_key": "err.nothing_to_commit.title",
        "detail_key": "err.nothing_to_commit.detail",
        "suggestions": [],
        "info": True,
    },
    {
        "id": "already_up_to_date",
        "pattern": r"Already up.to.date",
        "title_key": "err.already_up_to_date.title",
        "detail_key": "err.already_up_to_date.detail",
        "suggestions": [],
        "info": True,
    },
]

COMPILED = [(p["id"], re.compile(p["pattern"], re.IGNORECASE), p) for p in PATTERNS]


def match(text):
    for pid, rx, p in COMPILED:
        m = rx.search(text or "")
        if m:
            line = ""
            for l in (text or "").splitlines():
                if rx.search(l):
                    line = l.strip()
                    break
            result = dict(p)
            result.pop("pattern", None)
            result["matched"] = line
            return result
    return None
