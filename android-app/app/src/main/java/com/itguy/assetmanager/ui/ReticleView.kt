package com.itguy.assetmanager.ui

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View

/**
 * The scanner's target: a faint box with its four corners picked out.
 *
 * It used to be a layer-list that drew the same rounded rectangle three
 * times, two of them nudged diagonally, on the theory that the overlap would
 * read as corner brackets. It does not: a rectangle offset by 40dp is still a
 * whole rectangle, so the viewfinder showed two boxes crossing each other at
 * an angle, which is the one thing a "hold it here" frame must not do.
 *
 * Four corners, drawn as four corners. The colour is the install's accent,
 * set from the palette rather than baked in, because the scanner was the last
 * screen still showing the bundled pink.
 */
class ReticleView @JvmOverloads constructor(
    context: Context, attrs: AttributeSet? = null, defStyle: Int = 0,
) : View(context, attrs, defStyle) {

    private val d = resources.displayMetrics.density
    private val radius = 18f * d
    /** How far along each edge a corner bracket runs. */
    private val arm = 34f * d

    private val box = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 1f * d
        color = 0x44FFFFFF
    }

    private val corner = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 3.5f * d
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
        color = Color.WHITE
    }

    fun setColor(colour: Int) {
        corner.color = colour
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        val inset = corner.strokeWidth / 2f
        val r = RectF(inset, inset, width - inset, height - inset)
        canvas.drawRoundRect(r, radius, radius, box)

        // each corner is a straight run in, round the curve, and straight out
        val p = Path()
        // top-left
        p.moveTo(r.left, r.top + radius + arm)
        p.lineTo(r.left, r.top + radius)
        p.quadTo(r.left, r.top, r.left + radius, r.top)
        p.lineTo(r.left + radius + arm, r.top)
        // top-right
        p.moveTo(r.right - radius - arm, r.top)
        p.lineTo(r.right - radius, r.top)
        p.quadTo(r.right, r.top, r.right, r.top + radius)
        p.lineTo(r.right, r.top + radius + arm)
        // bottom-right
        p.moveTo(r.right, r.bottom - radius - arm)
        p.lineTo(r.right, r.bottom - radius)
        p.quadTo(r.right, r.bottom, r.right - radius, r.bottom)
        p.lineTo(r.right - radius - arm, r.bottom)
        // bottom-left
        p.moveTo(r.left + radius + arm, r.bottom)
        p.lineTo(r.left + radius, r.bottom)
        p.quadTo(r.left, r.bottom, r.left, r.bottom - radius)
        p.lineTo(r.left, r.bottom - radius - arm)

        canvas.drawPath(p, corner)
    }
}
