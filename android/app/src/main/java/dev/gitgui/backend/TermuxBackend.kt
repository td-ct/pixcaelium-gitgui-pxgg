package dev.gitgui.backend

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.os.Bundle
import android.app.PendingIntent
import java.util.concurrent.CompletableFuture
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

private const val TERMUX_PACKAGE = "com.termux"
private const val RUN_COMMAND_SERVICE = "com.termux.app.RunCommandService"
private const val ACTION_RUN_COMMAND = "com.termux.RUN_COMMAND"
private const val EXTRA_PATH = "com.termux.RUN_COMMAND_PATH"
private const val EXTRA_ARGUMENTS = "com.termux.RUN_COMMAND_ARGUMENTS"
private const val EXTRA_WORKDIR = "com.termux.RUN_COMMAND_WORKDIR"
private const val EXTRA_BACKGROUND = "com.termux.RUN_COMMAND_BACKGROUND"
private const val EXTRA_LABEL = "com.termux.RUN_COMMAND_COMMAND_LABEL"
private const val EXTRA_PENDING_INTENT = "com.termux.RUN_COMMAND_PENDING_INTENT"
private const val EXTRA_RESULT_BUNDLE = "com.termux.service.PLUGIN_RESULT_BUNDLE"
private const val RESULT_STDOUT = "com.termux.service.PLUGIN_RESULT_BUNDLE_STDOUT"
private const val RESULT_STDERR = "com.termux.service.PLUGIN_RESULT_BUNDLE_STDERR"
private const val RESULT_EXIT_CODE = "com.termux.service.PLUGIN_RESULT_BUNDLE_EXIT_CODE"
private const val RESULT_ERR = "com.termux.service.PLUGIN_RESULT_BUNDLE_ERR"
private const val RESULT_ERRMSG = "com.termux.service.PLUGIN_RESULT_BUNDLE_ERRMSG"
private const val PREFIX = "/data/data/com.termux/files/usr"
private const val RECEIVER_ACTION = "dev.gitgui.RUN_COMMAND_RESULT"

class TermuxBackend(private val context: Context) : Backend {
    override val name = "termux"

