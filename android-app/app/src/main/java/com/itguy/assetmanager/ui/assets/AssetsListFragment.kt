package com.itguy.assetmanager.ui.assets

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.core.widget.addTextChangedListener
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.NetworkUtils
import com.itguy.assetmanager.data.OfflineCache
import com.itguy.assetmanager.databinding.FragmentAssetsListBinding
import com.itguy.assetmanager.ui.MainActivity
import com.itguy.assetmanager.ui.Refreshable
import kotlinx.coroutines.launch

class AssetsListFragment : Fragment(), Refreshable {

    private var _b: FragmentAssetsListBinding? = null
    private val b get() = _b!!
    private lateinit var adapter: AssetAdapter
    private var searchJob: kotlinx.coroutines.Job? = null

    /** What the list is narrowed to. Survives a refresh and a tab away. */
    private var filters = AssetFilters()

    /**
     * Every asset the phone last saw, unfiltered -- what the filter sheet
     * offers its options from.
     *
     * It cannot be the list on screen: filter by Location = Warehouse and the
     * only location left in view is Warehouse, so the filter could never be
     * widened again without clearing it first.
     */
    private var allKnown: List<com.itguy.assetmanager.data.model.Asset> = emptyList()

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        _b = FragmentAssetsListBinding.inflate(inflater, container, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        adapter = AssetAdapter(
            onClick = { asset ->
                (activity as? MainActivity)?.showFragment(AssetEditFragment.newInstance(asset.id), "Edit Asset", addToBackStack = true)
            },
            // long-press = the web UI's row action menu (sign / print / QR / …)
            onLongClick = { asset ->
                showAssetActions(
                    asset,
                    onEdit = {
                        (activity as? MainActivity)?.showFragment(
                            AssetEditFragment.newInstance(asset.id), "Edit Asset", addToBackStack = true
                        )
                    },
                    onChanged = { refresh() },
                    onAssign = {
                        (activity as? MainActivity)?.showFragment(
                            AssetEditFragment.newInstance(asset.id, assignNow = true),
                            "Assign Asset", addToBackStack = true
                        )
                    }
                )
            }
        )
        b.assetsRecycler.layoutManager = LinearLayoutManager(requireContext())
        b.assetsRecycler.adapter = adapter

        b.addFab.setOnClickListener {
            (activity as? MainActivity)?.showFragment(AssetEditFragment.newInstance(null), "Add Asset", addToBackStack = true)
        }

        b.filterBtn.setOnClickListener { openFilters() }
        b.filterSummary.setOnClickListener {
            filters = AssetFilters()
            paintFilterChrome()
            refresh()
        }

        b.searchInput.addTextChangedListener {
            searchJob?.cancel()
            searchJob = lifecycleScope.launch {
                kotlinx.coroutines.delay(300)
                load(it?.toString().orEmpty())
            }
        }

        paintFilterChrome()
        load("")
    }

    private fun openFilters() {
        val sheet = AssetFiltersSheet()
        // the cache is the fallback: with no signal there is still a full set
        // of rows to build the options from
        sheet.source = allKnown.ifEmpty { OfflineCache.loadAssets().orEmpty() }
        sheet.current = filters
        sheet.onApply = { chosen ->
            filters = chosen
            paintFilterChrome()
            refresh()
        }
        sheet.show(parentFragmentManager, "asset-filters")
    }

    /** The button's count and the line under it, kept in step with [filters]. */
    private fun paintFilterChrome() {
        val b = _b ?: return
        b.filterBtn.text = if (filters.isEmpty) "FILTER" else "FILTER (${filters.activeCount})"
        val parts = listOfNotNull(
            filters.status?.takeIf { it.isNotBlank() },
            filters.type?.takeIf { it.isNotBlank() },
            filters.location?.takeIf { it.isNotBlank() },
            filters.manufacturer?.takeIf { it.isNotBlank() },
        )
        if (parts.isEmpty()) {
            b.filterSummary.visibility = View.GONE
        } else {
            b.filterSummary.text = "Filtered: ${parts.joinToString(" · ")}  —  tap to clear"
            b.filterSummary.visibility = View.VISIBLE
        }
    }

