package dev.gitgui

import android.content.Context
import dev.gitgui.backend.Backend
import dev.gitgui.backend.ExecResult
import org.json.JSONArray
import org.json.JSONObject
import java.net.URLDecoder

object ApiRouter {
    private const val MAX_OUTPUT = 512 * 1024

    private fun trunc(s: String): String = if (s.length > MAX_OUTPUT) s.substring(0, MAX_OUTPUT) else s

    fun handle(context: Context, backend: Backend, method: String, rawPath: String, body: String?): Pair<Int, String> {
        val q = rawPath.indexOf('?')
        val path = if (q >= 0) rawPath.substring(0, q) else rawPath
        val query = if (q >= 0) rawPath.substring(q + 1) else ""
        fun qp(name: String): String? {
            for (part in query.split("&")) {
                val kv = part.split("=", limit = 2)
                if (kv[0] == name) return URLDecoder.decode(kv.getOrElse(1) { "" }, "UTF-8")
            }
            return null
        }
        fun assets(name: String): String = context.assets.open(name).bufferedReader().readText()

        val json = if (!body.isNullOrEmpty()) JSONObject(body) else JSONObject()
        val repo = json.optString("repo", null)

        return try {
            when {
                path == "/api/meta" -> 200 to JSONObject().put("name", "gitgui").put("backend", backend.name)
                    .put("langs", JSONArray(listOf("en", "de"))).put("auth_required", false).toString()

                path.startsWith("/api/i18n/") -> 200 to assets("gui/i18n/" + path.removePrefix("/api/i18n/") + ".json")

                path == "/api/commands" -> {
                    val catalog = JSONObject(assets("gui/catalog/commands.json"))
                    val helpA = try { backend.helpA(repo) } catch (e: Exception) { "" }
                    val desc = HashMap<String, String>()
                    var current: JSONObject? = null
                    for (line in helpA.lineSequence()) {
                        if (line.isBlank()) continue
                        if (!line.startsWith(" ") && line.trimEnd().endsWith("Commands")) continue
                        if (line.startsWith("   ")) {
                            val parts = line.trim().split(Regex("\\s+"), 2)
                            if (parts.isNotEmpty()) desc[parts[0]] = if (parts.size > 1) parts[1] else ""
                        }
                    }
                    for (i in 0 until catalog.getJSONArray("categories").length()) {
                        val cat = catalog.getJSONArray("categories").getJSONObject(i)
                        for (j in 0 until cat.getJSONArray("commands").length()) {
                            val cmd = cat.getJSONArray("commands").getJSONObject(j)
                            desc[cmd.getString("name")]?.let { cmd.put("live_desc", it) }
                        }
                    }
                    200 to catalog.toString()
                }

                path == "/api/workflows" -> 200 to assets("gui/catalog/workflows.json")

                path == "/api/workflow/run" && method == "POST" -> {
                    val res = Workflows.run(backend, ::assets, repo, json.getString("id"), json.optJSONObject("params") ?: JSONObject())
                    200 to res.toString()
                }

                path == "/api/exec" && method == "POST" -> {
                    val args = json.getJSONArray("args")
                    val argList = (0 until args.length()).map { args.getString(it) }
                    val timeout = json.optInt("timeout", 60).coerceIn(5, 300)
                    val jobId = json.optString("job_id", null)
                    val r = backend.run(repo, argList, timeout, jobId)
                    200 to JSONObject().put("exit_code", r.exitCode).put("stdout", trunc(r.stdout))
                        .put("stderr", trunc(r.stderr)).put("truncated", false).put("args", JSONArray(argList)).toString()
                }

                path == "/api/complete" && method == "POST" -> {
                    val words = json.getJSONArray("words")
                    val wordList = (0 until words.length()).map { words.getString(it) }
                    val cword = json.optInt("cword", wordList.size - 1)
                    val r = backend.complete(repo, wordList, cword)
                    200 to JSONObject(r.mapValues { e ->
                        when (val v = e.value) {
                            is List<*> -> JSONArray(v)
                            else -> v
                        }
                    }).toString()
                }

                path == "/api/man" -> {
                    val cmd = qp("cmd") ?: ""
                    200 to JSONObject(backend.man(cmd, qp("repo"))).toString()
                }

                path == "/api/help" -> 200 to JSONObject().put("cmd", qp("cmd")).put("text", backend.shortHelp(qp("cmd") ?: "", qp("repo"))).toString()

                path == "/api/fs/list" && method == "POST" -> 200 to JSONObject(backend.listDirs(json.optString("path", null))).toString()

                path == "/api/repos" -> 200 to JSONObject().put("repos", JSONArray()).toString()

                path == "/api/stop" && method == "POST" ->
                    200 to JSONObject().put("stopped", backend.stop(json.optString("job_id"))).toString()

                path == "/api/preflight" -> preflightResponse()


                
path == "/api/preflight/install" && method == "POST" -> {
                    val pkgs = json.getJSONArray("packages")
                    val list = (0 until pkgs.length()).map { pkgs.getString(it) }
                    val r = if (backend.name == "termux") backend.raw(listOf("pkg", "install", "-y") + list, timeoutSec = 600)
                            else ExecResult(1, "", "apt install ${list.joinToString(" ")}")
                    200 to JSONObject().put("ok", r.exitCode == 0).put("output", (r.stdout + r.stderr).takeLast(4000)).toString()
                }

                else -> 404 to JSONObject().put("error", "unknown endpoint").toString()
            }
        } catch (e: Exception) {
            500 to JSONObject().put("error", e.message ?: "error").toString()
        }
    }
    private val preflightLock = java.util.concurrent.atomic.AtomicBoolean(false)
    private var preflightCache: String? = null
    private var preflightCacheTs = 0L
    private fun preflightResponse(): Pair<Int, String> {
        val c = preflightCache
        if (c != null && System.currentTimeMillis() - preflightCacheTs < 60_000) return 200 to c
        if (preflightLock.compareAndSet(false, true)) {
            Thread {
                try {
                    val r = computePreflight()
                    preflightCache = r
                    preflightCacheTs = System.currentTimeMillis()
                } catch (e: Exception) {
                    preflightCache = JSONObject().put("backend", backend.name).put("ok", false).put("checks", JSONArray()).put("error", e.message ?: "?").toString()
                    preflightCacheTs = System.currentTimeMillis()
                } finally { preflightLock.set(false) }
            }.start()
        }
        return 200 to JSONObject().put("backend", backend.name).put("ok", true).put("running", true).put("checks", JSONArray()).toString()
    }
    private fun computePreflight(): String {
                    val checks = JSONArray()
                    fun add(id: String, label: String, ok: Boolean, detail: String = "", install: String? = null, optional: Boolean = false) {
                        val o = JSONObject().put("id", id).put("label_key", label).put("ok", ok)
                            .put("detail", detail).put("optional", optional)
                        if (install != null) o.put("install", install) else o.put("install", JSONObject.NULL)
                        checks.put(o)
                    }
                    val g = backend.raw(listOf("git", "--version"))
                    add("git", "pf.git", g.exitCode == 0, g.stdout.trim().lineSequence().firstOrNull() ?: "", if (g.exitCode != 0) "git" else null)
                    val bsh = backend.raw(listOf("bash", "-c", "echo ok"))
                    add("bash", "pf.bash", bsh.exitCode == 0 && bsh.stdout.trim() == "ok", "", if (bsh.exitCode != 0) "bash" else null)
                    val comp = backend.raw(listOf("bash", "-c", "for f in \"\$PREFIX/share/bash-completion/completions/git\" \"\$PREFIX/share/git-core/git-completion.bash\"; do [ -f \"\$f\" ] && echo \"\$f\" && exit 0; done; exit 1"))
                    add("completion", "pf.completion", comp.exitCode == 0, comp.stdout.trim(), if (comp.exitCode != 0) "bash-completion" else null, optional = true)
                    val mn = backend.raw(listOf("bash", "-c", "command -v man || true"))
                    add("man", "pf.man", mn.stdout.isNotBlank(), mn.stdout.trim(), optional = true)
                    if (backend.name == "termux") {
                        val ping = backend.raw(listOf("echo", "ok"), timeoutSec = 12)
                        add("termux_connection", "pf.termux_connection", ping.exitCode == 0 && ping.stdout.trim() == "ok", ping.stderr.trim().take(200))
                        val props = backend.raw(listOf("bash", "-c", "grep -Eq '^allow-external-apps[[:space:]]*=[[:space:]]*true' \"\$HOME/.termux/termux.properties\" && echo yes || echo no"))
                        add("allow_external_apps", "pf.allow_external_apps", props.stdout.trim() == "yes", if (props.stdout.trim() != "yes") "setze allow-external-apps = true in ~/.termux/termux.properties" else "")
                        add("storage", "pf.storage", true, "Termux braucht Storage-Zugriff fuer /storage/emulated/0; Akku-Optimierung abschalten", optional = true)
                    }
                    val okAll = (0 until checks.length()).all { checks.getJSONObject(it).getBoolean("ok") || checks.getJSONObject(it).getBoolean("optional") }
                    return JSONObject().put("backend", backend.name).put("ok", okAll).put("checks", checks).toString()
    }

}
