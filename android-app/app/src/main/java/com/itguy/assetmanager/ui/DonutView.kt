package com.itguy.assetmanager.ui

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.util.AttributeSet
import android.view.View

/**
 * The status donut from the web dashboard: one arc per status, sized by its
 * share, with the total in the middle. Small gaps between arcs so two
 * neighbouring colours still read as two.
 */
class DonutView @JvmOverloads constructor(
    context: Context, attrs: AttributeSet? = null
) : View(context, attrs) {

    private val d = resources.displayMetrics.density
    private val stroke = 15f * d
    private val arc = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = stroke }
    private val track = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = stroke }
    private val big = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textAlign = Paint.Align.CENTER; typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD); textSize = 24f * d
    }
    private val small = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textAlign = Paint.Align.CENTER; typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        textSize = 9.5f * d; letterSpacing = 0.08f
    }
    private val box = RectF()
    private var parts: List<Pair<Int, Int>> = emptyList()     // value, colour
    var label: String = "ASSETS"

    fun setData(values: List<Pair<Int, Int>>, trackColour: Int, textColour: Int, subColour: Int) {
        parts = values.filter { it.first > 0 }
        track.color = trackColour; big.color = textColour; small.color = subColour
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        val size = minOf(width, height).toFloat()
        val r = (size - stroke) / 2f
        val cx = width / 2f; val cy = height / 2f
        box.set(cx - r, cy - r, cx + r, cy + r)
        canvas.drawArc(box, 0f, 360f, false, track)
        val total = parts.sumOf { it.first }
        if (total > 0) {
            val gap = if (parts.size > 1) 2.5f else 0f
            var start = -90f
            for ((v, c) in parts) {
                val sweep = 360f * v / total
                arc.color = c
                canvas.drawArc(box, start + gap / 2, (sweep - gap).coerceAtLeast(0.5f), false, arc)
                start += sweep
            }
        }
        canvas.drawText(total.toString(), cx, cy + big.textSize * 0.30f, big)
        canvas.drawText(label, cx, cy + big.textSize * 0.30f + small.textSize * 1.6f, small)
    }
}
