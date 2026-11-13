package dev.gitgui

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.provider.DocumentsContract
import org.json.JSONObject
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import dev.gitgui.backend.Backend
import dev.gitgui.backend.HttpBackend
import dev.gitgui.backend.TermuxBackend
import org.json.JSONObject

class MainActivity : Activity() {

    private lateinit var webView: WebView
    private lateinit var backend: Backend

    @SuppressLint("SetJavaScriptEnabled", "AddJavascriptInterface")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        backend = if (intent?.getStringExtra("backend") == "http") {
            HttpBackend(
                intent.getStringExtra("server") ?: "http://127.0.0.1:8765",
                intent.getStringExtra("token")
            )
        } else {
            TermuxBackend(this)
        }
        webView = WebView(this)
        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.addJavascriptInterface(Bridge(), "GitguiBridge")
        browseSysBtnVisibility()
        setContentView(webView)
        webView.webViewClient = object : WebViewClient() {
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
                if (request.url.host != "gitgui.local" || request.method != "GET") return null
                val path = request.url.path ?: "/"
                if (path.startsWith("/api/")) return null
                return try {
                    val assetPath = "gui" + (if (path == "/") "/index.html" else path)
                    val mime = when {
                        assetPath.endsWith(".html") -> "text/html"
                        assetPath.endsWith(".js") -> "text/javascript"
                        assetPath.endsWith(".css") -> "text/css"
                        assetPath.endsWith(".json") -> "application/json"
                        else -> "application/octet-stream"
                    }
                    WebResourceResponse(mime, "utf-8", assets.open(assetPath))
                } catch (e: Exception) {
                    WebResourceResponse("text/plain", "utf-8", e.message?.byteInputStream() ?: ByteArray(0).inputStream())
                }
            }
        }
        webView.loadUrl("http://gitgui.local/")
    }

    private fun browseSysBtnVisibility() {
        webView.post {
            webView.evaluateJavascript(
                "var b=document.getElementById('browse-sys'); if(b){ if(window.GitguiBridge && GitguiBridge.pickDir) b.style.display=''; else b.style.display='none'; }", null)
        }
    }

    private fun pickDirectory() {
        try {
            startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT_TREE), 4242)
        } catch (e: Exception) {
            webView.post { webView.evaluateJavascript("window.gitguiPicked && window.gitguiPicked(null)", null) }
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode == 4242) {
            var path: String? = null
            if (resultCode == RESULT_OK && data?.data != null) {
                val tree = data.data!!
                try {
                    contentResolver.takePersistableUriPermission(tree,
                        Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
                } catch (e: Exception) { /* ok */ }
                val docId = DocumentsContract.getTreeDocumentId(tree)
                if (docId.startsWith("primary:")) path = "/storage/emulated/0/" + docId.removePrefix("primary:")
            }
            val js = "window.gitguiPicked && window.gitguiPicked(" + JSONObject.quote(path ?: "") + ")"
            webView.post { webView.evaluateJavascript(js, null) }
        }
        super.onActivityResult(requestCode, resultCode, data)
    }

    inner class Bridge {
        @JavascriptInterface fun pickDir() = pickDirectory()

        @JavascriptInterface
        fun call(method: String, path: String, body: String?): String {
            val (code, payload) = ApiRouter.handle(this@MainActivity, backend, method, path, body)
            return JSONObject()
                .put("status", code)
                .put("data", try { JSONObject(payload) } catch (e: Exception) { JSONObject().put("raw", payload) })
                .toString()
        }
    }
}
