package com.itguy.assetmanager.ui.assets

import android.graphics.Color
import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import com.itguy.assetmanager.data.model.Asset
import com.itguy.assetmanager.databinding.ItemAssetBinding

class AssetAdapter(private val onClick: (Asset) -> Unit) : RecyclerView.Adapter<AssetAdapter.VH>() {
    private val items = mutableListOf<Asset>()

    fun submit(list: List<Asset>) {
        items.clear(); items.addAll(list)
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val b = ItemAssetBinding.inflate(LayoutInflater.from(parent.context), parent, false)
        return VH(b)
    }

    override fun onBindViewHolder(holder: VH, position: Int) = holder.bind(items[position], onClick)

    override fun getItemCount() = items.size

    class VH(private val b: ItemAssetBinding) : RecyclerView.ViewHolder(b.root) {
        fun bind(a: Asset, onClick: (Asset) -> Unit) {
            b.assetName.text = a.Name.ifBlank { "(unnamed)" }
            val meta = listOfNotNull(
                "ID: ${a.AssetTag.ifBlank { a.id ?: "" }}".takeIf { a.AssetTag.isNotBlank() || a.id != null },
                a.Type.ifBlank { null },
                a.Serial.ifBlank { null },
                a.Location.ifBlank { null }
            ).joinToString(" · ")
            b.assetMeta.text = meta
            b.assetStatus.text = a.Status
            b.statusDot.setBackgroundColor(statusColor(a.Status))
            b.root.setOnClickListener { onClick(a) }
        }

        private fun statusColor(status: String): Int = when (status) {
            "Available" -> Color.parseColor("#2ECC71")
            "Checked-Out" -> Color.parseColor("#3BC9DB")
            "Under-Maintenance" -> Color.parseColor("#FFB84D")
            "Retired" -> Color.parseColor("#FF3B30")
            "Lost/Stolen" -> Color.parseColor("#FF3B30")
            else -> Color.parseColor("#8A93A6")
        }
    }
}
