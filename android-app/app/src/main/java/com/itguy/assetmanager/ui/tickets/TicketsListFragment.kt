package com.itguy.assetmanager.ui.tickets

import androidx.appcompat.app.AlertDialog
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
import com.itguy.assetmanager.data.Prefs
import com.itguy.assetmanager.data.model.Ticket
import com.itguy.assetmanager.databinding.DialogTicketNewBinding
import com.itguy.assetmanager.databinding.FragmentTicketsListBinding
import com.itguy.assetmanager.ui.MainActivity
import com.itguy.assetmanager.ui.Pills
import com.itguy.assetmanager.ui.Refreshable
import com.itguy.assetmanager.ui.StatusTint
import com.itguy.assetmanager.ui.generic.SimpleAdapter
import com.itguy.assetmanager.ui.generic.SimpleRow
import kotlinx.coroutines.launch

class TicketsListFragment : Fragment(), Refreshable {
    companion object {
        /** [openNew]: straight into "New ticket", as the dashboard's button does. */
        fun newInstance(openNew: Boolean = false) = TicketsListFragment().apply {
            arguments = Bundle().apply { putBoolean("openNew", openNew) }
        }
    }

    private var _b: FragmentTicketsListBinding? = null
    private val b get() = _b!!
    private var showClosed = false
    private var all: List<Ticket> = emptyList()

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        _b = FragmentTicketsListBinding.inflate(inflater, container, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        b.recycler.layoutManager = LinearLayoutManager(requireContext())

        // Active / Closed. Two pills rather than a tab bar: it is a filter,
        // and it now looks like the other filters in the app.
        paintPills()
        b.pillActive.setOnClickListener { choose(false) }
        b.pillClosed.setOnClickListener { choose(true) }

        b.searchInput.addTextChangedListener { render() }
        b.addFab.setOnClickListener { openCreateDialog() }
        load()
        if (arguments?.getBoolean("openNew") == true) {
            arguments?.putBoolean("openNew", false)       // once, not again on the way back
            view.post { if (_b != null) openCreateDialog() }
        }
    }

    private fun choose(closed: Boolean) {
        if (showClosed == closed) return
        showClosed = closed
        paintPills()
        render()
    }

    private fun paintPills() =
        Pills.paintRow(listOf(b.pillActive, b.pillClosed), if (showClosed) 1 else 0)

    override fun refresh() = load()

    private fun load() {
        // what the phone already has, before the server is asked
        OfflineCache.loadTickets()?.let { all = it; render() }
        lifecycleScope.launch {
            try {
                val resp = ApiClient.api().listTickets()
                // body() is null on any non-2xx, and .orEmpty() turned that into
                // an empty list -- so a 401 or a 500 rendered as "No tickets",
                // which reads as "you have none" rather than "this failed".
                if (!resp.isSuccessful || resp.body() == null) {
                    showFromCache(Exception("server returned HTTP ${resp.code()}"))
                    return@launch
                }
                val list = resp.body()!!
                if (_b == null) return@launch
                all = list
                render()
                b.offlineBanner.visibility = View.GONE
                OfflineCache.saveTickets(list)
            } catch (e: Exception) {
                if (_b != null) showFromCache(e)
            }
        }
    }

    /** Last known tickets, clearly labelled as such, beats a blank screen. */
    private fun showFromCache(error: Exception?) {
        if (_b == null) return
        val cached = OfflineCache.loadTickets()
        if (cached != null) {
            all = cached
            render()
            val age = NetworkUtils.timeAgo(OfflineCache.lastUpdated("tickets"))
            b.offlineBanner.text = "📡 Offline — showing cached tickets from $age"
            b.offlineBanner.visibility = View.VISIBLE
        } else {
            b.recycler.adapter = null
            b.offlineBanner.visibility = View.GONE
            b.emptyText.text = error?.message?.let { "Could not load tickets: $it" }
                ?: "No connection and nothing cached yet"
            b.emptyText.visibility = View.VISIBLE
        }
    }

    private fun render() {
        if (_b == null) return
        val query = b.searchInput.text?.toString().orEmpty().trim()
        var filtered = all.filter { (it.status in listOf("Resolved", "Closed")) == showClosed }
        if (query.isNotBlank()) {
            filtered = filtered.filter {
                it.subject.contains(query, true) ||
                    (it.code ?: "").contains(query, true) ||
                    it.requester.contains(query, true) ||
                    it.status.contains(query, true)
            }
        }
        val adapter = SimpleAdapter(onClick = { row ->
            val t = row.payload as Ticket
            (activity as? MainActivity)?.showFragment(TicketDetailFragment.newInstance(t.id), "Ticket ${t.code ?: ""}", addToBackStack = true)
        })
        b.recycler.adapter = adapter
        adapter.submit(filtered.map { t ->
            // the subject leads, because that is what anyone is looking for;
            // the code and who raised it identify which one; the pill is the
            // state, exactly as on an asset row
            SimpleRow(
                title = t.subject.ifBlank { "(no subject)" },
                subtitle = listOfNotNull(
                    t.code?.takeIf { it.isNotBlank() },
                    t.priority.takeIf { it.isNotBlank() },
                    t.requester.takeIf { it.isNotBlank() },
                ).joinToString(" · "),
                payload = t,
                trailing = t.status,
                tint = StatusTint.of(t.status),
            )
        })
        b.emptyText.text = when {
            query.isNotBlank() -> "Nothing matches “$query”"
            showClosed -> "No closed tickets"
            else -> "No open tickets"
        }
        b.emptyText.visibility = if (filtered.isEmpty()) View.VISIBLE else View.GONE
    }

    private fun openCreateDialog() {
        lifecycleScope.launch {
            val spaces = try { ApiClient.api().spaces().body().orEmpty().filter { it.can_edit } } catch (e: Exception) { emptyList() }
            if (_b == null) return@launch
            if (spaces.size > 1) {
                // more than one department: ask which team this is for
                com.itguy.assetmanager.ui.BrandDialog(requireContext()).setTitle("Which department?")
                    .setItems(spaces.map { it.name }.toTypedArray()) { _, i -> openCreateDialog(spaces[i]) }
                    .setNegativeButton("Cancel", null).show()
            } else openCreateDialog(spaces.firstOrNull())
        }
    }

    private fun openCreateDialog(space: com.itguy.assetmanager.data.model.SpaceItem?) {
        val d = DialogTicketNewBinding.inflate(layoutInflater)
        com.itguy.assetmanager.ui.FormLabels.apply(d.root)
        com.itguy.assetmanager.ui.BrandDialog(requireContext()).setTitle(if (space != null) "New ${space.name} ticket" else "New ticket").setView(d.root)
            .setPositiveButton("Create") { _, _ ->
                val subj = d.newSubject.text?.toString()?.trim().orEmpty()
                if (subj.isBlank()) return@setPositiveButton
                val ticket = Ticket(
                    subject = subj,
                    description = d.newDescription.text?.toString()?.trim().orEmpty(),
                    requester = Prefs.displayName.ifBlank { Prefs.username },
                    SpaceID = space?.id,
                )
                lifecycleScope.launch {
                    try { ApiClient.api().createTicket(ticket); load() } catch (e: Exception) { }
                }
            }
            .setNegativeButton("Cancel", null).show()
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
