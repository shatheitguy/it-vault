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
