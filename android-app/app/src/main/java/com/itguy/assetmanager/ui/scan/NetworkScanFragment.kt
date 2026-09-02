package com.itguy.assetmanager.ui.scan

import android.app.AlertDialog
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.model.ScanDevice
import com.itguy.assetmanager.databinding.FragmentNetworkScanBinding
import com.itguy.assetmanager.ui.MainActivity
import com.itguy.assetmanager.ui.Refreshable
import com.itguy.assetmanager.ui.assets.AssetEditFragment
import com.itguy.assetmanager.ui.generic.SimpleAdapter
import com.itguy.assetmanager.ui.generic.SimpleRow
import kotlinx.coroutines.launch

class NetworkScanFragment : Fragment(), Refreshable {
    private var _b: FragmentNetworkScanBinding? = null
    private val b get() = _b!!

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        _b = FragmentNetworkScanBinding.inflate(inflater, container, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        b.recycler.layoutManager = LinearLayoutManager(requireContext())
        b.deepScanCheck.setOnCheckedChangeListener { _, checked -> b.prefixInput.isEnabled = checked }
        b.prefixInput.isEnabled = false
        b.scanBtn.setOnClickListener { doScan() }
    }

    override fun refresh() { /* re-scanning isn't free (it sweeps the LAN) -- only scan on an explicit tap */ }

    private fun doScan() {
        val deep = b.deepScanCheck.isChecked
        val prefix = b.prefixInput.text?.toString()?.trim().orEmpty()
        if (deep && prefix.isBlank()) { b.scanStatus.text = "Enter a CIDR range for deep scan (e.g. 192.168.1.0/24)"; return }
        b.scanStatus.text = "Scanning…"
        b.scanBtn.isEnabled = false
        b.emptyText.visibility = View.GONE
        lifecycleScope.launch {
            try {
                val resp = ApiClient.api().scan(prefix.ifBlank { null }, if (deep) "1" else "0")
                val list = resp.body().orEmpty()
                if (_b == null) return@launch
                if (!resp.isSuccessful) {
                    b.scanStatus.text = "✕ Scan failed"
                } else {
                    b.scanStatus.text = "${list.size} device(s) found"
                    val adapter = SimpleAdapter(onClick = { row -> onDeviceTapped(row.payload as ScanDevice) })
                    b.recycler.adapter = adapter
                    adapter.submit(list.map { d ->
                        val title = d.host?.takeIf { it.isNotBlank() } ?: d.ip
                        val subtitle = listOfNotNull(d.ip, d.mac?.takeIf { it.isNotBlank() }, d.vendor?.takeIf { it.isNotBlank() }).joinToString(" · ")
                        SimpleRow(title, subtitle, d)
                    })
                    b.emptyText.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
                    b.emptyText.text = "No devices found"
                }
            } catch (e: Exception) {
                if (_b != null) b.scanStatus.text = "✕ Scan failed: ${e.message}"
            } finally {
                _b?.scanBtn?.isEnabled = true
            }
        }
    }

    private fun onDeviceTapped(d: ScanDevice) {
        AlertDialog.Builder(requireContext())
            .setTitle(d.host?.takeIf { it.isNotBlank() } ?: d.ip)
            .setMessage("Add this device as an asset? You'll review and fill in the rest before saving.")
            .setPositiveButton("Add as Asset") { _, _ ->
                val f = AssetEditFragment.newInstanceWithPrefill(
                    name = d.host?.takeIf { it.isNotBlank() } ?: "Device ${d.ip}",
                    mac = d.mac.orEmpty(),
                    type = "Network Device",
                    location = "LAN"
                )
                (activity as? MainActivity)?.showFragment(f, "Add Asset", addToBackStack = true)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
