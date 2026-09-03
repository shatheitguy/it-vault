package com.itguy.assetmanager.ui.dashboard

import android.graphics.Color
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.OfflineCache
import com.itguy.assetmanager.databinding.FragmentDashboardBinding
import com.itguy.assetmanager.ui.MainActivity
import com.itguy.assetmanager.ui.Refreshable
import com.itguy.assetmanager.ui.assets.AssetEditFragment
import com.itguy.assetmanager.ui.tickets.TicketDetailFragment
import kotlinx.coroutines.launch

/** Mirrors the web app's Dashboard exactly: KPI row, then the same five
 * widgets in the same order (Asset Status, Top Asset Types, Recent Assets,
 * Open Tickets, Recent Activity), each pulling live from the server. */
class DashboardFragment : Fragment(), Refreshable {
    private var _b: FragmentDashboardBinding? = null
    private val b get() = _b!!

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        _b = FragmentDashboardBinding.inflate(inflater, container, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        b.statTotal.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statLabel).text = "TOTAL ASSETS"
        b.statOut.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statLabel).text = "CHECKED OUT"
        b.statMaint.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statLabel).text = "MAINTENANCE"
        b.statDue.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statLabel).text = "CHECKOUTS DUE SOON"
        b.statWarr.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statLabel).text = "WARRANTY EXPIRING"
        refresh()
    }

    override fun refresh() {
        val bb = _b ?: return
        bb.dashProgress.visibility = View.VISIBLE
        lifecycleScope.launch {
            try {
                var d = try {
                    val resp = ApiClient.api().dashboard()
                    resp.body()?.also { if (resp.isSuccessful) OfflineCache.saveDashboard(it) }
                } catch (e: Exception) { null }
                if (d == null) d = OfflineCache.loadDashboard()
                if (_b != null && d != null) {
                    b.statTotal.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statValue).text = d.total.toString()
                    b.statOut.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statValue).text = d.checked_out.toString()
                    b.statMaint.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statValue).text = d.maintenance.toString()
                    b.statDue.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statValue).text = d.due_soon.toString()
                    b.statWarr.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statValue).text = d.warranty_expiring.toString()

                    renderBars(b.statusBars, (d.by_status ?: emptyMap()), ::statusColor)
                    renderBars(b.typeBars, (d.by_type ?: emptyMap())) { resources.getColor(com.itguy.assetmanager.R.color.accent, null) }
                    renderBars(b.contractsBars, (d.contracts_by_type ?: emptyMap())) { resources.getColor(com.itguy.assetmanager.R.color.accent2, null) }
                    b.contractsExpiring.removeAllViews()
                    val expiring = d.expiring_contracts ?: emptyList()
                    if (expiring.isEmpty()) emptyRow(b.contractsExpiring, "No contracts expiring soon")
                    else expiring.forEach { ec ->
                        addTwoLineRow(b.contractsExpiring, "${ec.name} · ${ec.type ?: "—"}", "${ec.vendor ?: "—"} · ends ${ec.end_date ?: "—"} · ${ec.days_left}d left") {
                            (activity as? MainActivity)?.showFragment(com.itguy.assetmanager.ui.contracts.ContractEditFragment.newInstance(ec.id), "Edit Contract", addToBackStack = true)
                        }
                    }
                }
            } catch (e: Exception) {}

            try {
                val list = ApiClient.api().listAssets(order = "recent").body().orEmpty().take(12)
                if (_b != null) {
                    b.recentAssets.removeAllViews()
                    if (list.isEmpty()) emptyRow(b.recentAssets, "No assets")
                    else list.forEach { a ->
                        addTwoLineRow(b.recentAssets, a.Name.ifBlank { "(unnamed)" }, "${a.Type} · ${a.Serial} · ${a.Status}") {
                            (activity as? MainActivity)?.showFragment(AssetEditFragment.newInstance(a.id), "Edit Asset", addToBackStack = true)
                        }
                    }
                }
            } catch (e: Exception) {}

            try {
                val open = ApiClient.api().listTickets().body().orEmpty().filter { it.status !in listOf("Resolved", "Closed") }.take(12)
                if (_b != null) {
                    b.openTickets.removeAllViews()
                    if (open.isEmpty()) emptyRow(b.openTickets, "No open tickets")
                    else open.forEach { t ->
                        addTwoLineRow(b.openTickets, "${t.code ?: ""} · ${t.subject}", t.status) {
                            (activity as? MainActivity)?.showFragment(TicketDetailFragment.newInstance(t.id), "Ticket ${t.code ?: ""}", addToBackStack = true)
                        }
                    }
                }
            } catch (e: Exception) {}

            try {
                val audit = ApiClient.api().audit().body().orEmpty().take(10)
                if (_b != null) {
                    b.activityFeed.removeAllViews()
                    if (audit.isEmpty()) emptyRow(b.activityFeed, "No activity")
                    else audit.forEach { a ->
                        addTwoLineRow(b.activityFeed, "${a.actor ?: "system"} ${a.action ?: ""}", "${a.detail ?: ""}  ·  ${a.ts}", null)
                    }
                }
            } catch (e: Exception) {}

            _b?.dashProgress?.visibility = View.GONE
        }
    }

    private fun statusColor(s: String): Int = when (s) {
        "Available" -> Color.parseColor("#2ECC71")
        "Checked-Out" -> Color.parseColor("#3BC9DB")
        "Under-Maintenance" -> Color.parseColor("#FFB84D")
        "Retired" -> Color.parseColor("#FF3B30")
        else -> Color.parseColor("#8A93A6")
    }

    /** Reproduces the web app's renderBars(): sorted desc by count, each row a label+count line over a proportional colored bar. */
    private fun renderBars(container: LinearLayout, data: Map<String, Int>, colorFor: (String) -> Int) {
        container.removeAllViews()
        val entries = data.toList().sortedByDescending { it.second }
        if (entries.isEmpty()) { emptyRow(container, "No data yet"); return }
        val max = (entries.maxOfOrNull { it.second } ?: 1).coerceAtLeast(1)
        val density = resources.displayMetrics.density
        for ((label, count) in entries) {
            val row = LinearLayout(requireContext()).apply { orientation = LinearLayout.VERTICAL; setPadding(0, 0, 0, (10 * density).toInt()) }
            val top = LinearLayout(requireContext()).apply { orientation = LinearLayout.HORIZONTAL }
            val labelTv = TextView(requireContext()).apply { text = label; setTextColor(resources.getColor(com.itguy.assetmanager.R.color.text, null)); textSize = 13f
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f) }
            val countTv = TextView(requireContext()).apply { text = count.toString(); setTextColor(resources.getColor(com.itguy.assetmanager.R.color.text, null)); textSize = 13f; setTypeface(typeface, android.graphics.Typeface.BOLD) }
            top.addView(labelTv); top.addView(countTv)
            val track = LinearLayout(requireContext()).apply {
                layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, (5 * density).toInt()).also { it.topMargin = (5 * density).toInt() }
                setBackgroundColor(Color.parseColor("#1A222E"))
            }
            val fillWidthPct = (count.toFloat() / max.toFloat())
            val fill = View(requireContext())
            fill.setBackgroundColor(colorFor(label))
            track.addView(fill, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, fillWidthPct))
            track.addView(View(requireContext()), LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f - fillWidthPct))
            row.addView(top); row.addView(track)
            container.addView(row)
        }
    }

    private fun addTwoLineRow(container: LinearLayout, title: String, subtitle: String, onClick: (() -> Unit)?) {
        val density = resources.displayMetrics.density
        val row = LinearLayout(requireContext()).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, (6 * density).toInt(), 0, (6 * density).toInt())
            if (onClick != null) { isClickable = true; isFocusable = true; setOnClickListener { onClick() } }
        }
        val t = TextView(requireContext()).apply { text = title; setTextColor(resources.getColor(com.itguy.assetmanager.R.color.text, null)); textSize = 13.5f }
        val s = TextView(requireContext()).apply { text = subtitle; setTextColor(resources.getColor(com.itguy.assetmanager.R.color.muted, null)); textSize = 11.5f }
        row.addView(t); row.addView(s)
        container.addView(row)
    }

    private fun emptyRow(container: LinearLayout, text: String) {
        val tv = TextView(requireContext())
        tv.text = text
        tv.setTextColor(resources.getColor(com.itguy.assetmanager.R.color.muted, null))
        tv.textSize = 13f
        container.addView(tv)
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _b = null
    }
}
