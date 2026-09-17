package com.itguy.assetmanager.ui

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import androidx.core.content.pm.ShortcutInfoCompat
import androidx.core.content.pm.ShortcutManagerCompat
import androidx.core.graphics.drawable.IconCompat
import com.itguy.assetmanager.data.Branding
import com.itguy.assetmanager.data.Prefs
import com.itguy.assetmanager.ui.login.LoginActivity

/**
 * Which launcher icon the phone shows, and a branded shortcut beside it.
 *
 * The thing people ask for -- "make the app icon our logo" -- is the one
 * Android does not allow. The launcher icon is a resource compiled into the
 * APK; nothing at runtime can replace it with a PNG fetched from a server, and
 * no setting on the server can either. Two things are possible, and between
 * them they cover the intent:
 *
 * **Switch between icons the APK already contains.** That is what the
 * activity-aliases in the manifest are for: same app, same activity, three
 * tiles. [apply] enables one and disables the rest.
 *
 * **Pin a home-screen shortcut carrying the server's own logo.** A shortcut
 * icon *is* just a bitmap, so this one really can be the customer's mark --
 * see [pinBrandedShortcut]. It sits next to the app icon rather than replacing
 * it, which is the honest version of the request.
 */
object AppIcon {

    /** The three tiles the APK ships, in the order Settings lists them. */
    enum class Variant(val component: String, val label: String) {
        DEFAULT("com.itguy.assetmanager.ui.login.LoginActivity", "Shield"),
        LIGHT("com.itguy.assetmanager.ui.LauncherLight", "Light"),
        MONO("com.itguy.assetmanager.ui.LauncherMono", "Mono"),
    }

    /** What is enabled right now, according to the package manager. */
    fun current(ctx: Context): Variant {
        val pm = ctx.packageManager
        for (v in Variant.entries) {
            val state = pm.getComponentEnabledSetting(ComponentName(ctx.packageName, v.component))
            if (state == PackageManager.COMPONENT_ENABLED_STATE_ENABLED) return v
        }
        // nothing explicitly enabled means nothing has been changed yet, and
        // the manifest's own default is the activity
        return Variant.DEFAULT
    }

    /**
     * Make [want] the launcher icon.
     *
     * Order matters: enable the new one before disabling the old. Do it the
     * other way round and there is a moment with no enabled LAUNCHER
     * component at all, which some launchers notice and respond to by dropping
     * the app off the home screen until the next reboot.
     */
    fun apply(ctx: Context, want: Variant) {
        val pm = ctx.packageManager
        pm.setComponentEnabledSetting(
            ComponentName(ctx.packageName, want.component),
            PackageManager.COMPONENT_ENABLED_STATE_ENABLED,
            PackageManager.DONT_KILL_APP,
        )
        for (other in Variant.entries) {
            if (other == want) continue
            pm.setComponentEnabledSetting(
                ComponentName(ctx.packageName, other.component),
                PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
                PackageManager.DONT_KILL_APP,
            )
        }
        Prefs.appIcon = want.name
    }

    /** Whether this launcher will accept a pinned shortcut at all. */
    fun canPin(ctx: Context): Boolean = ShortcutManagerCompat.isRequestPinShortcutSupported(ctx)

    /**
     * Offer to pin a home-screen shortcut using the server's logo.
     *
     * This is the one place the customer's own mark can become an icon on the
     * home screen, because a shortcut's icon is a bitmap rather than a
     * compiled resource. Returns false when there is no cached logo to use --
     * which means the app has not talked to the server yet, and the honest
     * answer is to say so rather than pin the shield and call it branding.
     */
    fun pinBrandedShortcut(ctx: Context): Boolean {
        val logo: Bitmap = Branding.logo(ctx) ?: return false
        if (!canPin(ctx)) return false
        val label = Prefs.brandName.ifBlank { "IT-Vault" }
        val intent = Intent(ctx, LoginActivity::class.java).apply {
            action = Intent.ACTION_MAIN
            addCategory(Intent.CATEGORY_LAUNCHER)
        }
        val shortcut = ShortcutInfoCompat.Builder(ctx, "branded-home")
            .setShortLabel(label.take(12))
            .setLongLabel(label.take(40))
            .setIcon(IconCompat.createWithAdaptiveBitmap(logo))
            .setIntent(intent)
            .build()
        return ShortcutManagerCompat.requestPinShortcut(ctx, shortcut, null)
    }
}
