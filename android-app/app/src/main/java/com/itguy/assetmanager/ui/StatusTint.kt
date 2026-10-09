package com.itguy.assetmanager.ui

import android.graphics.Color

/**
 * One colour per state, for every list in the app.
 *
 * The asset list had its own table of these, which was fine while it was the
 * only list with a coloured pill. Now that a ticket and a contract wear one
 * too, a single table is the only way "Open" and "Available" end up reading
 * as the same kind of green on the same kind of screen.
 *
 * The values are picked for a light surface: the web palette's neon green and
 * pale amber on white make a pill nobody can read, and these pills carry text
 * rather than being a coloured dash. They are left alone in dark mode because
 * a colour chosen to be legible on white is legible on near-black too, and
 * because a status that changes hue with the time of day is a status people
 * stop trusting.
 */
object StatusTint {

    private val GREEN = Color.parseColor("#0F9D63")
    private val BLUE = Color.parseColor("#0E8FB3")
    private val AMBER = Color.parseColor("#B0761A")
    private val RED = Color.parseColor("#D24545")
    private val GREY = Color.parseColor("#6B7280")
    private val NEUTRAL = Color.parseColor("#667085")

    /** The colour for an asset status, a ticket status or a priority. */
    fun of(value: String): Int = when (value.trim()) {
        // assets
        "Available" -> GREEN
        "Checked-Out", "Checked Out" -> BLUE
        "Under-Maintenance", "Under Maintenance" -> AMBER
        "Retired" -> GREY
        "Lost/Stolen" -> RED
        // tickets
        "Open" -> RED
        "In Progress", "In-Progress" -> AMBER
        "Pending" -> BLUE
        "Resolved" -> GREEN
        "Closed" -> GREY
        // priorities
        "Urgent", "Critical", "High" -> RED
        "Normal", "Medium" -> BLUE
        "Low" -> GREY
        else -> NEUTRAL
    }

    /**
     * The colour for "this contract ends in N days".
     *
     * Expired is as loud as it gets, the last week is red, the last month
     * amber, and anything further away is not news.
     */
    fun forDaysLeft(days: Long): Int = when {
        days < 0 -> GREY
        days <= 7 -> RED
        days <= 30 -> AMBER
        else -> GREEN
    }
}
