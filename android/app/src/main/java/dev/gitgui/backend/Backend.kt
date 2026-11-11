package dev.gitgui.backend

data class ExecResult(val exitCode: Int, val stdout: String, val stderr: String)

interface Backend {
    val name: String
    fun run(repo: String?, args: List<String>, timeoutSec: Int = 60): ExecResult
    fun complete(repo: String?, words: List<String>, cword: Int): Map<String, Any?>
    fun man(cmd: String, repo: String?): Map<String, Any?>
    fun shortHelp(cmd: String, repo: String?): String
    fun helpA(repo: String?): String
    fun listDirs(path: String?): Map<String, Any?>
}
