package com.itguy.assetmanager.ui.update

import android.app.Activity
import androidx.appcompat.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.FileProvider
import androidx.core.content.pm.PackageInfoCompat
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.lifecycleScope
import com.google.gson.Gson
import com.itguy.assetmanager.R
import com.itguy.assetmanager.data.Palette
import com.itguy.assetmanager.data.Prefs
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * Self-hosted in-app updater — no Play Store involved.
 *
 * On launch (once a day) and on demand from Settings, the app fetches a tiny
 * JSON manifest published on the IT-Vault GitHub Pages site. If it advertises a
 * higher versionCode than the installed one, the user is offered a one-tap
 * "Update now" that downloads the signed APK from GitHub Releases and launches
 * the system installer.
 *
 * The new APK must be signed with the SAME release key as the installed build,
 * otherwise Android refuses the in-place update.
 */
object AppUpdater {

    // Update manifest, served over HTTPS. The Pages copy is CDN-cached and fast, but it
    // can lag a fresh publish, so fall back to the same file straight from the repo.
    private val MANIFEST_URLS = listOf(
        "https://shatheitguy.github.io/it-vault/app/latest.json",
        "https://raw.githubusercontent.com/shatheitguy/it-vault/main-fresh/docs/app/latest.json"
    )

    // How often the silent launch check runs.
    private const val CHECK_INTERVAL_MS = 24L * 60 * 60 * 1000  // once per day

    private val http by lazy {
        OkHttpClient.Builder()
            .connectTimeout(8, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .build()
    }
    private val gson = Gson()

    data class Manifest(
        val versionCode: Long = 0,
        val versionName: String = "",
        val apkUrl: String = "",
        val notes: String = ""
    )

    fun currentVersionCode(ctx: Context): Long = runCatching {
        PackageInfoCompat.getLongVersionCode(ctx.packageManager.getPackageInfo(ctx.packageName, 0))
    }.getOrDefault(0L)

    fun currentVersionName(ctx: Context): String = runCatching {
        ctx.packageManager.getPackageInfo(ctx.packageName, 0).versionName ?: ""
    }.getOrDefault("")

    /** Last failure reason, so the UI can say something truer than "check your connection". */
    @Volatile private var lastError: String? = null

    private suspend fun fetch(): Manifest? = withContext(Dispatchers.IO) {
        lastError = null
        for (url in MANIFEST_URLS) {
            val result = runCatching {
                http.newCall(Request.Builder().url(url).build()).execute().use { resp ->
                    if (!resp.isSuccessful) {
                        lastError = "update server returned HTTP ${resp.code}"
                        return@use null
                    }
                    val body = resp.body?.string()?.takeIf { it.isNotBlank() }
                    if (body == null) {
                        lastError = "empty response from the update server"
                        return@use null
                    }
                    gson.fromJson(body, Manifest::class.java)
                }
            }
            val m = result.getOrElse { e ->
                lastError = e.message ?: "network error"
                null
            }
            // A manifest is only usable if it actually carries a version.
            if (m != null && m.versionCode > 0) return@withContext m
            if (m != null) lastError = "update manifest was malformed"
        }
        null
    }

    /** Silent daily check on launch; prompts only for a newer, non-skipped version. */
    fun checkOnLaunch(activity: Activity) {
        val owner = activity as? LifecycleOwner ?: return
        val now = System.currentTimeMillis()
        if (now - Prefs.lastUpdateCheck < CHECK_INTERVAL_MS) return
        Prefs.lastUpdateCheck = now
        owner.lifecycleScope.launch {
            val m = fetch() ?: return@launch
            if (m.versionCode > currentVersionCode(activity) && m.versionCode != Prefs.skippedUpdateCode) {
                if (!activity.isFinishing) showUpdateDialog(activity, m, manual = false)
            }
        }
    }

    /** User-triggered "Check for updates" — always reports a result via [onResult]. */
    fun checkManual(activity: Activity, onResult: (String) -> Unit) {
        val owner = activity as? LifecycleOwner ?: return
        owner.lifecycleScope.launch {
            val m = fetch()
            when {
                m == null ->
                    onResult("Couldn't check for updates (${lastError ?: "no response"}). Try again in a moment.")
                m.versionCode > currentVersionCode(activity) -> {
                    onResult("Update available: v${m.versionName}")
                    if (!activity.isFinishing) showUpdateDialog(activity, m, manual = true)
                }
                else ->
                    onResult("You're on the latest version (v${currentVersionName(activity)}).")
            }
        }
    }

    private fun showUpdateDialog(activity: Activity, m: Manifest, manual: Boolean) {
        val msg = buildString {
            append("A new version of IT-Vault is available.\n\n")
            append("Installed: v${currentVersionName(activity)}\n")
            append("New: v${m.versionName}")
            if (m.notes.isNotBlank()) append("\n\n${m.notes}")
        }
        val dlg = com.itguy.assetmanager.ui.BrandDialog(activity)
            .setTitle("Update available")
            .setMessage(msg)
            .setPositiveButton("Update now") { _, _ -> startDownload(activity, m) }
            .setNegativeButton("Later", null)
        // Only offer "skip" for the automatic prompt, never for a manual check.
        if (!manual) {
            dlg.setNeutralButton("Skip this version") { _, _ -> Prefs.skippedUpdateCode = m.versionCode }
        }
        dlg.show()
    }

    private fun startDownload(activity: Activity, m: Manifest) {
        if (m.apkUrl.isBlank()) return
        val owner = activity as? LifecycleOwner ?: return

        // A ring rather than a bar: an APK over a slow link takes long enough
        // that a 4dp line creeping across a dialog reads as a frozen app. It
        // is the same ring the dashboard draws, so the one piece of the app
        // that appears while you wait still looks like the app.
        val d = activity.resources.displayMetrics.density
        fun px(v: Float) = (v * d).toInt()
        val accent = Palette.serverColours()?.accent
            ?: activity.resources.getColor(R.color.accent, null)

        val ring = com.itguy.assetmanager.ui.RingView(activity).apply {
            layoutParams = LinearLayout.LayoutParams(px(132f), px(132f)).also {
                it.gravity = android.view.Gravity.CENTER_HORIZONTAL
            }
            setColors(accent, (accent and 0x00FFFFFF) or 0x33000000,
                      activity.resources.getColor(R.color.text_strong, null))
            centerText = "0%"
        }
        val label = TextView(activity).apply {
            text = "Downloading the update…"
            textSize = 15f
            gravity = android.view.Gravity.CENTER
            setTextColor(activity.resources.getColor(R.color.text_strong, null))
            setPadding(0, px(18f), 0, 0)
        }
        val sub = TextView(activity).apply {
            textSize = 12.5f
            gravity = android.view.Gravity.CENTER
            setTextColor(activity.resources.getColor(R.color.text_soft, null))
            setPadding(0, px(4f), 0, 0)
        }
        val container = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            gravity = android.view.Gravity.CENTER_HORIZONTAL
            setPadding(px(24f), px(26f), px(24f), px(10f))
            addView(ring); addView(label); addView(sub)
        }
        val progressDlg = com.itguy.assetmanager.ui.BrandDialog(activity)
            .setView(container)
            .setCancelable(false)
            .create()
        progressDlg.show()

        // the arc eases toward each reported figure rather than stepping, so
        // a burst of chunks reads as one smooth sweep
        var shown = 0f
        var sweep: android.animation.ValueAnimator? = null

        owner.lifecycleScope.launch {
            val file = runCatching {
                download(activity, m.apkUrl) { read, total ->
                    val target = if (total > 0) (read.toFloat() / total) else 0f
                    activity.runOnUiThread {
                        sweep?.cancel()
                        sweep = android.animation.ValueAnimator.ofFloat(shown, target).apply {
                            duration = 220
                            addUpdateListener { a ->
                                shown = a.animatedValue as Float
                                ring.progress = shown
                                ring.centerText = "${Math.round(shown * 100)}%"
                            }
                            start()
                        }
                        sub.text = if (total > 0) "${mb(read)} of ${mb(total)}" else mb(read)
                    }
                }
            }.getOrNull()
            sweep?.cancel()
            runCatching { progressDlg.dismiss() }
            if (file == null) {
                if (!activity.isFinishing) com.itguy.assetmanager.ui.BrandDialog(activity)
                    .setTitle("Download failed")
                    .setMessage("Couldn't download the update. Please try again in a moment.")
                    .setPositiveButton("OK", null).show()
                return@launch
            }
            install(activity, file)
        }
    }