    /** The filters, applied wherever the rows came from. */
    private fun applyFilters(list: List<com.itguy.assetmanager.data.model.Asset>) =
        if (filters.isEmpty) list else list.filter { filters.matches(it) }

    /** What to say when the list is empty, which depends on why it is. */
    private fun emptyMessage(query: String): String = when {
        !filters.isEmpty && query.isNotBlank() ->
            "No assets match \"$query\" with these filters"
        !filters.isEmpty -> "No assets match these filters"
        query.isNotBlank() -> "No assets match \"$query\""
        else -> "No assets found"
    }

    // guarded: an action sheet or pull-to-refresh can fire this just as the
    // view is going away, and `b` would throw on a destroyed binding
    override fun refresh() { _b?.let { load(it.searchInput.text?.toString().orEmpty()) } }

    private fun load(query: String) {
        // On screen first, from what the phone already has. The fetch below
        // replaces it a moment later; until this, every visit to the list
        // was a blank screen with a spinner on top of data we already held.
        prepaintFromCache(query)
        lifecycleScope.launch {
            b.offlineBanner.visibility = View.GONE
            // Skip straight to cache if there's plainly no network -- avoids
            // sitting through a multi-second connect timeout on every screen.
            if (!NetworkUtils.isOnline(requireContext())) {
                showFromCache(query, null)
                return@launch
            }
            try {
                val resp = ApiClient.api().listAssets(q = query.ifBlank { null })
                if (_b == null) return@launch
                val list = resp.body().orEmpty()
                // the unfiltered set is what the sheet offers its options from
                if (query.isBlank()) allKnown = list
                val shown = applyFilters(list)
                adapter.submit(shown)
                b.emptyText.text = emptyMessage(query)
                b.emptyText.visibility = if (shown.isEmpty()) View.VISIBLE else View.GONE
                if (query.isBlank()) OfflineCache.saveAssets(list)
            } catch (e: Exception) {
                if (_b == null) return@launch
                showFromCache(query, e)
            }
        }
    }

    /**
     * The cached rows, with no claim about being offline -- this runs before
     * we have even tried the server, so "offline" would be a guess. Only
     * [showFromCache] says that, and it only runs once a fetch has failed.
     */
    private fun prepaintFromCache(query: String) {
        if (_b == null) return
        val cached = OfflineCache.loadAssets() ?: return
        if (allKnown.isEmpty()) allKnown = cached
        adapter.submit(applyFilters(filterCached(cached, query)))
    }

    private fun filterCached(cached: List<com.itguy.assetmanager.data.model.Asset>, query: String) =
        if (query.isBlank()) cached else cached.filter {
            it.Name.contains(query, true) || it.Type.contains(query, true) ||
            it.Serial.contains(query, true) || it.Location.contains(query, true) ||
            it.AssetTag.contains(query, true) ||
            // the code a printed tag's QR carries, so a scan resolves
            // from the cache with no network
            (it.PublicCode.isNotBlank() && it.PublicCode.equals(query, true))
        }

    private fun showFromCache(query: String, error: Exception?) {
        if (_b == null) return
        val cached = OfflineCache.loadAssets()
        if (cached != null) {
            if (allKnown.isEmpty()) allKnown = cached
            val filtered = applyFilters(filterCached(cached, query))
            adapter.submit(filtered)
            val age = NetworkUtils.timeAgo(OfflineCache.lastUpdated("assets"))
            b.offlineBanner.text = "📡 Offline — showing cached data from $age"
            b.offlineBanner.visibility = View.VISIBLE
            b.emptyText.text = emptyMessage(query)
            b.emptyText.visibility = if (filtered.isEmpty()) View.VISIBLE else View.GONE
        } else {
            adapter.submit(emptyList())
            b.emptyText.text = if (error != null) "Could not load assets: ${error.message}" else "No connection and nothing cached yet"
            b.emptyText.visibility = View.VISIBLE
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _b = null
    }
}
