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
                    onChanged = { refresh() }
                )
            }
        )
        b.assetsRecycler.layoutManager = LinearLayoutManager(requireContext())
        b.assetsRecycler.adapter = adapter

        b.addFab.setOnClickListener {
            (activity as? MainActivity)?.showFragment(AssetEditFragment.newInstance(null), "Add Asset", addToBackStack = true)
        }

        b.searchInput.addTextChangedListener {
            searchJob?.cancel()
            searchJob = lifecycleScope.launch {
                kotlinx.coroutines.delay(300)
                load(it?.toString().orEmpty())
            }
        }

        load("")
    }

    // guarded: an action sheet or pull-to-refresh can fire this just as the
    // view is going away, and `b` would throw on a destroyed binding
    override fun refresh() { _b?.let { load(it.searchInput.text?.toString().orEmpty()) } }

    private fun load(query: String) {
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
                adapter.submit(list)
                b.emptyText.text = "No assets found"
                b.emptyText.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
                if (query.isBlank()) OfflineCache.saveAssets(list)
            } catch (e: Exception) {
                if (_b == null) return@launch
                showFromCache(query, e)
            }
        }
    }

    private fun showFromCache(query: String, error: Exception?) {
        if (_b == null) return
        val cached = OfflineCache.loadAssets()
        if (cached != null) {
            val filtered = if (query.isBlank()) cached else cached.filter {
                it.Name.contains(query, true) || it.Type.contains(query, true) ||
                it.Serial.contains(query, true) || it.Location.contains(query, true) ||
                it.AssetTag.contains(query, true)
            }
            adapter.submit(filtered)
            val age = NetworkUtils.timeAgo(OfflineCache.lastUpdated("assets"))
            b.offlineBanner.text = "📡 Offline — showing cached data from $age"
            b.offlineBanner.visibility = View.VISIBLE
            b.emptyText.text = "No cached assets match \"$query\""
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
