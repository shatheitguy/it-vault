package com.itguy.assetmanager.ui.assets

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import com.google.android.material.bottomsheet.BottomSheetDialogFragment
import com.itguy.assetmanager.R
import com.itguy.assetmanager.data.model.Asset
import com.itguy.assetmanager.ui.ActionSheet

/**
 * What the list is narrowed to. All four are "any" until somebody picks.
 *
 * Search and filters are different questions and both are kept: the search box
 * answers "where is the thing called X", the filters answer "show me every
 * laptop in the Dubai store that is still available". Typing a status into the
 * search box happened to work for Status and nothing else, which is the sort
 * of near-miss that teaches people the app is unreliable.
 */
data class AssetFilters(
    val status: String? = null,
    val type: String? = null,
    val location: String? = null,
    val manufacturer: String? = null,
) {
    val activeCount: Int
        get() = listOf(status, type, location, manufacturer).count { !it.isNullOrBlank() }

    val isEmpty: Boolean get() = activeCount == 0

    /** True when this asset survives every filter that is set. */
    fun matches(a: Asset): Boolean =
        (status.isNullOrBlank() || a.Status.equals(status, true)) &&
        (type.isNullOrBlank() || a.Type.equals(type, true)) &&
        (location.isNullOrBlank() || a.Location.equals(location, true)) &&
        (manufacturer.isNullOrBlank() || a.Manufacturer.equals(manufacturer, true))
}

/**
 * The filter sheet: status, category, location, manufacturer.
 *
 * The options are built from the assets the phone actually has rather than
 * from a fixed list or another round trip. Two reasons. An install's
 * categories are its own -- "CCTV", "Vehicle", whatever they set up -- so a
 * hard-coded list would be wrong everywhere. And this screen has to work with
 * no signal, which it does, because the same list is in the offline cache.
 *
 * An option that no asset has is not offered: a filter that can only return
 * nothing is a dead end.
 */
class AssetFiltersSheet : BottomSheetDialogFragment() {

    /** Called with the chosen filters when APPLY is tapped. */
    var onApply: ((AssetFilters) -> Unit)? = null

    /** The rows the options come from, and the filters already in force. */
    var source: List<Asset> = emptyList()
    var current: AssetFilters = AssetFilters()

