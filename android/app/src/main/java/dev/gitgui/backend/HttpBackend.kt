package dev.gitgui.backend

import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

class HttpBackend(private val baseUrl: String, private val token: String? = null) : Backend {
    override val name = "http"

    private fun call(method: String, path: String, body: JSONObject? = null): JSONObject {
        val url = URL(baseUrl.trimEnd('/') + path + if (token != null) "?token=$token" else "")
        val conn = url.openConnection() as HttpURLConnection
        conn.requestMethod = method
        conn.connectTimeout = 15000
        conn.readTimeout = 300000
        if (token != null) conn.setRequestProperty("Authorization", "Bearer $token")
        if (body != null) {
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json")
            OutputStreamWriter(conn.outputStream).use { it.write(body.toString()) }
        }
        val code = conn.responseCode
        val text = (if (code < 400) conn.inputStream else conn.errorStream)?.bufferedReader()?.readText() ?: "{}"
        return JSONObject(text)
    }

    override fun run(repo: String?, args: List<String>, timeoutSec: Int): ExecResult {
        val r = call("POST", "/api/exec", JSONObject().put("repo", repo).put("args", args).put("timeout", timeoutSec))
        return ExecResult(r.optInt("exit_code", 1), r.optString("stdout"), r.optString("stderr"))
    }

    override fun complete(repo: String?, words: List<String>, cword: Int): Map<String, Any?> {
        val r = call("POST", "/api/complete", JSONObject().put("repo", repo).put("words", words).put("cword", cword))
        val arr = r.optJSONArray("candidates")
        val n = arr?.length() ?: 0
        val cands = (0 until n).map { i -> arr!!.getString(i) }
        return mapOf(
            "candidates" to cands,
            "common_prefix" to r.optString("common_prefix"),
            "source" to r.optString("source"),
        )
    }

    override fun man(cmd: String, repo: String?): Map<String, Any?> {
        val r = call("GET", "/api/man?cmd=$cmd&repo=${repo ?: ""}")
        return mapOf("cmd" to cmd, "source" to r.optString("source"), "text" to r.optString("text"))
    }

    override fun shortHelp(cmd: String, repo: String?): String {
        return call("GET", "/api/help?cmd=$cmd&repo=${repo ?: ""}").optString("text")
    }

    override fun helpA(repo: String?): String {
        val r = call("POST", "/api/commands", JSONObject().put("repo", repo))
        return r.toString()
    }

    override fun listDirs(path: String?): Map<String, Any?> {
        val r = call("POST", "/api/fs/list", JSONObject().put("path", path ?: ""))
        val arr = r.optJSONArray("dirs")
        val n = arr?.length() ?: 0
        val dirs = (0 until n).map { i -> arr!!.getString(i) }
        return mapOf(
            "path" to r.optString("path"),
            "parent" to r.optString("parent"),
            "dirs" to dirs,
        )
    }
}
