package com.itguy.assetmanager.data

import android.content.Context
import android.graphics.Color
import android.graphics.drawable.ColorDrawable
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.core.content.ContextCompat
import com.itguy.assetmanager.R

/**
 * The deployment's colours, applied to a view tree.
 *
 * Every install themes itself -- accent, second accent, page and card
 * background -- and the app was ignoring all of it and rendering the bundled
 * red. `/api/branding` has always returned these values; nothing read them.
 *
 * Two decisions worth knowing:
 *
 * The derived colours (card surface, hairlines, body and muted text, the ink
 * on a coloured button) use the same arithmetic as the web app and the
 * publicly shared pages, so one server produces one set of colours across all
 * three. In particular `bestTextOn` picks button ink from the accent's own
 * lightness: a fixed dark ink vanishes on a near-black accent and a fixed
 * white one vanishes on bright yellow.
 *
 * Applying it walks the view tree and swaps colours by *role* rather than
 * requiring every layout to be rewritten: a view currently painted in the
 * bundled accent is repainted in the server's accent, and so on for each
 * palette slot. That keeps XML as the single source of layout truth and means
 * a screen added later is themed without being told about theming.
 */
object Palette {

    /** True once the server's palette has been cached at least once. */
    fun isCustom(): Boolean = parse(Prefs.brandAccent) != null

    // ---------------------------------------------------------------- maths

    /** #rgb / #rrggbb -> colour int, or null if it isn't a hex colour. */
    private fun parse(raw: String?): Int? {
        val s = (raw ?: "").trim()
        if (!s.startsWith("#")) return null
        val hex = when (s.length) {
            4 -> "#" + s[1] + s[1] + s[2] + s[2] + s[3] + s[3]
            7 -> s
            else -> return null
        }
        return runCatching { Color.parseColor(hex) }.getOrNull()
    }

    /** A gradient is stored as its CSS; take the first colour out of it. */
    private fun firstColour(raw: String?): Int? {
        parse(raw)?.let { return it }
        val m = Regex("#[0-9a-fA-F]{3,6}").find(raw ?: "") ?: return null
        return parse(m.value)
    }

    private fun isLight(c: Int): Boolean =
        (Color.red(c) * 0.299 + Color.green(c) * 0.587 + Color.blue(c) * 0.114) > 150

    /** Lighten (positive) or darken (negative) by a fraction of full range. */
    private fun shade(c: Int, amt: Double): Int {
        fun f(v: Int) = (v + 255 * amt).coerceIn(0.0, 255.0).toInt()
        return Color.rgb(f(Color.red(c)), f(Color.green(c)), f(Color.blue(c)))
    }

