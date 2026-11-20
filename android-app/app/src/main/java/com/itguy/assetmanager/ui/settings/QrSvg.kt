package com.itguy.assetmanager.ui.settings

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.Paint
import androidx.core.graphics.PathParser

/**
 * The server sends QR codes (authenticator setup, WhatsApp linking) as the SVG
 * the Python qrcode library draws: a viewBox and path outlines. Android has no
 * SVG view, but it does read SVG path syntax -- so the outlines are drawn
 * straight onto a bitmap, black on white with a quiet margin, which is all a
 * QR code is.
 */
object QrSvg {
    fun render(svg: String, sizePx: Int): Bitmap? = try {
        val vb = Regex("""viewBox="([\d.\s-]+)"""").find(svg)?.groupValues?.get(1)
            ?.trim()?.split(Regex("\\s+"))?.map { it.toFloat() }
        val w = vb?.getOrNull(2) ?: Regex("""width="([\d.]+)""").find(svg)?.groupValues?.get(1)?.toFloat() ?: 0f
        val h = vb?.getOrNull(3) ?: Regex("""height="([\d.]+)""").find(svg)?.groupValues?.get(1)?.toFloat() ?: 0f
        val paths = Regex("""<path[^>]*\sd="([^"]+)"""").findAll(svg).map { it.groupValues[1] }.toList()
        val rects = Regex("""<rect[^>]*?x="([\d.]+)"[^>]*?y="([\d.]+)"[^>]*?width="([\d.]+)"[^>]*?height="([\d.]+)"""")
            .findAll(svg).map { m -> m.groupValues.drop(1).map { it.toFloat() } }.toList()
        if (w <= 0f || h <= 0f || (paths.isEmpty() && rects.isEmpty())) null else {
            val bmp = Bitmap.createBitmap(sizePx, sizePx, Bitmap.Config.ARGB_8888)
            val c = Canvas(bmp); c.drawColor(Color.WHITE)
            val pad = sizePx * 0.04f
            val scale = (sizePx - 2 * pad) / maxOf(w, h)
            val m = Matrix().apply { postScale(scale, scale); postTranslate(pad, pad) }
            val ink = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.BLACK; style = Paint.Style.FILL }
            c.save(); c.concat(m)
            for (d in paths) PathParser.createPathFromPathData(d)?.let { c.drawPath(it, ink) }
            for ((x, y, rw, rh) in rects) if (rw < w * 0.98f) c.drawRect(x, y, x + rw, y + rh, ink)
            c.restore()
            bmp
        }
    } catch (e: Exception) { null }
}
