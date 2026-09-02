package com.itguy.assetmanager.ui.generic

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import com.itguy.assetmanager.databinding.ItemSimpleBinding

data class SimpleRow(val title: String, val subtitle: String = "", val payload: Any? = null)

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
