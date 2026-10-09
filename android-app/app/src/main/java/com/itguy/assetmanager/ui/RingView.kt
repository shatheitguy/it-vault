package com.itguy.assetmanager.ui

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View
import kotlin.math.min

/**
 * The progress ring from the dashboard's hero card: a track, an arc over it,
 * and a percentage in the middle.
 *
 * A view rather than a drawable because it has to draw text in the hole, and
 * because the hero card sits on the accent colour -- so the track is a faded
 * version of whatever is drawn on, not a fixed grey. Both colours are set
 * from the outside for that reason.
 */
class RingView @JvmOverloads constructor(
    context: Context, attrs: AttributeSet? = null, defStyle: Int = 0,
) : View(context, attrs, defStyle) {

    private val track = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        color = Color.parseColor("#33FFFFFF")
    }
    private val arc = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        color = Color.WHITE
    }
    private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        textAlign = Paint.Align.CENTER
        isFakeBoldText = true
    }

    private val box = RectF()

    /** 0..1. Clamped, because a server that reports 7 of 5 should not draw a
     *  second lap round the ring. */
    var progress: Float = 0f
        set(v) { field = v.coerceIn(0f, 1f); invalidate() }

    /** What sits in the hole. Empty hides it. */
    var centerText: String = ""
        set(v) { field = v; invalidate() }

    fun setColors(arcColor: Int, trackColor: Int, textColor: Int) {
        arc.color = arcColor
        track.color = trackColor
        label.color = textColor
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        val w = width.toFloat()
        val h = height.toFloat()
        val size = min(w, h)
        val stroke = size * 0.1f
        track.strokeWidth = stroke
        arc.strokeWidth = stroke
        val inset = stroke / 2f + size * 0.02f
        box.set(
            (w - size) / 2f + inset, (h - size) / 2f + inset,
            (w + size) / 2f - inset, (h + size) / 2f - inset,
        )
        canvas.drawArc(box, 0f, 360f, false, track)
        // from twelve o'clock, clockwise, as a progress ring is read
        if (progress > 0f) canvas.drawArc(box, -90f, 360f * progress, false, arc)

        if (centerText.isNotEmpty()) {
            label.textSize = size * 0.24f
            val mid = (label.descent() + label.ascent()) / 2f
            canvas.drawText(centerText, w / 2f, h / 2f - mid, label)
        }
    }
}
