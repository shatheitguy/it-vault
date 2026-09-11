package com.itguy.assetmanager.ui.heartbeat

import android.app.AlertDialog
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.NetworkUtils
import com.itguy.assetmanager.data.OfflineCache
import com.itguy.assetmanager.data.model.HbMonitor
import com.itguy.assetmanager.data.model.HbMonitorRequest
import com.itguy.assetmanager.databinding.DialogHeartbeatEditBinding
import com.itguy.assetmanager.databinding.FragmentHeartbeatBinding
import com.itguy.assetmanager.ui.Refreshable
import kotlinx.coroutines.launch

/**
 * Heartbeat on the phone: what is down right now, and enough control to act on
 * it without finding a desk -- add a monitor, force a check, pause the one
 * that is crying wolf while you work on it.
 *
 * The checking itself is the server's job and runs around the clock whether
 * this screen is open or not, so there is no polling loop here beyond a
 * refresh when the screen comes back into view.
 */
class HeartbeatFragment : Fragment(), Refreshable {

    private var _b: FragmentHeartbeatBinding? = null
    private val b get() = _b!!
    private lateinit var adapter: HeartbeatAdapter
    private var monitors: List<HbMonitor> = emptyList()

    private val kinds = listOf("ping", "http", "keyword", "port", "dns")
    private val kindLabels = listOf(
        "Ping (ICMP) — is the device alive",
        "HTTP(S) — is the service answering",
        "HTTP keyword — does the page say the right thing",
        "TCP port — is the service listening",
        "DNS — does the name still resolve"
    )
    private val kindHints = mapOf(
        "ping" to "Right for switches, access points, printers and cameras — anything that should simply be reachable.",
        "http" to "Asks for the page and treats anything outside 200-299 as down.",
        "keyword" to "Catches the case a plain HTTP check misses: the server answers 200 while the app behind it is broken.",
        "port" to "Opens a TCP connection and closes it again — SQL on 3306, RDP on 3389, SMTP on 25.",
        "dns" to "Fails if the name stops resolving. Worth having on DNS you depend on but do not control."
    )

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        _b = FragmentHeartbeatBinding.inflate(inflater, container, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        adapter = HeartbeatAdapter { m -> onMonitorTapped(m) }
        b.recycler.layoutManager = LinearLayoutManager(requireContext())
        b.recycler.adapter = adapter
        b.addBtn.setOnClickListener { showEditDialog(null) }
        b.checkNowBtn.setOnClickListener { checkAll() }
        load()
    }

    override fun onResume() {
        super.onResume()
        if (monitors.isNotEmpty()) load()
    }

    override fun refresh() = load()

    private fun load() {
        val binding = _b ?: return
        binding.statusLine.text = "Loading…"
        lifecycleScope.launch {
            try {
                val resp = ApiClient.api().heartbeatState(24)
                if (_b == null) return@launch
                if (resp.code() == 403) {
                    b.statusLine.text = "No access to Heartbeat."
                    b.emptyText.visibility = View.GONE
                    adapter.submit(emptyList())
                    return@launch
                }
                if (!resp.isSuccessful || resp.body() == null) {
                    showFromCache("server returned HTTP ${resp.code()}")
                    return@launch
                }
                b.offlineBanner.visibility = View.GONE
                val state = resp.body()
                OfflineCache.saveHeartbeat(state!!)
                val list = state.monitors.orEmpty()
                // down first, then still-being-retried, then healthy, then paused
                monitors = list.sortedWith(
                    compareBy({ rank(it.uiStatus) }, { it.label.lowercase() })
                )
                adapter.submit(monitors)
                val c = state?.counts
                b.nDown.text = (c?.down ?: 0).toString()
                b.nPending.text = (c?.pending ?: 0).toString()
                b.nUp.text = (c?.up ?: 0).toString()
                b.nPaused.text = (c?.disabled ?: 0).toString()
                b.statusLine.text = if (list.isEmpty()) ""
                    else "${list.size} monitor${if (list.size == 1) "" else "s"} · checked around the clock"
                b.emptyText.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
            } catch (e: Exception) {
                if (_b != null) showFromCache(e.message ?: "connection failed")
            }
        }
    }

    /**
     * Monitor status from the last successful read, labelled with its age.
     *
     * Stale up/down is worth showing as long as it is obviously stale -- what
     * is not worth showing is an empty list, which reads as "no monitors
     * configured" when the truth is "could not ask".
     */
    private fun showFromCache(why: String) {
        if (_b == null) return
        val cached = OfflineCache.loadHeartbeat()
        if (cached == null) {
            b.offlineBanner.visibility = View.GONE
            b.statusLine.text = "✕ $why"
            return
        }
        val list = cached.monitors.orEmpty()
        monitors = list.sortedWith(compareBy({ rank(it.uiStatus) }, { it.label.lowercase() }))
        adapter.submit(monitors)
        val c = cached.counts
        b.nDown.text = (c?.down ?: 0).toString()
        b.nPending.text = (c?.pending ?: 0).toString()
        b.nUp.text = (c?.up ?: 0).toString()
        b.nPaused.text = (c?.disabled ?: 0).toString()
        val age = NetworkUtils.timeAgo(OfflineCache.lastUpdated("heartbeat"))
        b.offlineBanner.text = "📡 Offline — last known status from $age"
        b.offlineBanner.visibility = View.VISIBLE
        b.statusLine.text = "✕ $why"
        b.emptyText.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
    }

