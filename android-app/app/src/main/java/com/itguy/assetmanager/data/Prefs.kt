package com.itguy.assetmanager.data

import android.content.Context
import android.content.SharedPreferences
import androidx.appcompat.app.AppCompatDelegate
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * Persistent, encrypted on-device storage for the server address and the
 * user's API key. Once these are set the app stays logged in indefinitely
 * (like Nextcloud's app-password model) -- every request just carries the
 * key, no session cookie / re-login involved.
 */
object Prefs {
    private const val FILE = "itguy_assets_secure_prefs"
    private lateinit var prefs: SharedPreferences

    fun init(context: Context) {
        if (::prefs.isInitialized) return
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        prefs = EncryptedSharedPreferences.create(
            context, FILE, masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    }

    var serverUrl: String
        get() = prefs.getString("server_url", "") ?: ""
        set(v) = prefs.edit().putString("server_url", v).apply()

    var apiKey: String
        get() = prefs.getString("api_key", "") ?: ""
        set(v) = prefs.edit().putString("api_key", v).apply()

    var username: String
        get() = prefs.getString("username", "") ?: ""
        set(v) = prefs.edit().putString("username", v).apply()

    var role: String
        get() = prefs.getString("role", "") ?: ""
        set(v) = prefs.edit().putString("role", v).apply()

    var displayName: String
        get() = prefs.getString("display_name", "") ?: ""
        set(v) = prefs.edit().putString("display_name", v).apply()

    val isLoggedIn: Boolean
        get() = serverUrl.isNotBlank() && apiKey.isNotBlank()

    /** Branding pulled from the server after login, so the app wears the
     *  deployment's own name/logo instead of the bundled IT-Vault defaults. */
    var brandName: String
        get() = prefs.getString("brand_name", "") ?: ""
        set(v) = prefs.edit().putString("brand_name", v).apply()

    /**
     * The deployment's theme, cached as the raw hex the server reports.
     *
     * Cached rather than fetched on demand for one reason: it has to be
     * readable *before the first frame is drawn*. Waiting on /api/branding
     * means the app paints in the bundled red and then snaps to the real
     * colours a moment later, which is the flicker. Read from disk, the
     * palette is already right by the time anything is inflated.
     *
     * Blank means "never fetched" -- the bundled palette is used, which is
     * also what a fresh install shows until its first successful refresh.
     */
    var brandAccent: String
        get() = prefs.getString("brand_accent", "") ?: ""
        set(v) = prefs.edit().putString("brand_accent", v).apply()

    var brandAccent2: String
        get() = prefs.getString("brand_accent2", "") ?: ""
        set(v) = prefs.edit().putString("brand_accent2", v).apply()

    /** Page background. May be a single hex or a gradient's first colour. */
    var brandBg: String
        get() = prefs.getString("brand_bg", "") ?: ""
        set(v) = prefs.edit().putString("brand_bg", v).apply()

    /** Card / component background. */
    var brandSurface: String
        get() = prefs.getString("brand_surface", "") ?: ""
        set(v) = prefs.edit().putString("brand_surface", v).apply()

    /** Corner radius in dp, as configured on the server. 0 means unset. */
    var brandRadius: Int
        get() = prefs.getInt("brand_radius", 0)
        set(v) = prefs.edit().putInt("brand_radius", v).apply()

    /** Epoch millis of the last silent in-app update check (throttled to once a day). */
    var lastUpdateCheck: Long
        get() = prefs.getLong("last_update_check", 0L)
        set(v) = prefs.edit().putLong("last_update_check", v).apply()

    /** A versionCode the user chose to "Skip" so the launch prompt won't nag about it again. */
    var skippedUpdateCode: Long
        get() = prefs.getLong("skipped_update_code", 0L)
        set(v) = prefs.edit().putLong("skipped_update_code", v).apply()

    /** "system" (default, follows the device setting), "light", or "dark". */
    var themeMode: String
        get() = prefs.getString("theme_mode", "system") ?: "system"
        set(v) {
            prefs.edit().putString("theme_mode", v).apply()
            applyThemeMode()
        }

    /** Call once at the top of every entry-point Activity's onCreate, before
     * super.onCreate() -- AppCompatDelegate needs to know the mode before the
     * theme is resolved for this Activity's window. */
    fun applyThemeMode() {
        AppCompatDelegate.setDefaultNightMode(
            when (themeMode) {
                "light" -> AppCompatDelegate.MODE_NIGHT_NO
                "dark" -> AppCompatDelegate.MODE_NIGHT_YES
                else -> AppCompatDelegate.MODE_NIGHT_FOLLOW_SYSTEM
            }
        )
    }

    fun clear() {
        prefs.edit().clear().apply()
    }
}
