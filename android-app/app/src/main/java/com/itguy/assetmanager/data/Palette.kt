package com.itguy.assetmanager.data

import android.content.Context
import android.content.res.Configuration
import android.content.res.Resources
import android.graphics.Color
import android.graphics.drawable.ColorDrawable
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import androidx.appcompat.app.AppCompatDelegate
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

    /** An accent too close to the surface it sits on is nudged toward legible.
     *
     * Away from the surface, not into it. Mixing an accent into the very
     * surface it has to stand out from is how a yellow brand colour vanishes
     * on white -- which is exactly what light mode would otherwise do to it.
     * The hue is kept: it is still their colour, darkened or lightened only
     * as far as it takes to be read. */
    private fun ensureVisible(accent: Int, surface: Int): Int {
        if (contrast(accent, surface) >= 2.2) return accent
        val away = if (isLight(surface)) Color.BLACK else Color.WHITE
        var out = accent
        var i = 0
        while (i < 6 && contrast(out, surface) < 2.2) {
            out = blend(away, out, 0.18)   // 18% toward the far end each pass
            i++
        }
        return out
    }

    /**
     * Which scheme the phone is in.
     *
     * Whether an interface is light or dark was never really an admin's
     * decision: the person holding the phone answered it once, for every app
     * they own, and expects this one to agree. What the server decides is the
     * brand -- the accent, the hue of the ground -- which is what the palette
     * below keeps.
     *
     * An explicit choice in the app's own settings still wins; "system" (the
     * default) asks the device.
     */
    fun prefersLight(): Boolean = when (AppCompatDelegate.getDefaultNightMode()) {
        AppCompatDelegate.MODE_NIGHT_NO -> true
        AppCompatDelegate.MODE_NIGHT_YES -> false
        else -> (Resources.getSystem().configuration.uiMode and
            Configuration.UI_MODE_NIGHT_MASK) != Configuration.UI_MODE_NIGHT_YES
    }

    /**
     * A configured colour, swung to the scheme in use.
     *
     * The whole palette derives from two values -- the page ground and the
     * card surface -- so following the device means swinging exactly those
     * two and letting text, muted text, outlines and button ink fall out of
     * them as they already do. A colour already on the right side of the line
     * is returned untouched, which is why a dark install in dark mode is what
     * it always was.
     */
    private fun toScheme(c: Int, wantLight: Boolean, isSurface: Boolean): Int {
        if (isLight(c) == wantLight) return c
        return if (wantLight) blend(Color.WHITE, c, if (isSurface) 0.97 else 0.91)
        else blend(Color.parseColor("#05070b"), c, if (isSurface) 0.86 else 0.90)
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
        val wantLight = prefersLight()
        val baseBg = toScheme(firstColour(Prefs.brandBg) ?: Color.parseColor("#0a0d13"),
                              wantLight, false)
        val surface = toScheme(firstColour(Prefs.brandSurface) ?: Color.parseColor("#121826"),
                               wantLight, true)
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

        // Two maps over the same roles, because one colour can mean two
        // things. In the light palette the card surface and the ink on a
        // coloured button are both #FFFFFF, and a single map keyed by colour
        // has to pick one: it picked the ink, so every view whose background
        // was plain white -- a reply bar, a toolbar strip -- was repainted in
        // near-black. Which it means is decided by where the colour is used.
        // Behind something, white is a surface; in front of something, white
        // is ink. Each map puts the losing role first so the winner's put
        // overwrites it.
        fun build(inkWins: Boolean) = HashMap<Int, Int>(16).apply {
            if (!inkWins) put(from.onAccent, server.onAccent)
            put(from.bg, server.bg)
            put(from.surface, server.surface)
            put(from.surfaceVariant, server.surfaceVariant)
            put(from.accent, server.accent)
            put(from.accent2, server.accent2)
            put(from.accentContainer, server.accentContainer)
            put(from.text, server.text)
            put(from.muted, server.muted)
            put(from.outline, server.outline)
            put(from.barTrack, server.barTrack)
            if (inkWins) put(from.onAccent, server.onAccent)
        }
        val behind = build(inkWins = false)
        val front = build(inkWins = true)
        // a palette that maps a colour to itself has nothing to do
        if (behind.all { (k, v) -> k == v } && front.all { (k, v) -> k == v }) return
        walk(view, behind, front, server.accent)
    }

    /**
     * A view tagged with this, in XML or in code, is left exactly as it is --
     * and so is everything inside it.
     *
     * The repaint works by colour value, which cannot tell "a white card"
     * from "white text on the accent": both are #FFFFFF. Anything already
     * painted in deliberate contrast to the accent says so with this tag
     * instead of being guessed at.
     */
    const val KEEP = "keep-colours"

    /**
     * A tint list repainted by what it looks like when the view is *enabled*.
     *
     * Not by `defaultColor`, which is the trap this walked into for months.
     * A ColorStateList's default is the colour of its last entry, and
     * Material's own button tint is written
     *
     *     <item android:color="?attr/colorContainer" android:state_enabled="true"/>
     *     <item android:alpha="..." android:color="?attr/colorOnSurface"/>
     *
     * -- the accent first, the disabled grey last. So every filled button in
     * the app asked the palette to repaint a translucent grey that was never
     * a palette colour, missed, and kept the bundled red while the FAB beside
     * it (whose tint is a plain one-colour list) went to the install's own
     * accent. Enabled is the state a control is in when anyone is looking at
     * it, so that is the colour that decides.
     *
     * Returns null when there is nothing to change, and otherwise a list that
     * keeps whatever the disabled state was.
     */
    /**
     * The states worth asking a tint about, most specific first.
     *
     * Enough to carry a switch, which is the widget with the most to say: its
     * track and thumb are one colour checked and another unchecked, and
     * another again when it is off limits.
     */
    private val PROBES = arrayOf(
        intArrayOf(-android.R.attr.state_enabled),
        intArrayOf(android.R.attr.state_enabled, android.R.attr.state_checked),
        intArrayOf(android.R.attr.state_enabled, android.R.attr.state_selected),
        intArrayOf(android.R.attr.state_enabled),
    )

    private fun remap(
        csl: android.content.res.ColorStateList?, map: Map<Int, Int>,
    ): android.content.res.ColorStateList? {
        if (csl == null) return null

        // A tint that was one flat colour must come back one flat colour.
        //
        // Returning a state list here is what made the dashboard's hero card
        // go back to the bundled red the second time it was opened. The list
        // said "this colour unless the view is disabled", and whether a view
        // counts as enabled is not something every widget agrees on -- a card
        // is not a control, so a MaterialCardView's own fill was matching the
        // disabled entry and painting itself the colour we were trying to
        // replace. Nothing about a card's fill was ever state-dependent; it
        // only became so because this function made it so.
        if (!csl.isStateful) {
            val want = map[csl.defaultColor] ?: return null
            return if (want == csl.defaultColor) null
            else android.content.res.ColorStateList.valueOf(want)
        }

        // A stateful tint keeps its states, each one repainted on its own.
        // Reading only `defaultColor` is the trap this started in: a
        // ColorStateList's default is its *last* entry, and Material writes a
        // button's tint accent-first, disabled-grey-last.
        val before = PROBES.map { csl.getColorForState(it, csl.defaultColor) }
        val after = before.map { map[it] ?: it }
        if (before == after) return null
        return android.content.res.ColorStateList(
            PROBES + arrayOf(intArrayOf()),
            (after + after.last()).toIntArray(),
        )
    }

    private fun walk(v: View, behind: Map<Int, Int>, front: Map<Int, Int>, accent: Int) {
        if (v.tag == KEEP) return

        // background: only a flat colour can be remapped by value. A drawable
        // is mutated and tinted instead -- and mutate() matters, because
        // drawables from resources are shared and tinting one in place would
        // recolour every other view using it.
        (v.background as? ColorDrawable)?.color?.let { cur ->
            behind[cur]?.let { v.setBackgroundColor(it) }
        }
        remap(v.backgroundTintList, behind)?.let { v.backgroundTintList = it }

        when (v) {
            // A MaterialCardView's fill is neither a ColorDrawable nor a
            // background tint -- it is a shape drawable the card owns -- so
            // the two lines above cannot see it. The dashboard's hero card
            // asks for @color/accent and was still showing the bundled red on
            // a branded install, which is as visible as a miss gets.
            is com.google.android.material.card.MaterialCardView -> {
                remap(v.cardBackgroundColor, behind)?.let { v.setCardBackgroundColor(it) }
                remap(v.strokeColorStateList, behind)?.let { v.setStrokeColor(it) }
            }
            // A switch carries the accent on its track when it is on, which
            // is as much "the brand colour" as a button's fill.
            // A tab bar's indicator cannot be read back off the view, so it
            // is the one colour that has to be told rather than asked: it is
            // the accent by definition, which is why Directory and the
            // catalogue still underlined the chosen tab in the bundled red.
            is com.google.android.material.tabs.TabLayout -> {
                remap(v.tabTextColors, front)?.let { v.tabTextColors = it }
                v.setSelectedTabIndicatorColor(accent)
            }
            is androidx.appcompat.widget.SwitchCompat -> {
                remap(v.thumbTintList, behind)?.let { v.thumbTintList = it }
                remap(v.trackTintList, behind)?.let { v.trackTintList = it }
                front[v.currentTextColor]?.let { v.setTextColor(it) }
            }
            // a checkbox or a radio button says the same thing with its tick
            is android.widget.CompoundButton -> {
                remap(v.buttonTintList, behind)?.let { v.buttonTintList = it }
                front[v.currentTextColor]?.let { v.setTextColor(it) }
            }
            is com.google.android.material.button.MaterialButton -> {
                // a button's outline and the glyph on it are as much "the
                // brand colour" as its fill, and each is its own state list
                remap(v.strokeColor, front)?.let { v.strokeColor = it }
                remap(v.iconTint, front)?.let { v.iconTint = it }
                remap(v.textColors, front)?.let { v.setTextColor(it) }
            }
            is TextView -> {
                front[v.currentTextColor]?.let { v.setTextColor(it) }
                front[v.currentHintTextColor]?.let { v.setHintTextColor(it) }
                remap(v.compoundDrawableTintList, front)?.let {
                    v.compoundDrawableTintList = it
                }
            }
            is ImageView -> remap(v.imageTintList, front)?.let { v.imageTintList = it }
        }

        if (v is ViewGroup) {
            for (i in 0 until v.childCount) walk(v.getChildAt(i), behind, front, accent)
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
