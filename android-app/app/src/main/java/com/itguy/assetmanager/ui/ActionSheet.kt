package com.itguy.assetmanager.ui

import android.content.Context
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import com.itguy.assetmanager.R

/**
 * The rows a "what would you like to do with this?" sheet is made of.
 *
 * The asset sheet was a column of emoji and text with nothing else to it:
 * 🗑️ beside ✍️ beside 📄, each one a different size and a different era of
 * Unicode, none of them matching an icon anywhere else in the app. These are
 * the app's own outline icons in the app's own tint, on rows the same height
 * as the rows in every list.
 *
 * It lives here rather than inside the asset sheet because the same menu is
 * the right menu for a contract, a person or a ticket, and the second one
 * should not have to reinvent it.
 */
object ActionSheet {

    /** A destructive row is the one you do not want to tap by accident. */
    class Row(
        val label: String,
        val icon: Int,
        val destructive: Boolean = false,
        val onTap: () -> Unit,
    )

    private fun px(ctx: Context, v: Float) = (v * ctx.resources.displayMetrics.density).toInt()

    /** The sheet's own heading: what you long-pressed. */
    fun header(ctx: Context, title: String, subtitle: String?): LinearLayout {
        val block = LinearLayout(ctx).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(px(ctx, 22f), px(ctx, 18f), px(ctx, 22f), px(ctx, 14f))
        }
        block.addView(TextView(ctx).apply {
            text = title
            textSize = 16.5f
            maxLines = 2
            ellipsize = android.text.TextUtils.TruncateAt.END
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            setTextColor(ContextCompat.getColor(ctx, R.color.text_strong))
        })
        if (!subtitle.isNullOrBlank()) {
            block.addView(TextView(ctx).apply {
                text = subtitle
                textSize = 12.5f
                maxLines = 1
                ellipsize = android.text.TextUtils.TruncateAt.END
                setTextColor(ContextCompat.getColor(ctx, R.color.text_soft))
                setPadding(0, px(ctx, 3f), 0, 0)
            })
        }
        return block
    }

    fun divider(ctx: Context) = android.view.View(ctx).apply {
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, px(ctx, 1f)
        ).also {
            it.leftMargin = px(ctx, 22f)
            it.rightMargin = px(ctx, 22f)
            it.topMargin = px(ctx, 4f)
            it.bottomMargin = px(ctx, 4f)
        }
        setBackgroundColor(ContextCompat.getColor(ctx, R.color.divider))
    }

    /**
     * One action, as a row: the icon, the words, and a tap target the whole
     * width of the sheet.
     */
    fun row(ctx: Context, r: Row): LinearLayout {
        val ink = ContextCompat.getColor(
            ctx, if (r.destructive) R.color.stat_red else R.color.text_strong)
        val tint = ContextCompat.getColor(
            ctx, if (r.destructive) R.color.stat_red else R.color.text_soft)

        return LinearLayout(ctx).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            isClickable = true
            isFocusable = true
            // the same pill that marks the row you are on in the drawer, so a
            // press feels like the rest of the app
            background = rowBackground(ctx)
            setPadding(px(ctx, 22f), px(ctx, 14f), px(ctx, 22f), px(ctx, 14f))
            setOnClickListener { r.onTap() }

            addView(ImageView(ctx).apply {
                setImageResource(r.icon)
                imageTintList = android.content.res.ColorStateList.valueOf(tint)
                layoutParams = LinearLayout.LayoutParams(px(ctx, 22f), px(ctx, 22f))
                    .also { it.rightMargin = px(ctx, 18f) }
            })
            addView(TextView(ctx).apply {
                text = r.label
                textSize = 15.5f
                setTextColor(ink)
                layoutParams = LinearLayout.LayoutParams(
                    0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            })
        }
    }

    private fun rowBackground(ctx: Context) =
        android.graphics.drawable.StateListDrawable().apply {
            val pressed = GradientDrawable().apply {
                cornerRadius = px(ctx, 14f).toFloat()
                setColor(ContextCompat.getColor(ctx, R.color.chip_idle))
            }
            addState(intArrayOf(android.R.attr.state_pressed), pressed)
            addState(intArrayOf(), android.graphics.drawable.ColorDrawable(
                android.graphics.Color.TRANSPARENT))
        }
}
