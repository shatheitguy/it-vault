package com.itguy.assetmanager.ui

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.LruCache
import android.widget.ImageView
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.Prefs
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.Cache
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * Loads the server's pictures (brand logos, product and asset photos) into
 * ImageViews.
 *
 * They are behind the same sign-in as everything else, so they go through an
 * OkHttp client that adds the X-Api-Key header -- a plain image library would
 * just get 401s. Every picture URL carries ?v=<hash of the picture>, and the
 * server marks them cacheable for a year, so OkHttp's disk cache keeps them
 * across launches and offline; decoded bitmaps are also kept in memory so a
 * scrolling list never decodes the same logo twice.
 */
object Images {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val mem = object : LruCache<String, Bitmap>(
        (Runtime.getRuntime().maxMemory() / 16).toInt().coerceAtLeast(4 * 1024 * 1024)) {
        override fun sizeOf(key: String, value: Bitmap) = value.byteCount
    }
    @Volatile private var client: OkHttpClient? = null

    private fun client(ctx: Context): OkHttpClient = client ?: synchronized(this) {
        client ?: OkHttpClient.Builder()
            .cache(Cache(File(ctx.applicationContext.cacheDir, "pictures"), 40L * 1024 * 1024))
            .connectTimeout(6, TimeUnit.SECONDS)
            .readTimeout(15, TimeUnit.SECONDS)
            .addInterceptor { chain ->
                val r = chain.request().newBuilder()
                if (Prefs.apiKey.isNotBlank()) r.header("X-Api-Key", Prefs.apiKey)
                chain.proceed(r.build())
            }
            .build().also { client = it }
    }

    /**
     * Shows [path] in [view], [maxPx] on its longest side. [onDone] is told
     * whether a picture is now showing, so the caller can fall back to an icon.
     * A recycled row that has moved on to another asset is left alone.
     */
    fun load(view: ImageView, path: String?, maxPx: Int = 256, onDone: (Boolean) -> Unit = {}) {
        if (path.isNullOrBlank()) { view.tag = null; view.setImageDrawable(null); onDone(false); return }
        val url = ApiClient.absolute(path)
        view.tag = url
        mem.get("$url@$maxPx")?.let { view.setImageBitmap(it); onDone(true); return }
        view.setImageDrawable(null)
        val ctx = view.context.applicationContext
        scope.launch {
            val bmp = try {
                client(ctx).newCall(Request.Builder().url(url).build()).execute().use { resp ->
                    if (!resp.isSuccessful) null else resp.body?.bytes()?.let { decode(it, maxPx) }
                }
            } catch (e: Exception) { null }
            if (bmp != null) mem.put("$url@$maxPx", bmp)
            withContext(Dispatchers.Main) {
                if (view.tag != url) return@withContext       // the row shows something else now
                if (bmp != null) view.setImageBitmap(bmp)
                onDone(bmp != null)
            }
        }
    }

    private fun decode(bytes: ByteArray, maxPx: Int): Bitmap? {
        val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, o)
        var sample = 1
        while (o.outWidth / (sample * 2) >= maxPx && o.outHeight / (sample * 2) >= maxPx) sample *= 2
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.size, BitmapFactory.Options().apply { inSampleSize = sample })
    }

    /** Server changed (change of server or sign-out): forget what was shown. */
    fun clear() { mem.evictAll() }
}
