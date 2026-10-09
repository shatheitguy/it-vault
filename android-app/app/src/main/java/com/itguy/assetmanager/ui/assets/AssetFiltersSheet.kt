package com.itguy.assetmanager.ui.assets

import android.os.Bundle
import android.view.Gravity
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import com.google.android.material.bottomsheet.BottomSheetDialogFragment
import com.itguy.assetmanager.R
import com.itguy.assetmanager.data.model.Asset

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
        val pad = (16 * resources.displayMetrics.density).toInt()
        picked = current

        val root = LinearLayout(ctx).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, pad / 2, 0, pad)
        }

        root.addView(TextView(ctx).apply {
            text = "Filter assets"
            textSize = 15f
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setPadding(pad, pad / 2, pad, pad / 2)
            setTextColor(ContextCompat.getColor(ctx, R.color.text))
        })

        // Each row shows what it is set to, so the sheet reads as a summary of
        // the current view rather than four identical buttons.
        val rows = mutableListOf<Pair<TextView, () -> Unit>>()

        fun options(pick: (Asset) -> String): List<String> =
            source.map(pick).map { it.trim() }.filter { it.isNotBlank() }
                .distinctBy { it.lowercase() }.sortedBy { it.lowercase() }

        fun row(label: String, values: List<String>, get: () -> String?, set: (String?) -> Unit) {
            val view = TextView(ctx).apply {
                textSize = 16f
                gravity = Gravity.CENTER_VERTICAL
                setPadding(pad, pad, pad, pad)
                setTextColor(ContextCompat.getColor(ctx, R.color.text))
                isClickable = true
                setBackgroundResource(R.drawable.nav_item_bg)
            }
            fun paint() {
                val v = get()
                view.text = if (v.isNullOrBlank()) "$label:  Any" else "$label:  $v"
            }
            paint()
            view.setOnClickListener {
                if (values.isEmpty()) {
                    android.widget.Toast.makeText(
                        ctx, "Nothing to filter by yet -- no asset has a $label",
                        android.widget.Toast.LENGTH_SHORT
                    ).show()
                    return@setOnClickListener
                }
                // "Any" first, then what the data actually contains
                val items = (listOf("Any") + values).toTypedArray()
                val checked = get()?.let { cur ->
                    values.indexOfFirst { it.equals(cur, true) }.let { if (it < 0) 0 else it + 1 }
                } ?: 0
                com.itguy.assetmanager.ui.BrandDialog(ctx)
                    .setTitle(label)
                    .setSingleChoiceItems(items, checked) { dlg, which ->
                        set(if (which == 0) null else items[which])
                        paint()
                        dlg.dismiss()
                    }
                    .setNegativeButton("Cancel", null)
                    .show()
            }
            root.addView(view)
            rows += view to ::paint
        }

        row("Status", options { it.Status }, { picked.status }) { picked = picked.copy(status = it) }
        row("Category", options { it.Type }, { picked.type }) { picked = picked.copy(type = it) }
        row("Location", options { it.Location }, { picked.location }) { picked = picked.copy(location = it) }
        row("Manufacturer", options { it.Manufacturer }, { picked.manufacturer }) {
            picked = picked.copy(manufacturer = it)
        }

        val buttons = LinearLayout(ctx).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(pad, pad, pad, 0)
        }
        buttons.addView(TextView(ctx).apply {
            text = "CLEAR ALL"
            textSize = 14f
            gravity = Gravity.CENTER
            setPadding(pad, pad, pad, pad)
            setTextColor(ContextCompat.getColor(ctx, R.color.muted))
            isClickable = true
            setBackgroundResource(R.drawable.nav_item_bg)
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            setOnClickListener {
                picked = AssetFilters()
                rows.forEach { (_, repaint) -> repaint() }
            }
        })
        buttons.addView(TextView(ctx).apply {
            text = "APPLY"
            textSize = 14f
            gravity = Gravity.CENTER
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setPadding(pad, pad, pad, pad)
            setTextColor(ContextCompat.getColor(ctx, R.color.on_accent))
            setBackgroundColor(ContextCompat.getColor(ctx, R.color.accent))
            isClickable = true
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
                .apply { marginStart = pad / 2 }
            setOnClickListener {
                onApply?.invoke(picked)
                dismiss()
            }
        })
        root.addView(buttons)

        return root
    }
}
