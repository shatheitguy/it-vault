package com.itguy.assetmanager.ui.heartbeat

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.RecyclerView
import com.itguy.assetmanager.R
import com.itguy.assetmanager.data.model.HbMonitor
import com.itguy.assetmanager.databinding.ItemHeartbeatBinding

class HeartbeatAdapter(
    private val onClick: (HbMonitor) -> Unit
) : RecyclerView.Adapter<HeartbeatAdapter.VH>() {

    private val items = mutableListOf<HbMonitor>()

    fun submit(list: List<HbMonitor>) {
        items.clear()
        items.addAll(list)
        notifyDataSetChanged()
    }

    class VH(val b: ItemHeartbeatBinding) : RecyclerView.ViewHolder(b.root)

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int) =
        VH(ItemHeartbeatBinding.inflate(LayoutInflater.from(parent.context), parent, false))

    override fun getItemCount() = items.size

    override fun onBindViewHolder(holder: VH, position: Int) {
        val m = items[position]
        val b = holder.b
        val ctx = b.root.context
        val st = m.uiStatus
        val color = ContextCompat.getColor(ctx, when (st) {
            "up" -> R.color.hb_up
            "down" -> R.color.hb_down
            "paused" -> R.color.muted
            else -> R.color.hb_pending
        })
        // mutate() matters: the drawable comes from a shared resource, so
        // tinting it in place would recolour every other row's dot too
        b.statusDot.background?.mutate()?.setTint(color)
        b.monName.text = m.label
        val bits = mutableListOf<String>()
        bits += (m.kind ?: "ping").uppercase()
        bits += m.where
        m.last_ms?.let { bits += "$it ms" }
        if (st == "paused") bits += "paused"
        m.tag?.takeIf { it.isNotBlank() }?.let { bits += it }
        b.monTarget.text = bits.joinToString(" · ")
        b.monUptime.text = m.uptime?.let { "${it}%" } ?: "—"
        val err = m.last_error?.takeIf { it.isNotBlank() && st != "up" && st != "paused" }
        b.monError.text = err.orEmpty()
        b.monError.visibility = if (err == null) View.GONE else View.VISIBLE
        b.ecg.setData(m.bars, m.series, st)
        b.root.setOnClickListener { onClick(m) }
    }
}
