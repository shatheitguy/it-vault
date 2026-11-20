package com.itguy.assetmanager.ui

import com.itguy.assetmanager.R

/**
 * The icon for an item category -- the same rules, in the same order, and
 * the same drawings (ic_t_*, generated from the web's icon set) as the web
 * asset list, so a laptop is the same laptop on both.
 */
object TypeIcons {
    private val RULES: List<Pair<Regex, Int>> = listOf(
        Regex("laptop|notebook|macbook|chromebook|ultrabook", RegexOption.IGNORE_CASE) to R.drawable.ic_t_laptop,
        Regex("phone|mobile|iphone|android|smartphone|handset", RegexOption.IGNORE_CASE) to R.drawable.ic_t_smartphone,
        Regex("tablet|ipad|\\btab\\b", RegexOption.IGNORE_CASE) to R.drawable.ic_t_tablet,
        Regex("monitor|display|screen|\\btv\\b|television", RegexOption.IGNORE_CASE) to R.drawable.ic_t_monitor,
        Regex("desktop|workstation|\\bpc\\b|computer|all.?in.?one|imac|thin client", RegexOption.IGNORE_CASE) to R.drawable.ic_t_desktop,
        Regex("access.?point|\\bap\\b|wi-?fi|wireless|wlan", RegexOption.IGNORE_CASE) to R.drawable.ic_t_wifi,
        Regex("router|gateway|modem", RegexOption.IGNORE_CASE) to R.drawable.ic_t_router,
        Regex("switch|\\bhub\\b", RegexOption.IGNORE_CASE) to R.drawable.ic_t_switch,
        Regex("firewall|fortigate|\\butm\\b|sophos|palo alto", RegexOption.IGNORE_CASE) to R.drawable.ic_t_shield,
        Regex("server|\\bnas\\b|\\bsan\\b|hypervisor", RegexOption.IGNORE_CASE) to R.drawable.ic_t_server,
        Regex("\\bnvr\\b|\\bdvr\\b|storage|disk|drive|backup", RegexOption.IGNORE_CASE) to R.drawable.ic_t_drive,
        Regex("camera|cctv|webcam|ip cam", RegexOption.IGNORE_CASE) to R.drawable.ic_t_camera,
        Regex("printer|scanner|copier|\\bmfp\\b|plotter", RegexOption.IGNORE_CASE) to R.drawable.ic_t_printer,
        Regex("head(set|phone)|earphone|earbud|speaker|audio", RegexOption.IGNORE_CASE) to R.drawable.ic_t_headphones,
        Regex("\\bups\\b|battery|power|\\bpdu\\b|inverter", RegexOption.IGNORE_CASE) to R.drawable.ic_t_battery,
        Regex("keyboard|mouse|peripheral|dock", RegexOption.IGNORE_CASE) to R.drawable.ic_t_keyboard,
        Regex("projector", RegexOption.IGNORE_CASE) to R.drawable.ic_t_projector,
    )
    private val BY_NAME = mapOf(
        "laptop" to R.drawable.ic_t_laptop, "desktop" to R.drawable.ic_t_desktop, "monitor" to R.drawable.ic_t_monitor,
        "smartphone" to R.drawable.ic_t_smartphone, "tablet" to R.drawable.ic_t_tablet, "router" to R.drawable.ic_t_router,
        "switch" to R.drawable.ic_t_switch, "wifi" to R.drawable.ic_t_wifi, "shield" to R.drawable.ic_t_shield,
        "server" to R.drawable.ic_t_server, "drive" to R.drawable.ic_t_drive, "camera" to R.drawable.ic_t_camera,
        "printer" to R.drawable.ic_t_printer, "headphones" to R.drawable.ic_t_headphones, "battery" to R.drawable.ic_t_battery,
        "keyboard" to R.drawable.ic_t_keyboard, "projector" to R.drawable.ic_t_projector, "box" to R.drawable.ic_t_box,
    )

    /** Category icons picked in the web's Product Catalog, by category name. */
    @Volatile var chosen: Map<String, String> = emptyMap()

    fun forType(type: String?): Int {
        val t = type.orEmpty()
        chosen[t]?.let { BY_NAME[it] }?.let { return it }
        return RULES.firstOrNull { it.first.containsMatchIn(t) }?.second ?: R.drawable.ic_t_box
    }
}