    private val nextId = AtomicInteger(1)
    private val pending = ConcurrentHashMap<Int, CompletableFuture<Bundle>>()

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(ctx: Context, intent: Intent) {
            val id = intent.getIntExtra("execution_id", -1)
            val bundle = intent.getBundleExtra(EXTRA_RESULT_BUNDLE) ?: Bundle()
            if (id >= 0) pending.remove(id)?.complete(bundle)
        }
    }

    init {
        val filter = IntentFilter(RECEIVER_ACTION)
        if (Build.VERSION.SDK_INT >= 33) {
            context.registerReceiver(receiver, filter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            @Suppress("UnspecifiedRegisterReceiverFlag")
            context.registerReceiver(receiver, filter)
        }
    }

    private fun send(path: String, arguments: Array<String>, workdir: String, label: String, timeoutSec: Int): Bundle {
        val id = nextId.getAndIncrement()
        val resultIntent = Intent(RECEIVER_ACTION).setPackage(context.packageName).putExtra("execution_id", id)
        val flags = PendingIntent.FLAG_ONE_SHOT or
            (if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0)
        val pi = PendingIntent.getBroadcast(context, id, resultIntent, flags)
        val intent = Intent()
            .setClassName(TERMUX_PACKAGE, RUN_COMMAND_SERVICE)
            .setAction(ACTION_RUN_COMMAND)
            .putExtra(EXTRA_PATH, path)
            .putExtra(EXTRA_ARGUMENTS, arguments)
            .putExtra(EXTRA_WORKDIR, workdir)
            .putExtra(EXTRA_BACKGROUND, true)
            .putExtra(EXTRA_LABEL, label)
            .putExtra(EXTRA_PENDING_INTENT, pi)
        val future = CompletableFuture<Bundle>()
        pending[id] = future
        return try {
            context.startService(intent)
            future.get(timeoutSec.toLong(), TimeUnit.SECONDS)
        } catch (e: Exception) {
            Bundle().apply {
                putInt(RESULT_EXIT_CODE, 124)
                putString(RESULT_STDERR, "termux run failed: ${e.message}")
            }
        } finally {
            pending.remove(id)
        }
    }

    override fun run(repo: String?, args: List<String>, timeoutSec: Int, jobId: String?): ExecResult {
        val all = mutableListOf("-c", "core.quotepath=false")
        all.addAll(args)
        val workdir = repo ?: "$PREFIX/home"
        val b = if (jobId != null) {
            send("$PREFIX/bin/bash",
                arrayOf("-c", "exec -a \"\$0\" \"\$@\"", "gitgui-job-$jobId", "git", *all.toTypedArray()),
                workdir, "gitgui: git ${args.firstOrNull() ?: ""}", timeoutSec)
        } else {
            send("$PREFIX/bin/git", all.toTypedArray(), workdir,
                "gitgui: git ${args.firstOrNull() ?: ""}", timeoutSec)
        }
        val err = b.getInt(RESULT_ERR, -1)
        val errmsg = if (err != -1) b.getString(RESULT_ERRMSG) ?: "" else ""
        return ExecResult(
            b.getInt(RESULT_EXIT_CODE, 1),
            b.getString(RESULT_STDOUT) ?: "",
            (b.getString(RESULT_STDERR) ?: "") + errmsg
        )
    }

    override fun raw(args: List<String>, cwd: String?, timeoutSec: Int): ExecResult {
        val path = if (args[0].startsWith("/")) args[0] else "$PREFIX/bin/" + args[0].substringAfterLast('/')
        val b = send(path, args.drop(1).toTypedArray(), cwd ?: "$PREFIX/home", "gitgui: ${args[0]}", timeoutSec)
        return ExecResult(b.getInt(RESULT_EXIT_CODE, 1), b.getString(RESULT_STDOUT) ?: "", b.getString(RESULT_STDERR) ?: "")
    }

    override fun stop(jobId: String): Boolean {
        raw(listOf("pkill", "-TERM", "-f", "gitgui-job-$jobId"), timeoutSec = 15)
        raw(listOf("pkill", "-KILL", "-f", "gitgui-job-$jobId"), timeoutSec = 15)
        return true
    }

    override fun complete(repo: String?, words: List<String>, cword: Int): Map<String, Any?> {
        val arr = words.joinToString(" ") { w -> "'" + w.replace("'", "'\\''") + "'" }
        val script = """
            shopt -s progcomp 2>/dev/null
            COMP_WORDBREAKS=" "
            for f in "$PREFIX/share/bash-completion/completions/git" "$PREFIX/share/git-core/git-completion.bash" /usr/share/bash-completion/completions/git; do
              if [ -f "${'$'}f" ]; then source "${'$'}f" 2>/dev/null; break; fi
            done
            COMP_WORDS=($arr)
            COMP_CWORD=$cword
            COMP_LINE="${words.joinToString(" ")}"
            COMP_POINT=${'$'}{#COMP_LINE}
            words=("${'$'}{COMP_WORDS[@]}")
            cword=${'$'}COMP_CWORD
            cur="${'$'}{words[cword]}"
            prev="${'$'}{words[cword-1]}"
            COMPREPLY=()
            if declare -F __git_main >/dev/null 2>&1; then __git_main 2>/dev/null; fi
            if [ ${'$'}{#COMPREPLY[@]} -gt 0 ]; then printf '%s\0' "${'$'}{COMPREPLY[@]}"; fi
        """.trimIndent()
        val r = run(repo, listOf("-c", script), 30)
        val cands = r.stdout.split("\u0000").map { it.trimEnd(' ') }.filter { it.isNotEmpty() }.take(200)
        val common = if (cands.isEmpty()) "" else cands.reduce { a, b -> a.commonPrefixWith(b) }
        return mapOf("candidates" to cands, "common_prefix" to common, "source" to "termux")
    }

    override fun man(cmd: String, repo: String?): Map<String, Any?> {
        val r = run(repo, listOf("help", cmd), 30)
        val text = r.stdout.ifEmpty { run(repo, listOf(cmd, "-h"), 30).let { it.stdout + it.stderr } }
        return mapOf("cmd" to cmd, "source" to if (r.stdout.isNotEmpty()) "man" else "usage", "text" to text)
    }

    override fun shortHelp(cmd: String, repo: String?): String {
        val r = run(repo, listOf(cmd, "-h"), 30)
        return r.stdout + r.stderr
    }

    override fun helpA(repo: String?): String {
        return run(repo, listOf("help", "-a"), 30).stdout
    }

    override fun listDirs(path: String?): Map<String, Any?> {
        val p = path ?: "$PREFIX/home"
        val r = run(null, listOf("ls", "-1", "-d", "$p/*/"), 30)
        val dirs = r.stdout.lineSequence().map { it.trim().trimEnd('/').substringAfterLast('/') + "/" }.filter { it != "/" }.sorted().take(500).toList()
        return mapOf("path" to p, "parent" to p.trimEnd('/').substringBeforeLast('/', "/"), "dirs" to dirs)
    }
}
