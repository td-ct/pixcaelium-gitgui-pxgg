package dev.gitgui

import dev.gitgui.backend.Backend
import dev.gitgui.backend.ExecResult
import org.json.JSONArray
import org.json.JSONObject
import java.util.regex.Pattern

data class Step(val args: List<String>, val timeout: Int = 60)

object Workflows {
    private fun runSteps(backend: Backend, repo: String?, steps: List<Step>): JSONObject {
        val out = JSONObject()
        val stepsArr = JSONArray()
        val combined = StringBuilder()
        var ok = true
        for (s in steps) {
            val r: ExecResult = backend.run(repo, s.args, s.timeout)
            if (r.exitCode != 0) ok = false
            combined.append(r.stderr).append(r.stdout).append("\n")
            stepsArr.put(JSONObject().put("args", JSONArray(s.args)).put("exit_code", r.exitCode)
                .put("stdout", r.stdout).put("stderr", r.stderr))
        }
        out.put("ok", ok).put("steps", stepsArr).put("output", combined.toString()).put("data", JSONObject())
        return out
    }

    private fun matchError(assets: (String) -> String, text: String, repo: String?): JSONObject? {
        val pats = JSONObject(assets("gui/catalog/error_patterns.json")).getJSONArray("patterns")
        for (i in 0 until pats.length()) {
            val p = pats.getJSONObject(i)
            val m = Pattern.compile(p.getString("pattern"), Pattern.CASE_INSENSITIVE).matcher(text)
            if (m.find()) {
                val res = JSONObject()
                res.put("id", p.getString("id"))
                res.put("title_key", p.optString("title_key"))
                res.put("detail_key", p.optString("detail_key"))
                res.put("suggestions", p.optJSONArray("suggestions") ?: JSONArray())
                return res
            }
        }
        return null
    }

    fun run(backend: Backend, assets: (String) -> String, repo: String?, id: String, params: JSONObject): JSONObject {
        val p = { k: String -> params.optString(k, "") }
        val b = { k: String -> params.optBoolean(k, false) }
        val steps = when (id) {
            "clone" -> listOf(Step(mutableListOf("clone", p("url")).apply { if (p("dir").isNotEmpty()) add(p("dir")) }, 300))
            "init" -> listOf(Step(mutableListOf("init").apply { if (p("path").isNotEmpty()) add(p("path")) }))
            "status" -> listOf(Step(listOf("status", "--porcelain=v1", "-b")))
            "commit" -> buildList {
                val files = params.optJSONArray("files") ?: JSONArray()
                if (files.length() > 0) add(Step(mutableListOf("add", "--").apply { for (i in 0 until files.length()) add(files.getString(i)) }))
                add(Step(listOf("commit", "-m", p("message"))))
            }
            "pull" -> listOf(Step(mutableListOf("pull").apply {
                if (b("rebase")) add("--rebase")
                if (b("allow_unrelated")) add("--allow-unrelated-histories")
            }, 300))
            "push" -> {
                val branch = backend.run(repo, listOf("rev-parse", "--abbrev-ref", "HEAD")).stdout.trim().ifEmpty { "HEAD" }
                val args = mutableListOf("push")
                if (b("force")) args.add("--force-with-lease")
                if (b("set_upstream")) args.addAll(listOf("-u", "origin", branch))
                listOf(Step(args, 300))
            }
            "branch_list" -> listOf(Step(listOf("for-each-ref", "--format=%(refname:short) %(objectname:short) %(subject)", "refs/heads")))
            "branch_create" -> listOf(Step(mutableListOf("branch", p("name")).apply { if (p("start_point").isNotEmpty()) add(p("start_point")) }))
            "branch_switch" -> listOf(Step(listOf("switch", p("name"))))
            "branch_delete" -> listOf(Step(listOf("branch", if (b("force")) "-D" else "-d", p("name"))))
            "merge" -> listOf(Step(listOf("merge", p("branch")), 300))
            "conflicts" -> when (p("action")) {
                "list" -> listOf(Step(listOf("diff", "--name-only", "--diff-filter=U")))
                "resolve" -> listOf(Step(listOf("add", "--", p("file"))))
                "continue" -> listOf(Step(listOf("merge", "--continue"), 300))
                "abort" -> listOf(Step(listOf("merge", "--abort")))
                else -> listOf(Step(listOf("diff", "--name-only", "--diff-filter=U")))
            }
            "stash_push" -> listOf(Step(mutableListOf("stash", "push").apply {
                if (b("include_untracked")) add("-u")
                if (p("message").isNotEmpty()) addAll(listOf("-m", p("message")))
            }))
            "stash_list" -> listOf(Step(listOf("stash", "list")))
            "stash_pop" -> listOf(Step(mutableListOf("stash", "pop").apply {
                val idx = params.optInt("index", 0)
                if (idx != 0) add("stash@{$idx}")
            }, 300))
            "log" -> listOf(Step(mutableListOf("log", "--oneline", "--decorate", "-n", p("n").ifEmpty { "50" }).apply { if (b("graph")) add("--graph") }))
            "diff" -> listOf(Step(mutableListOf("diff").apply {
                if (b("staged")) add("--cached")
                if (p("file").isNotEmpty()) addAll(listOf("--", p("file")))
            }))
            "remote_list" -> listOf(Step(listOf("remote", "-v")))
            "remote_add" -> listOf(Step(listOf("remote", "add", p("name"), p("url"))))
            "remote_remove" -> listOf(Step(listOf("remote", "remove", p("name"))))
            "set_identity" -> listOf(
                Step(listOf("config", "user.name", p("name"))),
                Step(listOf("config", "user.email", p("email")))
            )
            "fix_safe_directory" -> listOf(Step(listOf("config", "--global", "--add", "safe.directory", p("path").ifEmpty { repo ?: "*" })))
            "undo_last_commit" -> listOf(Step(listOf("reset", "--soft", "HEAD~1")))
            else -> return JSONObject().put("ok", false).put("steps", JSONArray())
                .put("output", "").put("data", JSONObject())
                .put("error", JSONObject().put("id", "unknown_workflow"))
        }
        val res = runSteps(backend, repo, steps)
        val err = matchError(assets, res.getString("output"), repo)
        if (err != null) res.put("error", err)
        return res
    }
}
