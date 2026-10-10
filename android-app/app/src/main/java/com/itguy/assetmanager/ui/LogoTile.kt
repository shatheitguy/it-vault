package com.itguy.assetmanager.ui

import android.graphics.Outline
import android.view.View
import android.view.ViewOutlineProvider
import android.widget.ImageView

/**
 * How an install's logo is fitted into the tile it sits in.
 *
 * A white tile with the mark inset in the middle is the safe answer for a
 * logo of unknown shape, and it is the wrong answer for most of them: a
 * square badge drawn small inside a white square reads as a sticker stuck on
 * a sticker, with a white rim all the way round that belongs to neither.
 *
 * So the shape of the artwork decides. A roughly square mark is an app icon
 * and is given the whole tile, clipped to the tile's own corners, so the logo
 * *is* the tile. A wide one is a wordmark, and cropping a wordmark takes half
 * the name off, so that keeps the white surface and sits inside it.
 */
object LogoTile {

    /** Anything within this of square is treated as an icon. */
    private const val SQUARISH_LOW = 0.82f
    private const val SQUARISH_HIGH = 1.22f

    /**
     * Fits whatever [view] is currently showing. Call it again after the
     * server's logo replaces the bundled one, because the two are rarely the
     * same shape.
     *
     * [cornerDp] must match the tile drawable behind it, or the clip and the
     * white underneath it will disagree at the corners.
     */
    fun fit(view: ImageView, cornerDp: Float, insetDp: Float) {
        val d = view.resources.displayMetrics.density
        val radius = cornerDp * d

        val dr = view.drawable
        val w = dr?.intrinsicWidth ?: 0
        val h = dr?.intrinsicHeight ?: 0
        val squarish = w > 0 && h > 0 && (w.toFloat() / h) in SQUARISH_LOW..SQUARISH_HIGH

        if (squarish) {
            view.outlineProvider = object : ViewOutlineProvider() {
                override fun getOutline(v: View, outline: Outline) {
                    outline.setRoundRect(0, 0, v.width, v.height, radius)
                }
            }
            view.clipToOutline = true
            view.setPadding(0, 0, 0, 0)
            view.scaleType = ImageView.ScaleType.CENTER_CROP
        } else {
            // a wordmark keeps the white surface, and wants no clip: there is
            // nothing of it at the corners to clip away
            view.clipToOutline = false
            val p = (insetDp * d).toInt()
            view.setPadding(p, p, p, p)
            view.scaleType = ImageView.ScaleType.FIT_CENTER
        }
    }
}
