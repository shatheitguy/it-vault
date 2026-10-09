package com.itguy.assetmanager.ui.assets

import android.graphics.Color
import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import com.itguy.assetmanager.data.model.Asset
import com.itguy.assetmanager.databinding.ItemAssetBinding

class AssetAdapter(
    private val onClick: (Asset) -> Unit,
    private val onLongClick: ((Asset) -> Unit)? = null
) : RecyclerView.Adapter<AssetAdapter.VH>() {
    private val items = mutableListOf<Asset>()

    fun submit(list: List<Asset>) {
        items.clear(); items.addAll(list)
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val b = ItemAssetBinding.inflate(LayoutInflater.from(parent.context), parent, false)
        return VH(b)
    }

    override fun onBindViewHolder(holder: VH, position: Int) = holder.bind(items[position], onClick, onLongClick)

    override fun getItemCount() = items.size

    class VH(private val b: ItemAssetBinding) : RecyclerView.ViewHolder(b.root) {
        fun bind(a: Asset, onClick: (Asset) -> Unit, onLongClick: ((Asset) -> Unit)?) {
            b.assetName.text = a.Name.ifBlank { "(unnamed)" }
            val meta = listOfNotNull(
                "ID: ${a.AssetTag.ifBlank { a.id ?: "" }}".takeIf { a.AssetTag.isNotBlank() || a.id != null },
                a.Type.ifBlank { null },
                a.Serial.ifBlank { null },
                a.Location.ifBlank { null }
            ).joinToString(" · ")
            b.assetMeta.text = meta
            // The pill wears the status's colour: the dot for scanning a
            // column, the pill for reading one row. Both come from the same
            // value, so they cannot drift apart.
            val tint = statusColor(a.Status)
            b.assetStatus.text = a.Status.replace("-", " ")
            b.assetStatus.setTextColor(tint)
            b.assetStatus.background = android.graphics.drawable.GradientDrawable().apply {
                cornerRadius = 100f
                // a tenth of the colour: enough to say which, never enough to
                // compete with the name beside it
                setColor((tint and 0x00FFFFFF) or 0x1A000000)
            }
            b.statusDot.background = android.graphics.drawable.GradientDrawable().apply {
                shape = android.graphics.drawable.GradientDrawable.OVAL
                setColor(tint)
            }
            b.root.setOnClickListener { onClick(a) }
            b.root.setOnLongClickListener {
                if (onLongClick == null) false else { onLongClick(a); true }
            }
        }

        /**
         * One colour per state, darkened for a light surface.
         *
         * The old set was picked for a dark theme -- a neon green and a pale
         * amber on white are a pill nobody can read, and the pill now carries
         * text rather than being a coloured dash.
         */
        private fun statusColor(status: String): Int = when (status) {
            "Available" -> Color.parseColor("#0F9D63")
            "Checked-Out" -> Color.parseColor("#0E8FB3")
            "Under-Maintenance" -> Color.parseColor("#B0761A")
            "Retired" -> Color.parseColor("#6B7280")
            "Lost/Stolen" -> Color.parseColor("#D24545")
            else -> Color.parseColor("#667085")
        }
    }
}
