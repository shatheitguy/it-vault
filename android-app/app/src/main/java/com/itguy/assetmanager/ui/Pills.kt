package com.itguy.assetmanager.ui

import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.widget.TextView
import com.itguy.assetmanager.R
import com.itguy.assetmanager.data.Palette

/**
 * The chosen-one-of-several pill, painted by hand.
 *
 * Three screens draw the same control -- the theme choice in Settings, Active
 * and Closed on the ticket list, the type filters on the contract list -- and
 * all three need it filled in the install's own accent when it is the one
 * selected. That cannot be a state-list drawable, because the palette walker
 * repaints flat colours and leaves drawables alone, so each screen was going
 * to grow its own copy of this. One copy, here.
 */
object Pills {

    /**
     * Fills [pill] for [on], and puts its padding back.
     *
     * Handing a view a new background is enough to lose its padding, which is
     * how a pill ends up as tight as its own text.
     */
    fun paint(pill: TextView, on: Boolean) {
        val res = pill.resources
        val p = Palette.serverColours()
        val accent = p?.accent ?: res.getColor(R.color.accent, null)
        val onAccent = p?.onAccent ?: res.getColor(R.color.on_accent, null)
        val idle = res.getColor(R.color.chip_idle, null)
        val idleText = res.getColor(R.color.chip_idle_text, null)

        val l = pill.paddingLeft
        val t = pill.paddingTop
        val r = pill.paddingRight
        val b = pill.paddingBottom
        pill.background = GradientDrawable().apply {
            cornerRadius = 100f
            setColor(if (on) accent else idle)
        }
        pill.setPadding(l, t, r, b)
        pill.setTextColor(if (on) onAccent else idleText)
        pill.setTypeface(Typeface.DEFAULT, if (on) Typeface.BOLD else Typeface.NORMAL)
    }

    /** Paints a whole row at once: the one at [chosen] is on, the rest off. */
    fun paintRow(pills: List<TextView>, chosen: Int) {
        pills.forEachIndexed { i, pill -> paint(pill, i == chosen) }
    }
}