    private fun luminance(c: Int): Double {
        fun ch(v: Int): Double {
            val x = v / 255.0
            return if (x <= 0.03928) x / 12.92 else Math.pow((x + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * ch(Color.red(c)) + 0.7152 * ch(Color.green(c)) + 0.0722 * ch(Color.blue(c))
    }

    private fun contrast(a: Int, b: Int): Double {
        val la = luminance(a); val lb = luminance(b)
        return (maxOf(la, lb) + 0.05) / (minOf(la, lb) + 0.05)
    }

    /** Ink for text sitting on top of [bg] -- whichever of the two reads. */
    private fun bestTextOn(bg: Int): Int =
        if (contrast(bg, INK_DARK) >= contrast(bg, INK_LIGHT)) INK_DARK else INK_LIGHT

    /** An accent too close to the surface it sits on is nudged toward legible. */
    private fun ensureVisible(accent: Int, surface: Int): Int {
        if (contrast(accent, surface) >= 2.2) return accent
        fun mix(a: Int, b: Int) = Math.round(a * 0.65 + b * 0.35).toInt()
        return Color.rgb(
            mix(Color.red(accent), Color.red(surface)),
            mix(Color.green(accent), Color.green(surface)),
            mix(Color.blue(accent), Color.blue(surface)),
        )
    }

    private val INK_DARK = Color.parseColor("#04121f")
    private val INK_LIGHT = Color.parseColor("#e6edf6")

    // -------------------------------------------------------------- palette

    /** One palette slot: the bundled colour, and what the server makes of it. */
    class Colours(
        val bg: Int, val surface: Int, val surfaceVariant: Int,
        val accent: Int, val accent2: Int, val accentContainer: Int, val onAccent: Int,
        val text: Int, val muted: Int, val outline: Int, val barTrack: Int,
    )

    /** The server's palette, or null when nothing has been cached yet. */
    fun serverColours(): Colours? {
        val accentRaw = parse(Prefs.brandAccent) ?: return null
        val baseBg = firstColour(Prefs.brandBg) ?: Color.parseColor("#0a0d13")
        val surface = firstColour(Prefs.brandSurface) ?: Color.parseColor("#121826")
        val light = isLight(baseBg)
        val surfaceLight = isLight(surface)
        val accent = ensureVisible(accentRaw, surface)
        val accent2 = ensureVisible(parse(Prefs.brandAccent2) ?: accentRaw, surface)
        return Colours(
            bg = baseBg,
            surface = surface,
            surfaceVariant = if (surfaceLight) shade(surface, -0.04) else shade(surface, -0.02),
            accent = accent,
            accent2 = accent2,
            // the web uses rgba(accent,.14) over the surface; flatten it here
            // because Android tints are opaque in most of these slots
            accentContainer = blend(accent, surface, 0.14),
            onAccent = bestTextOn(accent),
            text = if (light) Color.parseColor("#16202e") else Color.parseColor("#e6edf6"),
            muted = if (light) Color.parseColor("#5d6b82") else Color.parseColor("#8a98b0"),
            outline = if (surfaceLight) shade(surface, -0.14) else shade(surface, 0.10),
            barTrack = if (surfaceLight) shade(surface, -0.08) else shade(surface, 0.06),
        )
    }

    private fun blend(fg: Int, bg: Int, alpha: Double): Int {
        fun c(f: Int, b: Int) = Math.round(f * alpha + b * (1 - alpha)).toInt()
        return Color.rgb(
            c(Color.red(fg), Color.red(bg)),
            c(Color.green(fg), Color.green(bg)),
            c(Color.blue(fg), Color.blue(bg)),
        )
    }

    /** The bundled palette, as currently resolved for light or night mode. */
    private fun bundled(ctx: Context): Colours {
        fun c(id: Int) = ContextCompat.getColor(ctx, id)
        return Colours(
            bg = c(R.color.bg), surface = c(R.color.surface),
            surfaceVariant = c(R.color.surface_variant),
            accent = c(R.color.accent), accent2 = c(R.color.accent2),
            accentContainer = c(R.color.accent_container), onAccent = c(R.color.on_accent),
            text = c(R.color.text), muted = c(R.color.muted),
            outline = c(R.color.outline), barTrack = c(R.color.bar_track),
        )
    }

    // ---------------------------------------------------------------- apply

    /**
     * Repaints [root] and everything under it in the server's colours.
     *
     * Safe to call on every screen, and a no-op when no palette is cached, so
     * a call site never has to ask whether theming is active.
     */
    fun apply(root: View?) {
        val view = root ?: return
        val server = serverColours() ?: return
        val from = bundled(view.context)
        val map = HashMap<Int, Int>(16).apply {
            put(from.bg, server.bg)
            put(from.surface, server.surface)
            put(from.surfaceVariant, server.surfaceVariant)
            put(from.accent, server.accent)
            put(from.accent2, server.accent2)
            put(from.accentContainer, server.accentContainer)
            put(from.onAccent, server.onAccent)
            put(from.text, server.text)
            put(from.muted, server.muted)
            put(from.outline, server.outline)
            put(from.barTrack, server.barTrack)
        }
        // a palette that maps a colour to itself has nothing to do
        if (map.all { (k, v) -> k == v }) return
        walk(view, map)
    }

    private fun walk(v: View, map: Map<Int, Int>) {
        // background: only a flat colour can be remapped by value. A drawable
        // is mutated and tinted instead -- and mutate() matters, because
        // drawables from resources are shared and tinting one in place would
        // recolour every other view using it.
        (v.background as? ColorDrawable)?.color?.let { cur ->
            map[cur]?.let { v.setBackgroundColor(it) }
        }
        v.backgroundTintList?.defaultColor?.let { cur ->
            map[cur]?.let { v.backgroundTintList = android.content.res.ColorStateList.valueOf(it) }
        }

        when (v) {
            is TextView -> {
                map[v.currentTextColor]?.let { v.setTextColor(it) }
                map[v.currentHintTextColor]?.let { v.setHintTextColor(it) }
                v.compoundDrawableTintList?.defaultColor?.let { cur ->
                    map[cur]?.let {
                        v.compoundDrawableTintList =
                            android.content.res.ColorStateList.valueOf(it)
                    }
                }
            }
            is ImageView -> v.imageTintList?.defaultColor?.let { cur ->
                map[cur]?.let { v.imageTintList = android.content.res.ColorStateList.valueOf(it) }
            }
        }

        if (v is ViewGroup) {
            for (i in 0 until v.childCount) walk(v.getChildAt(i), map)
        }
    }

    /** Stores what /api/branding reported. Returns true if anything changed. */
    fun store(body: Map<String, Any?>): Boolean {
        fun s(k: String) = (body[k] as? String)?.trim().orEmpty()
        val before = listOf(Prefs.brandAccent, Prefs.brandAccent2,
                            Prefs.brandBg, Prefs.brandSurface, Prefs.brandRadius.toString())
        parse(s("accent"))?.let { Prefs.brandAccent = s("accent") }
        parse(s("accent2"))?.let { Prefs.brandAccent2 = s("accent2") }
        if (s("bg").isNotBlank()) Prefs.brandBg = s("bg")
        if (s("comp_bg").isNotBlank()) Prefs.brandSurface = s("comp_bg")
        ((body["radius"] as? Number)?.toInt())?.let { Prefs.brandRadius = it }
        val after = listOf(Prefs.brandAccent, Prefs.brandAccent2,
                           Prefs.brandBg, Prefs.brandSurface, Prefs.brandRadius.toString())
        return before != after
    }

    /** Forgets the cached palette -- on logout, or a switch of server. */
    fun clear() {
        Prefs.brandAccent = ""
        Prefs.brandAccent2 = ""
        Prefs.brandBg = ""
        Prefs.brandSurface = ""
        Prefs.brandRadius = 0
    }
}