    /** "12.4 MB", so the counter needs no decoding. */
    private fun mb(bytes: Long): String = "%.1f MB".format(bytes / 1_048_576.0)

    private suspend fun download(
        ctx: Context, url: String, onProgress: (Long, Long) -> Unit,
    ): File =
        withContext(Dispatchers.IO) {
            val dir = File(ctx.cacheDir, "downloads").apply { mkdirs() }
            val out = File(dir, "it-vault-update.apk")
            if (out.exists()) out.delete()
            http.newCall(Request.Builder().url(url).build()).execute().use { resp ->
                if (!resp.isSuccessful) error("HTTP ${resp.code}")
                val body = resp.body ?: error("empty response")
                val total = body.contentLength()
                body.byteStream().use { input ->
                    out.outputStream().use { output ->
                        val buf = ByteArray(16 * 1024)
                        var read = 0L
                        var n: Int
                        while (input.read(buf).also { n = it } >= 0) {
                            output.write(buf, 0, n)
                            read += n
                            onProgress(read, total)
                        }
                    }
                }
            }
            out
        }

    private fun install(ctx: Context, file: File) {
        // Android 8+: the app must be permitted to install packages first.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !ctx.packageManager.canRequestPackageInstalls()) {
            runCatching {
                ctx.startActivity(
                    Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${ctx.packageName}"))
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                )
            }
            (ctx as? Activity)?.let {
                if (!it.isFinishing) com.itguy.assetmanager.ui.BrandDialog(it)
                    .setTitle("Allow installs")
                    .setMessage("Turn on \"Allow from this source\" for IT-Vault, then tap Update again to finish.")
                    .setPositiveButton("OK", null).show()
            }
            return
        }
        val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.fileprovider", file)
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        runCatching { ctx.startActivity(intent) }
    }
}
