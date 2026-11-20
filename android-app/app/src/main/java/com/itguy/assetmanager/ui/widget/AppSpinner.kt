package com.itguy.assetmanager.ui.widget

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Typeface
import android.util.AttributeSet
import android.util.TypedValue
import android.view.Gravity
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.widget.AppCompatSpinner
import androidx.core.content.ContextCompat
import com.google.android.material.bottomsheet.BottomSheetDialog
import com.itguy.assetmanager.R
import com.itguy.assetmanager.data.Palette

/**
 * A dropdown that opens the app's own picker instead of Android's popup.
 *
 * The stock Spinner popup is a different thing on every phone -- a floating
 * list on one, a dialog on another, in the system's font and colours either
 * way -- and it never looked like the rest of the app or the web. This is
 * still a Spinner (adapter, selection and listeners all work as before, so
 * no screen's code changes), but a tap brings up a sheet from the bottom in
 * the app's own style: the choices as rows, the current one ticked in the
 * install's accent.
 */
class AppSpinner @JvmOverloads constructor(
    context: Context, attrs: AttributeSet? = null, defStyleAttr: Int = androidx.appcompat.R.attr.spinnerStyle
) : AppCompatSpinner(context, attrs, defStyleAttr, MODE_DROPDOWN) {

    private var sheet: BottomSheetDialog? = null

    override fun performClick(): Boolean {
        val a = adapter ?: return super.performClick()
        if (sheet?.isShowing == true) return true
        val ctx = context
        val dp = { v: Float -> TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, resources.displayMetrics).toInt() }
        val accent = Palette.serverColours()?.accent ?: ContextCompat.getColor(ctx, R.color.accent)
        val textCol = ContextCompat.getColor(ctx, R.color.text_strong)

        val list = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL; setPadding(0, dp(8f), 0, dp(16f)) }
        prompt?.toString()?.takeIf { it.isNotBlank() }?.let { title ->
            list.addView(TextView(ctx).apply {
                text = title
                setTextColor(ContextCompat.getColor(ctx, R.color.text_soft))
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 12.5f)
                isAllCaps = true
                letterSpacing = 0.06f
                setPadding(dp(22f), dp(8f), dp(22f), dp(10f))
            })
        }
        val d = BottomSheetDialog(ctx)
        for (i in 0 until a.count) {
            val label = a.getItem(i)?.toString().orEmpty()
            val selected = i == selectedItemPosition
            val row = FrameLayout(ctx).apply {
                minimumHeight = dp(52f)
                isClickable = true; isFocusable = true
                val ta = ctx.obtainStyledAttributes(intArrayOf(android.R.attr.selectableItemBackground))
                foreground = ta.getDrawable(0); ta.recycle()
                setOnClickListener {
                    d.dismiss()
                    if (i != selectedItemPosition) setSelection(i)
                }
            }
            row.addView(TextView(ctx).apply {
                text = label
                setTextColor(if (selected) accent else textCol)
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 15.5f)
                if (selected) setTypeface(typeface, Typeface.BOLD)
                gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(22f), 0, dp(56f), 0)
            }, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(52f)))
            if (selected) {
                row.addView(ImageView(ctx).apply {
                    setImageResource(R.drawable.ic_check)
                    imageTintList = ColorStateList.valueOf(accent)
                }, FrameLayout.LayoutParams(dp(22f), dp(22f), Gravity.END or Gravity.CENTER_VERTICAL).apply { marginEnd = dp(22f) })
            }
            list.addView(row)
        }
        d.setContentView(ScrollView(ctx).apply { addView(list) })
        d.setOnDismissListener { sheet = null }
        sheet = d
        d.show()
        return true
    }
}
