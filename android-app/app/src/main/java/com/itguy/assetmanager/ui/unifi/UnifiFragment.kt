package com.itguy.assetmanager.ui.unifi

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.databinding.FragmentDirectoryBinding
import com.itguy.assetmanager.ui.Refreshable
import com.itguy.assetmanager.ui.generic.SimpleAdapter
import com.itguy.assetmanager.ui.generic.SimpleRow
import kotlinx.coroutines.launch

class UnifiFragment : Fragment(), Refreshable {
    private var _b: FragmentDirectoryBinding? = null
    private val b get() = _b!!
    private var tab = 0 // 0=devices 1=clients

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        _b = FragmentDirectoryBinding.inflate(inflater, container, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        b.recycler.layoutManager = LinearLayoutManager(requireContext())
        b.searchWrap.visibility = View.GONE
        b.addFab.visibility = View.GONE
        b.tabs.visibility = View.VISIBLE
        b.tabs.addTab(b.tabs.newTab().setText("Devices"))
        b.tabs.addTab(b.tabs.newTab().setText("Active Clients"))
        b.tabs.addOnTabSelectedListener(object : com.google.android.material.tabs.TabLayout.OnTabSelectedListener {
            override fun onTabSelected(t: com.google.android.material.tabs.TabLayout.Tab) { tab = t.position; load() }
            override fun onTabUnselected(t: com.google.android.material.tabs.TabLayout.Tab) {}
            override fun onTabReselected(t: com.google.android.material.tabs.TabLayout.Tab) {}
        })
        load()
    }

    override fun refresh() = load()

    private fun load() {
        lifecycleScope.launch {
            try {
                val adapter = SimpleAdapter()
                if (_b == null) return@launch
                b.recycler.adapter = adapter
                if (tab == 0) {
                    val resp = ApiClient.api().unifiDevices().body()
                    if (resp?.error == "not_configured") {
                        showMessage("UniFi Controller not configured -- set it up in Settings")
                    } else if (resp?.error != null) {
                        showMessage("✕ ${resp.error}")
                    } else {
                        val list = resp?.devices.orEmpty()
                        adapter.submit(list.map { SimpleRow(it.name ?: it.mac ?: "?", "${it.type} · ${it.ip} · ${if (it.online) "Online" else "Offline"} · ${it.num_sta} client(s)") })
                        b.emptyText.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
                        b.emptyText.text = "No devices"
                    }
                } else {
                    val resp = ApiClient.api().unifiClients().body()
                    if (resp?.error == "not_configured") {
                        showMessage("UniFi Controller not configured -- set it up in Settings")
                    } else if (resp?.error != null) {
                        showMessage("✕ ${resp.error}")
                    } else {
                        val list = resp?.clients.orEmpty()
                        adapter.submit(list.map { SimpleRow(it.hostname ?: it.mac ?: "?", "${it.ip} · ${it.network ?: ""} · ${if (it.is_wired) "Wired" else "Wi-Fi " + (it.essid ?: "")}") })
                        b.emptyText.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
                        b.emptyText.text = "No active clients"
                    }
                }
            } catch (e: Exception) {
                if (_b != null) showMessage("Could not load: ${e.message}")
            }
        }
    }

    private fun showMessage(msg: String) {
        if (_b == null) return
        b.recycler.adapter = SimpleAdapter()
        b.emptyText.text = msg
        b.emptyText.visibility = View.VISIBLE
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
