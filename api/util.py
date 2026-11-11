import os
import re

MAX_OUTPUT = 512 * 1024

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def strip_overstrike(text):
    text = ANSI_RE.sub("", text)
    text = re.sub(".\x08", "", text)
    return text


def base_env():
    env = dict(os.environ)
    env.update({
        "PAGER": "cat",
        "GIT_PAGER": "cat",
        "MANPAGER": "cat",
        "GIT_EDITOR": "true",
        "GIT_TERMINAL_PROMPT": "0",
        "TERM": "dumb",
        "MANWIDTH": "100",
        "LC_ALL": "C.UTF-8",
    })
    return env


def truncate(text):
    if text is None:
        return "", False
    if len(text) > MAX_OUTPUT:
        return text[:MAX_OUTPUT], True
    return text, False
