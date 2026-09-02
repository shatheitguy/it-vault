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
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(20, TimeUnit.SECONDS)
            .writeTimeout(20, TimeUnit.SECONDS)
            .addInterceptor(logging)
    }

    private fun authInterceptor() = Interceptor { chain ->
        val req = chain.request().newBuilder()
        if (Prefs.apiKey.isNotBlank()) req.addHeader("X-Api-Key", Prefs.apiKey)
        chain.proceed(req.build())
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
