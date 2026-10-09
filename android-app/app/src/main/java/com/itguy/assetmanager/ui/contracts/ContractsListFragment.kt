package com.itguy.assetmanager.ui.contracts

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.widget.addTextChangedListener
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.NetworkUtils
import com.itguy.assetmanager.data.OfflineCache
import com.itguy.assetmanager.data.model.Contract
import com.itguy.assetmanager.databinding.FragmentContractsListBinding
import com.itguy.assetmanager.ui.MainActivity
import com.itguy.assetmanager.ui.Pills
import com.itguy.assetmanager.ui.Refreshable
import com.itguy.assetmanager.ui.StatusTint
import com.itguy.assetmanager.ui.generic.SimpleAdapter
import com.itguy.assetmanager.ui.generic.SimpleRow
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Contracts, AMC (Annual Maintenance Contracts) with outside companies,
 * licenses, subscriptions, warranties and support agreements -- same
 * search + filter + list+form pattern as the Assets screen. */
class ContractsListFragment : Fragment(), Refreshable {
    private var _b: FragmentContractsListBinding? = null
    private val b get() = _b!!
    private var all: List<Contract> = emptyList()
    private var types = listOf("AMC", "License", "Subscription", "Warranty", "Support", "Lease", "Other")
    /** "" means every type. */
    private var chosenType = ""

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        _b = FragmentContractsListBinding.inflate(inflater, container, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        b.assetsRecycler.layoutManager = LinearLayoutManager(requireContext())
        b.addFab.setOnClickListener {
            (activity as? MainActivity)?.showFragment(ContractEditFragment.newInstance(0), "Add Contract", addToBackStack = true)
        }
        b.searchInput.addTextChangedListener { render() }
        buildTypePills()
        load()
    }

    override fun refresh() = load()

    /**
     * The filter row: "All 23", "AMC 4", "License 9"…
     *
     * A type with nothing in it is left out. The old spinner listed every
     * type the server knows about whether or not a single contract used it,
     * so choosing one was often a way to empty the screen.
     */
    private fun buildTypePills() {
        if (_b == null) return
        val ctx = requireContext()
        val present = types.filter { t -> all.any { it.type == t } }
        val labels = listOf("" to "All") + present.map { it to it }
        if (chosenType !in labels.map { it.first }) chosenType = ""

        b.typePills.removeAllViews()
        val views = mutableListOf<TextView>()
        labels.forEach { (value, label) ->
            val count = if (value.isBlank()) all.size else all.count { it.type == value }
            val pill = TextView(ctx).apply {
                text = "$label  $count"
                textSize = 12.5f
                val d = resources.displayMetrics.density
                setPadding((16 * d).toInt(), (8 * d).toInt(), (16 * d).toInt(), (8 * d).toInt())
                isClickable = true
                isFocusable = true
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT
                ).also { it.rightMargin = (8 * d).toInt() }
                setOnClickListener {
                    if (chosenType == value) return@setOnClickListener
                    chosenType = value
                    Pills.paintRow(views, labels.indexOfFirst { it.first == value })
                    render()
                }
            }
            views.add(pill)
            b.typePills.addView(pill)
        }
        Pills.paintRow(views, labels.indexOfFirst { it.first == chosenType }.coerceAtLeast(0))
    }

    private fun load() {
        // what the phone already has, before the server is asked
        OfflineCache.loadContracts()?.let {
            all = it
            buildTypePills()
            render()
        }
        lifecycleScope.launch {
            b.offlineBanner.visibility = View.GONE
            if (!NetworkUtils.isOnline(requireContext())) {
                showFromCache(null)
                return@launch
            }
            try {
                all = ApiClient.api().contracts().body().orEmpty()
                OfflineCache.saveContracts(all)
                val served = ApiClient.api().contractTypes().body().orEmpty().map { it.name }
                if (served.isNotEmpty()) types = served
                if (_b != null) { buildTypePills(); render() }
            } catch (e: Exception) {
                if (_b == null) return@launch
                showFromCache(e)
            }
        }
    }

    private fun showFromCache(error: Exception?) {
        if (_b == null) return
        val cached = OfflineCache.loadContracts()
        if (cached != null) {
            all = cached
            buildTypePills()
            render()
            val age = NetworkUtils.timeAgo(OfflineCache.lastUpdated("contracts"))
            b.offlineBanner.text = "📡 Offline — showing cached data from $age"
            b.offlineBanner.visibility = View.VISIBLE
        } else {
            b.emptyText.text = if (error != null) "Could not load contracts: ${error.message}" else "No connection and nothing cached yet"
            b.emptyText.visibility = View.VISIBLE
        }
    }

    /** Days from today to [endDate], or null if it has no usable end date. */
    private fun daysLeft(endDate: String): Long? {
        if (endDate.isBlank()) return null
        val d = try { SimpleDateFormat("yyyy-MM-dd", Locale.US).parse(endDate) } catch (e: Exception) { null }
            ?: return null
        return (d.time - Date().time) / (24L * 60 * 60 * 1000)
    }

    private fun render() {
        if (_b == null) return
        val query = b.searchInput.text?.toString().orEmpty().trim()
        var filtered = if (chosenType.isBlank()) all else all.filter { it.type == chosenType }
        if (query.isNotBlank()) {
            filtered = filtered.filter {
                it.name.contains(query, true) || it.vendor.contains(query, true) || it.type.contains(query, true)
            }
        }
        // soonest to expire first: a contract list is read to find out what is
        // about to lapse, and the one that lapses first was at the bottom
        filtered = filtered.sortedBy { daysLeft(it.end_date) ?: Long.MAX_VALUE }

        val adapter = SimpleAdapter(onClick = { row ->
            val c = row.payload as Contract
            (activity as? MainActivity)?.showFragment(ContractEditFragment.newInstance(c.id), "Edit Contract", addToBackStack = true)
        })
        b.assetsRecycler.adapter = adapter
        adapter.submit(filtered.map { c ->
            val left = daysLeft(c.end_date)
            SimpleRow(
                title = c.name,
                subtitle = listOfNotNull(
                    c.type.ifBlank { null },
                    c.vendor.ifBlank { null },
                    "ends ${c.end_date.ifBlank { "—" }}",
                ).joinToString(" · "),
                payload = c,
                // how long is left is the one thing worth seeing from the list
                trailing = when {
                    left == null -> null
                    left < 0 -> "expired"
                    left == 0L -> "today"
                    else -> "${left}d"
                },
                tint = left?.let { StatusTint.forDaysLeft(it) },
            )
        })

        // the headline the five stat cards were really there for
        val soon = all.count { c -> daysLeft(c.end_date)?.let { it in 0..30 } == true }
        if (soon > 0) {
            b.expiringNote.text = "$soon ${if (soon == 1) "contract expires" else "contracts expire"} within 30 days"
            b.expiringNote.setTextColor(StatusTint.forDaysLeft(30))
            b.expiringNote.visibility = View.VISIBLE
        } else {
            b.expiringNote.visibility = View.GONE
        }

        b.emptyText.text = if (query.isNotBlank()) "Nothing matches “$query”" else "No contracts yet"
        b.emptyText.visibility = if (filtered.isEmpty()) View.VISIBLE else View.GONE
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
