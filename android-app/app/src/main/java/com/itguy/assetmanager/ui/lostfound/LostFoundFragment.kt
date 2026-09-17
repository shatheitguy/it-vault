package com.itguy.assetmanager.ui.lostfound

import android.app.AlertDialog
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.model.LostFoundReport
import com.itguy.assetmanager.data.model.LostFoundStatus
import com.itguy.assetmanager.databinding.FragmentDirectoryBinding
import com.itguy.assetmanager.ui.Refreshable
import com.itguy.assetmanager.ui.generic.SimpleAdapter
import com.itguy.assetmanager.ui.generic.SimpleRow
import kotlinx.coroutines.launch

/**
 * Lost & Found, on the phone.
 *
 * A report arrives when a stranger scans an asset tag and says they have the
 * thing. What they leave is a name and a number, and the only useful next
 * step is to ring them -- which is the step a phone is good at and a desk
 * browser is not. So the number is one tap, the status is one tap, and there
 * is nothing else on the row.
 */
class LostFoundFragment : Fragment(), Refreshable {

    private var _b: FragmentDirectoryBinding? = null
    private val b get() = _b!!
    private var rows: List<LostFoundReport> = emptyList()
    private val adapter = SimpleAdapter(onClick = { row ->
        (row.payload as? LostFoundReport)?.let { openActions(it) }
    })

    override fun onCreateView(i: LayoutInflater, c: ViewGroup?, s: Bundle?): View {
        _b = FragmentDirectoryBinding.inflate(i, c, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        b.recycler.layoutManager = LinearLayoutManager(requireContext())
        b.recycler.adapter = adapter
        b.searchWrap.visibility = View.GONE
        b.addFab.visibility = View.GONE
        load()
    }

    override fun refresh() = load()

    private fun load() {
        lifecycleScope.launch {
            try {
                rows = ApiClient.api().lostFound()
                render()
            } catch (e: Exception) {
                toast("Could not load Lost & Found: ${e.message}")
            }
        }
    }

    private fun render() {
        adapter.submit(rows.map { r ->
            val who = listOfNotNull(
                r.finder_name?.takeIf { it.isNotBlank() },
                r.finder_mobile?.takeIf { it.isNotBlank() },
            ).joinToString(" · ").ifBlank { "reported by staff" }
            SimpleRow(
                title = "${r.ref ?: "LF-${r.id}"}   ${r.asset_name ?: r.asset_tag ?: ""}",
                subtitle = "${(r.status ?: "found").uppercase()} · $who",
                payload = r,
            )
        })
        b.emptyText.visibility = if (rows.isEmpty()) View.VISIBLE else View.GONE
        b.emptyText.text = "NOTHING REPORTED LOST OR FOUND"
    }

    private fun openActions(r: LostFoundReport) {
        val number = r.finder_mobile?.filter { it.isDigit() || it == '+' }.orEmpty()
        val actions = mutableListOf<Pair<String, () -> Unit>>()
        if (number.isNotBlank()) {
            actions += "Call ${r.finder_mobile}" to {
                // DIAL, not CALL: it opens the dialer with the number in it,
                // which needs no permission and lets them see who they are
                // about to ring before it rings.
                startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:$number")))
            }
        }
        actions += "Change status" to { askStatus(r) }
        if (!r.finder_note.isNullOrBlank()) {
            actions += "Where it was found" to {
                AlertDialog.Builder(requireContext())
                    .setTitle("Where it was found")
                    .setMessage(r.finder_note)
                    .setPositiveButton("Close", null)
                    .show()
            }
        }
        AlertDialog.Builder(requireContext())
            .setTitle("${r.ref ?: "LF-${r.id}"} · ${r.asset_name ?: ""}")
            .setItems(actions.map { it.first }.toTypedArray()) { _, which -> actions[which].second() }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun askStatus(r: LostFoundReport) {
        val labels = LostFoundStatus.ALL.map { it.uppercase() }.toTypedArray()
        AlertDialog.Builder(requireContext())
            .setTitle("Status")
            .setItems(labels) { _, which ->
                val next = LostFoundStatus.ALL[which]
                lifecycleScope.launch {
                    try {
                        ApiClient.api().lostFoundStatus(r.id, mapOf("status" to next))
                        toast("Marked ${next.uppercase()}")
                        load()
                    } catch (e: Exception) {
                        toast("Could not update that: ${e.message}")
                    }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun toast(msg: String) {
        if (isAdded) Toast.makeText(requireContext(), msg, Toast.LENGTH_SHORT).show()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _b = null
    }
}
