package com.itguy.assetmanager.data

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities

/**
 * Instant online/offline check so list screens can skip straight to the
 * offline cache instead of waiting out a full HTTP connect timeout (which is
 * what made "offline mode" feel broken/frozen before this existed).
 */
object NetworkUtils {
    fun isOnline(context: Context): Boolean {
        val cm = context.applicationContext.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
            ?: return true
        val network = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(network) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    /** "just now" / "5 min ago" / "3h ago" -- for the offline-cache banner. */
    fun timeAgo(millis: Long): String {
        if (millis <= 0L) return "unknown"
        val diff = (System.currentTimeMillis() - millis) / 1000
        return when {
            diff < 60 -> "just now"
            diff < 3600 -> "${diff / 60}m ago"
            diff < 86400 -> "${diff / 3600}h ago"
            else -> "${diff / 86400}d ago"
        }
    }
}
