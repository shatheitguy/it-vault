package com.itguy.assetmanager.ui.contracts

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.TextView
import androidx.core.widget.addTextChangedListener
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.OfflineCache
import com.itguy.assetmanager.data.model.Contract
import com.itguy.assetmanager.databinding.FragmentContractsListBinding
import com.itguy.assetmanager.ui.MainActivity
import com.itguy.assetmanager.ui.Refreshable
import com.itguy.assetmanager.ui.generic.SimpleAdapter
import com.itguy.assetmanager.ui.generic.SimpleRow
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Contracts, AMC (Annual Maintenance Contracts) with outside companies,
 * licenses, subscriptions, warranties and support agreements -- same
 * stat-row + list+form pattern as the Assets screen. */
class ContractsListFragment : Fragment(), Refreshable {
    private var _b: FragmentContractsListBinding? = null
    private val b get() = _b!!
    private var all: List<Contract> = emptyList()
    private var TYPES = listOf("All types", "AMC", "License", "Subscription", "Warranty", "Support", "Lease", "Other")

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        _b = FragmentContractsListBinding.inflate(inflater, container, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        b.statTotal.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statLabel).text = "TOTAL"
        b.statAmc.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statLabel).text = "AMC"
        b.statLicense.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statLabel).text = "LICENSES"
        b.statSub.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statLabel).text = "SUBSCRIPTIONS"
        b.statExpiring.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statLabel).text = "EXPIRING ≤30D"

        b.assetsRecycler.layoutManager = LinearLayoutManager(requireContext())
        b.addFab.setOnClickListener {
            (activity as? MainActivity)?.showFragment(ContractEditFragment.newInstance(0), "Add Contract", addToBackStack = true)
        }
        b.typeFilter.adapter = ArrayAdapter(requireContext(), android.R.layout.simple_spinner_dropdown_item, TYPES)
        b.typeFilter.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) { render(b.searchInput.text?.toString().orEmpty()) }
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {}
        }
        b.searchInput.addTextChangedListener { render(it?.toString().orEmpty()) }
        load()
    }

    override fun refresh() = load()

    private fun load() {
        lifecycleScope.launch {
            try {
                all = ApiClient.api().contracts().body().orEmpty()
                OfflineCache.saveContracts(all)
                val types = ApiClient.api().contractTypes().body().orEmpty().map { it.name }
                if (types.isNotEmpty() && _b != null) {
                    TYPES = listOf("All types") + types
                    val prev = b.typeFilter.selectedItemPosition.let { TYPES.getOrNull(it) } ?: "All types"
                    b.typeFilter.adapter = ArrayAdapter(requireContext(), android.R.layout.simple_spinner_dropdown_item, TYPES)
                    b.typeFilter.setSelection(TYPES.indexOf(prev).coerceAtLeast(0))
                }
                if (_b != null) { render(b.searchInput.text?.toString().orEmpty()); renderStats() }
            } catch (e: Exception) {
                if (_b == null) return@launch
                val cached = OfflineCache.loadContracts()
                if (cached != null) {
                    all = cached
                    render(b.searchInput.text?.toString().orEmpty())
                    renderStats()
                    b.emptyText.text = "Offline — showing cached data"
                } else {
                    b.emptyText.text = "Could not load contracts: ${e.message}"; b.emptyText.visibility = View.VISIBLE
                }
            }
        }
    }

    private fun renderStats() {
        val fmt = SimpleDateFormat("yyyy-MM-dd", Locale.US)
        val today = Date()
        val in30 = Date(today.time + 30L * 24 * 60 * 60 * 1000)
        val expiring = all.count { c ->
            if (c.end_date.isBlank()) return@count false
            val d = try { fmt.parse(c.end_date) } catch (e: Exception) { null } ?: return@count false
            !d.before(today) && !d.after(in30)
        }
        b.statTotal.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statValue).text = all.size.toString()
        b.statAmc.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statValue).text = all.count { it.type == "AMC" }.toString()
        b.statLicense.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statValue).text = all.count { it.type == "License" }.toString()
        b.statSub.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statValue).text = all.count { it.type == "Subscription" }.toString()
        b.statExpiring.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statValue).text = expiring.toString()
    }

    private fun render(query: String) {
        val typeSel = TYPES.getOrNull(b.typeFilter.selectedItemPosition) ?: "All types"
        var filtered = if (typeSel == "All types") all else all.filter { it.type == typeSel }
        if (query.isNotBlank()) {
            filtered = filtered.filter {
                it.name.contains(query, true) || it.vendor.contains(query, true) || it.type.contains(query, true)
            }
        }
        val adapter = SimpleAdapter(onClick = { row ->
            val c = row.payload as Contract
            (activity as? MainActivity)?.showFragment(ContractEditFragment.newInstance(c.id), "Edit Contract", addToBackStack = true)
        })
        b.assetsRecycler.adapter = adapter
        adapter.submit(filtered.map { c ->
            SimpleRow("${c.name} · ${c.type}", listOfNotNull(c.vendor.ifBlank { null }, "ends ${c.end_date.ifBlank { "—" }}").joinToString(" · "), c)
        })
        b.emptyText.visibility = if (filtered.isEmpty()) View.VISIBLE else View.GONE
        b.emptyText.text = "No contracts yet"
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
