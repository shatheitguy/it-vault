package com.itguy.assetmanager.ui.tickets

import android.app.AlertDialog
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.LinearLayout
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.Prefs
import com.itguy.assetmanager.data.model.Ticket
import com.itguy.assetmanager.databinding.FragmentTicketsListBinding
import com.itguy.assetmanager.ui.MainActivity
import com.itguy.assetmanager.ui.Refreshable
import com.itguy.assetmanager.ui.generic.SimpleAdapter
import com.itguy.assetmanager.ui.generic.SimpleRow
import kotlinx.coroutines.launch

class TicketsListFragment : Fragment(), Refreshable {
    private var _b: FragmentTicketsListBinding? = null
    private val b get() = _b!!
    private var showClosed = false

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        _b = FragmentTicketsListBinding.inflate(inflater, container, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        b.recycler.layoutManager = LinearLayoutManager(requireContext())
        b.tabs.addOnTabSelectedListener(object : com.google.android.material.tabs.TabLayout.OnTabSelectedListener {
            override fun onTabSelected(t: com.google.android.material.tabs.TabLayout.Tab) { showClosed = t.position == 1; load() }
            override fun onTabUnselected(t: com.google.android.material.tabs.TabLayout.Tab) {}
            override fun onTabReselected(t: com.google.android.material.tabs.TabLayout.Tab) {}
        })
        b.addFab.setOnClickListener { openCreateDialog() }
        load()
    }

    override fun refresh() = load()

    private fun load() {
        lifecycleScope.launch {
            try {
                val all = ApiClient.api().listTickets().body().orEmpty()
                val filtered = all.filter { (it.status in listOf("Resolved", "Closed")) == showClosed }
                if (_b == null) return@launch
                val adapter = SimpleAdapter(onClick = { row ->
                    val t = row.payload as Ticket
                    (activity as? MainActivity)?.showFragment(TicketDetailFragment.newInstance(t.id), "Ticket ${t.code ?: ""}", addToBackStack = true)
                })
                b.recycler.adapter = adapter
                adapter.submit(filtered.map { t ->
                    SimpleRow("${t.code ?: ""} · ${t.subject}", "${t.status} · ${t.priority} · ${t.requester}", t)
                })
                b.emptyText.visibility = if (filtered.isEmpty()) View.VISIBLE else View.GONE
                b.emptyText.text = "No tickets"
            } catch (e: Exception) {
                if (_b != null) { b.emptyText.text = "Could not load tickets: ${e.message}"; b.emptyText.visibility = View.VISIBLE }
            }
        }
    }

    private fun openCreateDialog() {
        val ctx = requireContext()
        val pad = (16 * resources.displayMetrics.density).toInt()
        val layout = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL; setPadding(pad, pad, pad, pad) }
        val subject = EditText(ctx).apply { hint = "Subject" }
        val desc = EditText(ctx).apply { hint = "Description"; minLines = 3 }
        layout.addView(subject); layout.addView(desc)

        AlertDialog.Builder(ctx).setTitle("New ticket").setView(layout)
            .setPositiveButton("Create") { _, _ ->
                val subj = subject.text.toString().trim()
                if (subj.isBlank()) return@setPositiveButton
                val ticket = Ticket(subject = subj, description = desc.text.toString().trim(), requester = Prefs.displayName.ifBlank { Prefs.username })
                lifecycleScope.launch {
                    try { ApiClient.api().createTicket(ticket); load() } catch (e: Exception) { }
                }
            }
            .setNegativeButton("Cancel", null).show()
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
