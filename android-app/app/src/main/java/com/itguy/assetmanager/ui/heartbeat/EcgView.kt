package com.itguy.assetmanager.ui.heartbeat

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PathMeasure
import android.util.AttributeSet
import android.view.View
import android.view.animation.LinearInterpolator

/**
 * The ECG trace, drawn from a monitor's own check history.
 *
 * One heartbeat per recorded check, oldest on the left: a check that answered
 * draws a full QRS complex, a failed check draws a flatline. That is the
 * honest picture and it reads instantly -- a run of red flat is an outage, and
 * you can see where it started.
 *
 * The bright segment travelling along the trace is the bedside-monitor idea:
 * it says the thing is being watched right now. The trace itself is history
 * and does not move, which matters -- a scrolling trace would imply live data
 * arriving faster than the check interval actually delivers it.
 */
class EcgView @JvmOverloads constructor(
    context: Context, attrs: AttributeSet? = null, defStyle: Int = 0
) : View(context, attrs, defStyle) {

    private val basePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
        alpha = 70
    }
    private val livePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }

    private val path = Path()
    private val measure = PathMeasure()
    private var pathLen = 0f
    private var sweep = 0f
    private var animator: ValueAnimator? = null

    private var bars: List<String> = emptyList()
    private var series: List<Int> = emptyList()
    private var status: String = "pending"
    private var strokeDp = 1.6f

    var colorUp = Color.parseColor("#1FA971")
    var colorDown = Color.parseColor("#E03B3B")
    var colorPending = Color.parseColor("#D08A1F")
    var colorPaused = Color.parseColor("#8A98B0")

    fun setStrokeDp(dp: Float) { strokeDp = dp; requestLayout(); invalidate() }

    /** @param status one of up / down / pending / paused. */
    fun setData(bars: List<String>?, series: List<Int>?, status: String?) {
        this.bars = bars.orEmpty()
        this.series = series.orEmpty()
        this.status = status ?: "pending"
        val c = when (this.status) {
            "up" -> colorUp
            "down" -> colorDown
            "paused" -> colorPaused
            else -> colorPending
        }
        basePaint.color = c
        basePaint.alpha = 70
        livePaint.color = c
        rebuild()
        // a paused monitor is not being checked, so nothing should be sweeping
        if (this.status == "paused") stopSweep() else startSweep()
        invalidate()
    }

    override fun onSizeChanged(w: Int, h: Int, ow: Int, oh: Int) {
        super.onSizeChanged(w, h, ow, oh)
        rebuild()
    }

    private fun rebuild() {
        val w = width.toFloat()
        val h = height.toFloat()
        path.reset()
        if (w <= 0f || h <= 0f) { pathLen = 0f; return }
        val strokePx = strokeDp * resources.displayMetrics.density
        basePaint.strokeWidth = strokePx
        livePaint.strokeWidth = strokePx + 0.4f * resources.displayMetrics.density
        val mid = h / 2f
        // keep the tallest spike inside the view, whatever height it is given
        val room = (h / 2f) - strokePx

        path.moveTo(0f, mid)
        if (bars.isEmpty()) {
            path.lineTo(w, mid)
        } else {
            val seg = w / bars.size
            val lo = series.minOrNull() ?: 0
            val hi = series.maxOrNull() ?: 1
            val span = (hi - lo).coerceAtLeast(1)
            var si = 0
            bars.forEachIndexed { i, s ->
                val x = i * seg
                fun at(f: Float) = x + seg * f
                when (s) {
                    "up" -> {
                        // a quicker response draws a taller spike, so the trace
                        // carries the response shape as well as the up/down record
                        val v = series.getOrNull(si)
                        si++
                        val norm = if (v == null) 0.5f else 1f - ((v - lo).toFloat() / span)
                        val amp = room * (0.55f + 0.45f * norm)
                        path.lineTo(at(0.10f), mid)
                        path.quadTo(at(0.17f), mid - amp * 0.22f, at(0.24f), mid)
                        path.lineTo(at(0.32f), mid + amp * 0.16f)
                        path.lineTo(at(0.40f), mid - amp)
                        path.lineTo(at(0.48f), mid + amp * 0.42f)
                        path.lineTo(at(0.56f), mid)
                        path.quadTo(at(0.72f), mid - amp * 0.28f, at(0.86f), mid)
                        path.lineTo(at(1f), mid)
                    }
                    "down" -> path.lineTo(at(1f), mid)
                    else -> {
                        path.lineTo(at(0.44f), mid)
                        path.lineTo(at(0.52f), mid - room * 0.3f)
                        path.lineTo(at(0.60f), mid)
                        path.lineTo(at(1f), mid)
                    }
                }
            }
        }
        measure.setPath(path, false)
        pathLen = measure.length
    }

    private fun startSweep() {
        val duration = when (status) {
            "down" -> 3600L      // slower, so a flatline reads as a flatline
            "up" -> 2600L
            else -> 4400L
        }
        val existing = animator
        if (existing != null && existing.isRunning && existing.duration == duration) return
        stopSweep()
        animator = ValueAnimator.ofFloat(0f, 1f).apply {
            this.duration = duration
            repeatCount = ValueAnimator.INFINITE
            interpolator = LinearInterpolator()
            addUpdateListener { sweep = it.animatedValue as Float; invalidate() }
            start()
        }
    }

    private fun stopSweep() {
        animator?.cancel()
        animator = null
        sweep = 0f
    }

    override fun onDraw(canvas: Canvas) {
        if (pathLen <= 0f) return
        canvas.drawPath(path, basePaint)
        if (status == "paused") {
            // no sweep: show the trace solid instead of leaving it faint
            val p = Paint(livePaint).apply { alpha = 140 }
            canvas.drawPath(path, p)
            return
        }
        // a bright window travelling along the trace, implemented as a dash
        // whose phase moves -- one gap the length of the path, so exactly one
        // segment is lit at a time
        val windowLen = (pathLen * 0.16f).coerceAtLeast(12f)
        livePaint.pathEffect = DashPathEffect(
            floatArrayOf(windowLen, pathLen),
            -(sweep * (pathLen + windowLen)) + windowLen
        )
        canvas.drawPath(path, livePaint)
    }

    // The view is invisible while its row is recycled off screen; running an
    // animator for it would burn battery for nothing.
    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        if (status != "paused") startSweep()
    }

    override fun onDetachedFromWindow() {
        stopSweep()
        super.onDetachedFromWindow()
    }
}
