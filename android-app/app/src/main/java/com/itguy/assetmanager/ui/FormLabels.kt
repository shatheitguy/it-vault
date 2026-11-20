package com.itguy.assetmanager.ui

import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import androidx.constraintlayout.widget.ConstraintLayout
import androidx.core.content.ContextCompat
import androidx.core.widget.TextViewCompat
import com.google.android.material.textfield.TextInputLayout
import com.itguy.assetmanager.R

/**
 * Fields the way the web app draws them: the label above the box, small and
 * quiet, rather than Material's hint that sits inside the box and floats up
 * into its border when you type.
 *
 * Every form already gives each TextInputLayout a hint; this lifts that hint
 * out into a label above the field, on every screen, so no layout had to be
 * rewritten and a new screen gets it without anyone remembering to. The field
 * and its new label are wrapped together, so a field that sat in a row with
 * a weight keeps its place and its weight.
 */
object FormLabels {

    fun apply(root: View?) {
        if (root != null) walk(root)
    }

    private fun walk(v: View) {
        if (v is TextInputLayout) { relabel(v); return }
        if (v is ViewGroup) for (i in v.childCount - 1 downTo 0) walk(v.getChildAt(i))
    }

    private fun relabel(til: TextInputLayout) {
        if (!til.isHintEnabled) return                 // done already, or wants no label
        val hint = til.hint?.toString()?.trim().orEmpty()
        if (hint.isEmpty()) return
        val parent = til.parent as? ViewGroup ?: return
        if (parent is ConstraintLayout) return         // constraints name the field; leave it be
        // "Search assets…" is a prompt, not a name: it stays inside the box
        // as the placeholder, the way the web's search box has it
        if (hint.endsWith("…") || hint.endsWith("...")) {
            til.hint = null
            til.isHintEnabled = false
            til.editText?.hint = hint
            return
        }
        val ctx = til.context
        val label = TextView(ctx).apply {
            text = hint.uppercase()
            TextViewCompat.setTextAppearance(this, R.style.FieldLabelText)
            setTextColor(ContextCompat.getColor(ctx, R.color.text_soft))
        }
        val idx = parent.indexOfChild(til)
        val lp = til.layoutParams
        parent.removeViewAt(idx)
        val box = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL }
        val dp6 = (6 * ctx.resources.displayMetrics.density).toInt()
        box.addView(label, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp6 })
        box.addView(til, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        parent.addView(box, idx, lp)
        // the placeholder inside the box stays useful: it shows until you type
        til.hint = null
        til.isHintEnabled = false
        til.editText?.let { if (it.hint.isNullOrBlank()) it.hint = "" }
    }
}