    private fun rank(status: String) = when (status) {
        "down" -> 0
        "pending" -> 1
        "up" -> 2
        else -> 3
    }

    private fun checkAll() {
        val binding = _b ?: return
        binding.checkNowBtn.isEnabled = false
        binding.statusLine.text = "Checking…"
        lifecycleScope.launch {
            try {
                val r = ApiClient.api().heartbeatCheckAll()
                if (_b == null) return@launch
                if (r.code() == 403) {
                    b.statusLine.text = "No access to Heartbeat."
                } else {
                    toast("Checked ${r.body()?.checked ?: 0} monitor(s)")
                    load()
                }
            } catch (e: Exception) {
                if (_b != null) b.statusLine.text = "✕ ${e.message ?: "check failed"}"
            } finally {
                _b?.checkNowBtn?.isEnabled = true
            }
        }
    }

    private fun onMonitorTapped(m: HbMonitor) {
        val st = m.uiStatus
        val paused = st == "paused"
        val lines = mutableListOf<String>()
        lines += "Status: ${if (st == "pending") "checking" else st}"
        lines += "Check: ${(m.kind ?: "ping").uppercase()} on ${m.where}"
        lines += "Every ${m.interval_s ?: 60}s, ${m.fail_threshold ?: 2} retr${if ((m.fail_threshold ?: 2) == 1) "y" else "ies"} before it counts as down"
        m.last_ms?.let { lines += "Last response: $it ms" }
        m.uptime?.let { lines += "Uptime (24h): $it% of ${m.samples ?: 0} checks" }
        m.cert_days?.let { lines += "Certificate expires in $it days" }
        m.last_change?.let { lines += "Changed state: $it" }
        m.last_error?.takeIf { it.isNotBlank() && st != "up" }?.let { lines += "\nReason: $it" }
        if ((m.notify ?: 1) == 0) lines += "\nAlerts are switched off for this monitor."

        AlertDialog.Builder(requireContext())
            .setTitle(m.label)
            .setMessage(lines.joinToString("\n"))
            .setPositiveButton("Check now") { _, _ -> checkOne(m) }
            .setNeutralButton(if (paused) "Resume" else "Pause") { _, _ -> togglePause(m) }
            .setNegativeButton("More…") { _, _ -> showMoreActions(m) }
            .show()
    }

