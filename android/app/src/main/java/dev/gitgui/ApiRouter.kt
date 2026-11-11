package dev.gitgui

import android.content.Context
import dev.gitgui.backend.Backend
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
                    val r = backend.run(repo, argList, timeout)
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

                else -> 404 to JSONObject().put("error", "unknown endpoint").toString()
            }
        } catch (e: Exception) {
            500 to JSONObject().put("error", e.message ?: "error").toString()
        }
    }
}
