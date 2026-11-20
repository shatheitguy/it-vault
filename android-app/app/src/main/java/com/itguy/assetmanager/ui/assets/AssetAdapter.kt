package com.itguy.assetmanager.ui.assets

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
            // the category's icon in the install's accent, on a tile of it
            val ctx = b.root.context
            val accent = com.itguy.assetmanager.data.Palette.serverColours()?.accent
                ?: androidx.core.content.ContextCompat.getColor(ctx, com.itguy.assetmanager.R.color.accent)
            b.typeIcon.setImageResource(com.itguy.assetmanager.ui.TypeIcons.forType(a.Type))
            b.typeIcon.imageTintList = android.content.res.ColorStateList.valueOf(accent)
            val tileRadius = 11f * ctx.resources.displayMetrics.density
            fun tile(colour: Int) {
                b.typeTile.background = android.graphics.drawable.GradientDrawable().apply {
                    cornerRadius = tileRadius; setColor(colour)
                }
            }
            tile((accent and 0x00FFFFFF) or 0x24000000)
            b.typeTile.clipChildren = false
            // the same picture the web shows: the asset's own photo, else its
            // model's; the type icon until (or unless) one loads
            val pic = com.itguy.assetmanager.data.Looks.pictureFor(a)
            b.typePhoto.visibility = android.view.View.GONE
            b.typeIcon.visibility = android.view.View.VISIBLE
            com.itguy.assetmanager.ui.Images.load(b.typePhoto, pic, 160) { shown ->
                b.typePhoto.visibility = if (shown) android.view.View.VISIBLE else android.view.View.GONE
                b.typeIcon.visibility = if (shown) android.view.View.GONE else android.view.View.VISIBLE
                if (shown) tile(android.graphics.Color.WHITE)
            }
            val logo = com.itguy.assetmanager.data.Looks.brandLogo(a)
            b.brandBadge.visibility = android.view.View.GONE
            com.itguy.assetmanager.ui.Images.load(b.brandBadge, logo, 64) { shown ->
                b.brandBadge.visibility = if (shown) android.view.View.VISIBLE else android.view.View.GONE
            }
            b.root.setOnClickListener { onClick(a) }
            b.root.setOnLongClickListener {
                if (onLongClick == null) false else { onLongClick(a); true }
            }
        }

        /** The table moved to StatusTint, which the ticket and contract
         *  lists now read from too. */
        private fun statusColor(status: String): Int =
            com.itguy.assetmanager.ui.StatusTint.of(status)
    }
}