    private fun showMoreActions(m: HbMonitor) {
        AlertDialog.Builder(requireContext())
            .setTitle(m.label)
            .setItems(arrayOf("Edit monitor", "Delete monitor")) { _, which ->
                when (which) {
                    0 -> showEditDialog(m)
                    1 -> confirmDelete(m)
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun checkOne(m: HbMonitor) {
        lifecycleScope.launch {
            try {
                ApiClient.api().heartbeatCheckOne(m.id)
                load()
            } catch (e: Exception) {
                toast("Check failed: ${e.message}")
            }
        }
    }

    private fun togglePause(m: HbMonitor) {
        lifecycleScope.launch {
            try {
                // the server keeps every other field; only `enabled` moves, and
                // kind/target go along because they are required on a PUT
                val body = HbMonitorRequest(
                    name = null, kind = m.kind, target = m.target, port = m.port,
                    keyword = m.keyword, tag = null, note = null,
                    interval_s = null, fail_threshold = null, timeout_s = null,
                    notify = null, enabled = (m.enabled ?: 1) == 0
                )
                val r = ApiClient.api().heartbeatUpdate(m.id, body)
                if (r.isSuccessful) {
                    toast(if ((m.enabled ?: 1) == 1) "Paused" else "Resumed")
                    load()
                } else toast("✕ ${r.errorBody()?.string()?.take(120) ?: "update failed"}")
            } catch (e: Exception) {
                toast("Update failed: ${e.message}")
            }
        }
    }

    private fun confirmDelete(m: HbMonitor) {
        AlertDialog.Builder(requireContext())
            .setTitle("Delete ${m.label}?")
            .setMessage("The monitor and its history are removed. This cannot be undone.")
            .setPositiveButton("Delete") { _, _ ->
                lifecycleScope.launch {
                    try {
                        val r = ApiClient.api().heartbeatDelete(m.id)
                        if (r.isSuccessful) { toast("Deleted"); load() } else toast("✕ Delete failed")
                    } catch (e: Exception) { toast("Delete failed: ${e.message}") }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showEditDialog(existing: HbMonitor?) {
        val d = DialogHeartbeatEditBinding.inflate(layoutInflater)
        d.edKind.adapter = ArrayAdapter(requireContext(),
            android.R.layout.simple_spinner_dropdown_item, kindLabels)

        fun applyKind() {
            val kind = kinds[d.edKind.selectedItemPosition]
            d.edPortWrap.visibility = if (kind == "port") View.VISIBLE else View.GONE
            d.edKeywordWrap.visibility = if (kind == "keyword") View.VISIBLE else View.GONE
            d.edTarget.hint = when (kind) {
                "http", "keyword" -> "URL or host"
                "dns" -> "Hostname to resolve"
                else -> "IP or hostname"
            }
            val iv = d.edInterval.text?.toString()?.toIntOrNull() ?: 60
            val rt = d.edRetries.text?.toString()?.toIntOrNull() ?: 2
            val secs = iv * rt
            val when0 = if (secs < 60) "$secs seconds" else "${Math.round(secs / 60.0)} minute(s)"
            d.edHint.text = (kindHints[kind] ?: "") +
                "\n\nYou will hear about an outage roughly $when0 after it starts, and once more when it recovers."
        }
        d.edKind.setOnItemSelectedListener(object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onItemSelected(p: android.widget.AdapterView<*>?, v: View?, pos: Int, id: Long) = applyKind()
            override fun onNothingSelected(p: android.widget.AdapterView<*>?) {}
        })

        existing?.let { m ->
            d.edName.setText(m.name.orEmpty())
            d.edKind.setSelection(kinds.indexOf(m.kind ?: "ping").coerceAtLeast(0))
            d.edTarget.setText(m.target.orEmpty())
            d.edPort.setText(m.port?.toString().orEmpty())
            d.edKeyword.setText(m.keyword.orEmpty())
            d.edTag.setText(m.tag.orEmpty())
            d.edInterval.setText((m.interval_s ?: 60).toString())
            d.edRetries.setText((m.fail_threshold ?: 2).toString())
            d.edTimeout.setText((m.timeout_s ?: 8).toString())
            d.edNotify.isChecked = (m.notify ?: 1) == 1
            d.edEnabled.isChecked = (m.enabled ?: 1) == 1
        }
        applyKind()

        AlertDialog.Builder(requireContext())
            .setTitle(if (existing == null) "Add monitor" else "Edit monitor")
            .setView(d.root)
            .setPositiveButton("Save", null)          // wired below so it can validate
            .setNegativeButton("Cancel", null)
            .create()
            .also { dlg ->
                dlg.setOnShowListener {
                    dlg.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                        val kind = kinds[d.edKind.selectedItemPosition]
                        val target = d.edTarget.text?.toString()?.trim().orEmpty()
                        val port = d.edPort.text?.toString()?.trim()?.toIntOrNull()
                        val keyword = d.edKeyword.text?.toString()?.trim().orEmpty()
                        if (target.isBlank()) { toast("Enter an IP, hostname or URL"); return@setOnClickListener }
                        if (kind == "port" && port == null) { toast("A port check needs a port number"); return@setOnClickListener }
                        if (kind == "keyword" && keyword.isBlank()) { toast("Enter the keyword to look for"); return@setOnClickListener }
                        val body = HbMonitorRequest(
                            name = d.edName.text?.toString()?.trim()?.ifBlank { target } ?: target,
                            kind = kind, target = target, port = port,
                            keyword = keyword, tag = d.edTag.text?.toString()?.trim().orEmpty(),
                            note = null,
                            interval_s = d.edInterval.text?.toString()?.trim()?.toIntOrNull() ?: 60,
                            fail_threshold = d.edRetries.text?.toString()?.trim()?.toIntOrNull() ?: 2,
                            timeout_s = d.edTimeout.text?.toString()?.trim()?.toIntOrNull() ?: 8,
                            notify = d.edNotify.isChecked, enabled = d.edEnabled.isChecked
                        )
                        save(existing?.id, body) { dlg.dismiss() }
                    }
                }
                dlg.show()
            }
    }

    private fun save(id: Int?, body: HbMonitorRequest, onDone: () -> Unit) {
        lifecycleScope.launch {
            try {
                val newId: Int?
                if (id == null) {
                    val r = ApiClient.api().heartbeatCreate(body)
                    if (!r.isSuccessful) {
                        toast("✕ ${r.body()?.error ?: r.errorBody()?.string()?.take(140) ?: "save failed"}")
                        return@launch
                    }
                    newId = r.body()?.id
                } else {
                    val r = ApiClient.api().heartbeatUpdate(id, body)
                    if (!r.isSuccessful) {
                        toast("✕ ${r.errorBody()?.string()?.take(140) ?: "save failed"}")
                        return@launch
                    }
                    newId = id
                }
                onDone()
                toast(if (id == null) "Monitor added" else "Monitor updated")
                // probe it now rather than leaving the row blank until the tick
                newId?.let { runCatching { ApiClient.api().heartbeatCheckOne(it) } }
                load()
            } catch (e: Exception) {
                toast("Save failed: ${e.message}")
            }
        }
    }

    private fun toast(msg: String) {
        if (isAdded) Toast.makeText(requireContext(), msg, Toast.LENGTH_SHORT).show()
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
