package com.itguy.assetmanager.ui.generic

import android.graphics.drawable.GradientDrawable
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import com.itguy.assetmanager.databinding.ItemSimpleBinding

/**
 * A row in one of the lists that is not the asset list.
 *
 * [trailing] and [tint] are what let a ticket or a contract carry its state
 * the way an asset does -- a coloured pill on the right and a matching dot on
 * the left. A row that has no state leaves them out and loses both, which is
 * right for a list of departments.
 *
 * They are declared after [payload] on purpose: every existing caller passes
 * title, subtitle and payload positionally.
 */
data class SimpleRow(
    val title: String,
    val subtitle: String = "",
    val payload: Any? = null,
    val trailing: String? = null,
    val tint: Int? = null,
)

/** Reusable title/subtitle row adapter used across Directory and the generic reference-list screens. */
class SimpleAdapter(
    private val onClick: ((SimpleRow) -> Unit)? = null,
    private val onDelete: ((SimpleRow) -> Unit)? = null
) : RecyclerView.Adapter<SimpleAdapter.VH>() {
    private val items = mutableListOf<SimpleRow>()

    fun submit(list: List<SimpleRow>) { items.clear(); items.addAll(list); notifyDataSetChanged() }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val b = ItemSimpleBinding.inflate(LayoutInflater.from(parent.context), parent, false)
        return VH(b)
    }

    override fun onBindViewHolder(holder: VH, position: Int) {
        val row = items[position]
        holder.b.lineTitle.text = row.title
        holder.b.lineSubtitle.text = row.subtitle
        holder.b.lineSubtitle.visibility = if (row.subtitle.isBlank()) View.GONE else View.VISIBLE

        // the pill and the dot are one decision: both come from `tint`, so a
        // row can never show a green dot beside an amber pill
        val tint = row.tint
        if (!row.trailing.isNullOrBlank() && tint != null) {
            holder.b.lineStatus.visibility = View.VISIBLE
            holder.b.lineStatus.text = row.trailing
            holder.b.lineStatus.setTextColor(tint)
            holder.b.lineStatus.background = GradientDrawable().apply {
                cornerRadius = 100f
                // a tenth of the colour: enough to say which, never enough to
                // compete with the name beside it
                setColor((tint and 0x00FFFFFF) or 0x1A000000)
            }
        } else {
            holder.b.lineStatus.visibility = View.GONE
        }
        if (tint != null) {
            holder.b.lineDot.visibility = View.VISIBLE
            holder.b.lineDot.background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(tint)
            }
        } else {
            holder.b.lineDot.visibility = View.GONE
        }

        holder.b.root.setOnClickListener { onClick?.invoke(row) }
        if (onDelete != null) {
            holder.b.deleteBtn.visibility = View.VISIBLE
            holder.b.deleteBtn.setOnClickListener { onDelete.invoke(row) }
        } else {
            holder.b.deleteBtn.visibility = View.GONE
        }
    }

    override fun getItemCount() = items.size

    class VH(val b: ItemSimpleBinding) : RecyclerView.ViewHolder(b.root)
}
