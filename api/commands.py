import json
import os


def load_catalog(gui_dir):
    with open(os.path.join(gui_dir, "catalog", "commands.json"), encoding="utf-8") as f:
        return json.load(f)


def commands_with_live_help(backend, repo, catalog):
    try:
        cats = backend.help_a(repo)
        desc = {}
        for cat in cats:
            for c in cat["commands"]:
                desc[c["name"]] = c["desc"]
        for cat in catalog.get("categories", []):
            for cmd in cat.get("commands", []):
                if desc.get(cmd["name"]):
                    cmd["live_desc"] = desc[cmd["name"]]
    except Exception:
        pass
    return catalog
