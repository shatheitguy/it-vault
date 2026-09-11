package com.itguy.assetmanager.data

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.widget.ImageView
import android.widget.TextView
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * Per-deployment branding.
 *
 * IT-Vault is self-hosted and each install can set its own app name and upload
 * its own logo, so the app shouldn't sit on the bundled "IT-Vault" defaults once
 * it's pointed at a server. After login (and on every launch) we pull
 * `/api/branding` for the name and cache `/logo.png` on disk, then apply both
 * wherever the app shows its identity.
 */
object Branding {

    private const val LOGO_FILE = "server_logo.png"

    private val http by lazy {
        OkHttpClient.Builder()
            .connectTimeout(6, TimeUnit.SECONDS)
            .readTimeout(15, TimeUnit.SECONDS)
            .build()
    }

    /** The name to display: the server's, falling back to the bundled app name. */
    fun name(ctx: Context): String =
        Prefs.brandName.ifBlank { ctx.getString(com.itguy.assetmanager.R.string.app_name) }

    private fun logoFile(ctx: Context) = File(ctx.filesDir, LOGO_FILE)

    /** Cached server logo, or null if we've never successfully fetched one. */
    fun logo(ctx: Context): Bitmap? {
        val f = logoFile(ctx)
        if (!f.exists() || f.length() == 0L) return null
        return runCatching { BitmapFactory.decodeFile(f.absolutePath) }.getOrNull()
    }

    /**
     * Pulls the name from /api/branding and the image from /logo.png.
     * Safe to call often — failures are swallowed and the cache is kept.
     */
    suspend fun refresh(ctx: Context) = withContext(Dispatchers.IO) {
        // ---- name ----
        runCatching {
            val resp = ApiClient.api().branding()
            val body = resp.body()
            if (resp.isSuccessful && body != null) {
                val name = (body["app_name"] as? String)?.trim()
                    ?: (body["logo_text"] as? String)?.trim()
                if (!name.isNullOrBlank()) Prefs.brandName = name
            }
        }

        // ---- logo ----
        runCatching {
            val base = Prefs.serverUrl
            if (base.isBlank()) return@runCatching
            val url = ApiClient.normalize(base) + "logo.png"
            http.newCall(Request.Builder().url(url).build()).execute().use { resp ->
                if (!resp.isSuccessful) return@use
                val bytes = resp.body?.bytes() ?: return@use
                // Only overwrite the cache when we actually decoded an image.
                if (bytes.isNotEmpty() &&
                    BitmapFactory.decodeByteArray(bytes, 0, bytes.size) != null
                ) {
                    logoFile(ctx).writeBytes(bytes)
                }
            }
        }
        Unit
    }

    /** Applies the cached branding to a name label and/or logo view. */
    fun apply(ctx: Context, nameView: TextView?, logoView: ImageView?) {
        nameView?.text = name(ctx)
        logo(ctx)?.let { logoView?.setImageBitmap(it) }
    }

    /** Clears cached branding — called when the user switches server / logs out. */
    fun clear(ctx: Context) {
        Prefs.brandName = ""
        runCatching { logoFile(ctx).delete() }
    }
}
