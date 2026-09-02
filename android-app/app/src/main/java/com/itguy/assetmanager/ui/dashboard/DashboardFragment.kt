package com.itguy.assetmanager.ui.dashboard

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.databinding.FragmentDashboardBinding
import com.itguy.assetmanager.ui.Refreshable
import kotlinx.coroutines.launch

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
                val resp = ApiClient.api().dashboard()
                val d = resp.body()
                if (_b == null) return@launch
                if (resp.isSuccessful && d != null) {
                    b.statTotal.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statValue).text = d.total.toString()
                    b.statOut.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statValue).text = d.checked_out.toString()
                    b.statMaint.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statValue).text = d.maintenance.toString()
                    b.statDue.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statValue).text = d.due_soon.toString()
                    b.statWarr.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statValue).text = d.warranty_expiring.toString()

                    b.statusList.removeAllViews()
                    val byStatus = (d.by_status ?: emptyMap()).toList().sortedByDescending { it.second }
                    if (byStatus.isEmpty()) {
                        addStatusRow("No data yet", "")
                    } else {
                        for ((status, count) in byStatus) addStatusRow(status, count.toString())
                    }
                }
            } catch (e: Exception) {
                if (_b != null) addStatusRow("Could not load dashboard", e.message ?: "")
            } finally {
                _b?.dashProgress?.visibility = View.GONE
            }
        }
    }

    private fun addStatusRow(label: String, value: String) {
        val row = TextView(requireContext())
        row.text = if (value.isBlank()) label else "$label — $value"
        row.setTextColor(resources.getColor(com.itguy.assetmanager.R.color.text, null))
        row.setPadding(0, 10, 0, 10)
        b.statusList.addView(row)
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _b = null
    }
}