    private var picked = AssetFilters()

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View {
        val ctx = requireContext()
        val d = resources.displayMetrics.density
        fun px(v: Float) = (v * d).toInt()
        picked = current

        val root = LinearLayout(ctx).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, 0, 0, px(10f))
        }

        // the same header, rows and dividers the long-press sheet uses: both
        // are "here is a thing, here is what you can do to it", and there was
        // no reason for the two to look like different apps
        val header = ActionSheet.header(ctx, "Filter assets", summary())
        root.addView(header)
        root.addView(ActionSheet.divider(ctx))

        fun options(pick: (Asset) -> String): List<String> =
            source.map(pick).map { it.trim() }.filter { it.isNotBlank() }
                .distinctBy { it.lowercase() }.sortedBy { it.lowercase() }

        val repaint = mutableListOf<() -> Unit>()

        fun row(
            label: String, icon: Int, values: List<String>,
            get: () -> String?, set: (String?) -> Unit,
        ) {
            val holder = LinearLayout(ctx).apply {
                orientation = LinearLayout.VERTICAL
            }
            fun draw() {
                holder.removeAllViews()
                holder.addView(ActionSheet.row(ctx, ActionSheet.Row(
                    label, icon, value = get()?.takeIf { it.isNotBlank() } ?: ActionSheet.ANY,
                ) { choose(label, values, get, set) { repaint.forEach { r -> r() } } }))
                // a row built after the screen was themed has to be themed
                // itself, or its value comes out in the bundled accent
                com.itguy.assetmanager.data.Palette.apply(holder)
            }
            draw()
            repaint += ::draw
            root.addView(holder)
        }

        row("Status", R.drawable.ic_status, options { it.Status },
            { picked.status }) { picked = picked.copy(status = it) }
        row("Category", R.drawable.ic_catalog, options { it.Type },
            { picked.type }) { picked = picked.copy(type = it) }
        row("Location", R.drawable.ic_location, options { it.Location },
            { picked.location }) { picked = picked.copy(location = it) }
        row("Manufacturer", R.drawable.ic_factory, options { it.Manufacturer },
            { picked.manufacturer }) { picked = picked.copy(manufacturer = it) }

        // the header's subtitle counts what is set, so it has to be redrawn
        // along with the rows
        repaint += {
            (header.getChildAt(1) as? TextView)?.text = summary()
        }

        root.addView(ActionSheet.divider(ctx))

        val buttons = LinearLayout(ctx).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(px(22f), px(10f), px(22f), px(6f))
        }
        buttons.addView(
            com.google.android.material.button.MaterialButton(
                ctx, null, com.google.android.material.R.attr.materialButtonStyle
            ).apply {
                text = "Clear all"
                layoutParams = LinearLayout.LayoutParams(
                    0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f
                ).also { it.rightMargin = px(10f) }
                setOnClickListener {
                    picked = AssetFilters()
                    repaint.forEach { it() }
                }
            }.also { quiet(it) }
        )
        buttons.addView(
            com.google.android.material.button.MaterialButton(ctx).apply {
                text = "Apply"
                layoutParams = LinearLayout.LayoutParams(
                    0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
                setOnClickListener { onApply?.invoke(picked); dismiss() }
            }.also { filled(it) }
        )
        root.addView(buttons)

        return root
    }

    /** What the sheet says it is doing, under its own title. */
    private fun summary(): String = when (picked.activeCount) {
        0 -> "Showing everything"
        1 -> "1 filter set"
        else -> "${picked.activeCount} filters set"
    }

    /** The pill buttons the rest of the app uses, built in code. */
    private fun filled(b: com.google.android.material.button.MaterialButton) {
        val p = com.itguy.assetmanager.data.Palette.serverColours()
        val accent = p?.accent ?: resources.getColor(R.color.accent, null)
        val on = p?.onAccent ?: resources.getColor(R.color.on_accent, null)
        b.cornerRadius = 100
        b.isAllCaps = false
        b.textSize = 15f
        b.setTypeface(android.graphics.Typeface.DEFAULT, android.graphics.Typeface.BOLD)
        b.minHeight = (52 * resources.displayMetrics.density).toInt()
        b.backgroundTintList = android.content.res.ColorStateList.valueOf(accent)
        b.setTextColor(on)
    }

    private fun quiet(b: com.google.android.material.button.MaterialButton) {
        val p = com.itguy.assetmanager.data.Palette.serverColours()
        val accent = p?.accent ?: resources.getColor(R.color.accent, null)
        b.cornerRadius = 100
        b.isAllCaps = false
        b.textSize = 15f
        b.setTypeface(android.graphics.Typeface.DEFAULT, android.graphics.Typeface.BOLD)
        b.minHeight = (52 * resources.displayMetrics.density).toInt()
        b.backgroundTintList = android.content.res.ColorStateList.valueOf(
            (accent and 0x00FFFFFF) or 0x24000000)
        b.setTextColor(accent)
    }

    /**
     * Picking one value for one filter.
     *
     * "Any" is first and always offered; the rest is whatever the assets on
     * the phone actually contain, so a filter can never return nothing.
     */
    private fun choose(
        label: String, values: List<String>,
        get: () -> String?, set: (String?) -> Unit, done: () -> Unit,
    ) {
        val ctx = requireContext()
        if (values.isEmpty()) {
            android.widget.Toast.makeText(
                ctx, "Nothing to filter by yet \u2014 no asset has a $label",
                android.widget.Toast.LENGTH_SHORT,
            ).show()
            return
        }
        // Our own rows rather than setSingleChoiceItems.
        //
        // The platform's version builds its rows from an adapter whenever it
        // feels like laying out, so a repaint lands on rows it then replaces,
        // and its radio marks stayed the bundled red however many passes we
        // gave them. These are the rows the sheet itself is made of, built
        // once, themed once, and the tick is the same tick the rest of the
        // app draws.
        val items = listOf(ActionSheet.ANY) + values
        val chosen = get()?.takeIf { it.isNotBlank() }

        val list = LinearLayout(ctx).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, (6 * resources.displayMetrics.density).toInt(), 0, 0)
        }
        val dlg = com.itguy.assetmanager.ui.BrandDialog(ctx)
            .setTitle(label)
            .setView(android.widget.ScrollView(ctx).apply { addView(list) })
            .setNegativeButton("Cancel", null)
            .create()

        items.forEach { option ->
            val isAny = option == ActionSheet.ANY
            val on = if (isAny) chosen == null else option.equals(chosen, true)
            list.addView(ActionSheet.row(ctx, ActionSheet.Row(
                option,
                if (on) R.drawable.ic_check else R.drawable.ic_blank,
                value = null,
                selected = on,
            ) {
                set(if (isAny) null else option)
                done()
                dlg.dismiss()
            }))
        }
        dlg.show()
        com.itguy.assetmanager.data.Palette.apply(list)
    }
}
