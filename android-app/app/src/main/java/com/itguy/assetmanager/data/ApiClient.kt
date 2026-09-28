package com.itguy.assetmanager.data

import okhttp3.CookieJar
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

/**
 * Every request is authenticated purely via the X-Api-Key header (see
 * Prefs.apiKey) -- deliberately NOT via cookies, so the client never depends
 * on the web UI's short 5-minute session-cookie lifetime. CookieJar.NO_COOKIES
 * makes sure OkHttp never accidentally starts relying on a session cookie.
 */
object ApiClient {
    private var retrofit: Retrofit? = null
    private var builtForUrl: String? = null

    fun api(): ApiService {
        val base = Prefs.serverUrl.ifBlank { "http://localhost/" }
        if (retrofit == null || builtForUrl != base) {
            retrofit = build(base)
            builtForUrl = base
        }
        return retrofit!!.create(ApiService::class.java)
    }

    /** Used only during the login screen, before an api key exists yet, when we need a session cookie briefly. */
    fun apiWithCookies(base: String): ApiService {
        val client = baseClientBuilder().cookieJar(InMemoryCookieJar()).build()
        return Retrofit.Builder()
            .baseUrl(normalize(base))
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ApiService::class.java)
    }

    private fun build(base: String): Retrofit {
        val client = baseClientBuilder()
            .cookieJar(CookieJar.NO_COOKIES)
            .addInterceptor(authInterceptor())
            .build()
        return Retrofit.Builder()
            .baseUrl(normalize(base))
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
    }

    private fun baseClientBuilder(): OkHttpClient.Builder {
        val logging = HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BASIC }
        return OkHttpClient.Builder()
            .connectTimeout(6, TimeUnit.SECONDS)
            .readTimeout(10, TimeUnit.SECONDS)
            .writeTimeout(10, TimeUnit.SECONDS)
            .addInterceptor(logging)
    }

    private fun authInterceptor() = Interceptor { chain ->
        val req = chain.request().newBuilder()
        if (Prefs.apiKey.isNotBlank()) req.addHeader("X-Api-Key", Prefs.apiKey)
        chain.proceed(req.build())
    }

    /**
     * True when this address would send the API key over plain HTTP to
     * somewhere that is not the local network.
     *
     * Cleartext has to stay possible: IT-Vault is usually a box on the office
     * LAN with no certificate. But the API key is a standing credential for
     * the whole register, and http:// to a public address puts it on the wire
     * for every hop in between. Android's network security config cannot
     * express "private ranges only" -- it takes host names, not CIDR -- so
     * the check is here, where the address the person typed is known.
     */
    fun isPublicCleartext(raw: String): Boolean {
        val url = normalize(raw)
        if (!url.startsWith("http://")) return false
        val host = url.removePrefix("http://").substringBefore('/')
            .substringBefore(':').lowercase()
        if (host == "localhost" || host.endsWith(".local") || host.endsWith(".lan") ||
            host.endsWith(".internal") || host.endsWith(".home")) return false
        val parts = host.split('.')
        val octets = parts.mapNotNull { it.toIntOrNull() }
        if (octets.size == 4 && parts.size == 4) {
            val (a, bb, _, _) = octets
            if (a == 10) return false
            if (a == 127) return false
            if (a == 192 && bb == 168) return false
            if (a == 172 && bb in 16..31) return false
            if (a == 169 && bb == 254) return false
            return true            // a public IPv4 literal
        }
        // a bare hostname with no dots is a LAN name; anything else is public
        return parts.size > 1
    }

    fun normalize(raw: String): String {
        var v = raw.trim()
        if (!v.startsWith("http://") && !v.startsWith("https://")) v = "http://$v"
        return if (v.endsWith("/")) v else "$v/"
    }

    /** Call after login succeeds / server address changes so the next api() call rebuilds with the new base URL. */
    fun reset() {
        retrofit = null
        builtForUrl = null
    }
}

/** Minimal same-process cookie jar -- only needed transiently during the login POST/me() calls. */
private class InMemoryCookieJar : CookieJar {
    private val store = mutableMapOf<String, List<okhttp3.Cookie>>()
    override fun saveFromResponse(url: okhttp3.HttpUrl, cookies: List<okhttp3.Cookie>) {
        store[url.host] = cookies
    }
    override fun loadForRequest(url: okhttp3.HttpUrl): List<okhttp3.Cookie> {
        return store[url.host] ?: emptyList()
    }
}
