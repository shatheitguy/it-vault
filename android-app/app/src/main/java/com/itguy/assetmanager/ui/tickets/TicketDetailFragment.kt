package com.itguy.assetmanager.ui.tickets

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.model.ReplyRequest
import com.itguy.assetmanager.databinding.FragmentTicketDetailBinding
import kotlinx.coroutines.launch

class TicketDetailFragment : Fragment() {
    private var _b: FragmentTicketDetailBinding? = null
    private val b get() = _b!!
    private var ticketId = 0
    private val STATUSES = listOf("Open", "In Progress", "Pending", "Resolved", "Closed")
    private var suppressStatusCallback = false

    companion object {
        fun newInstance(id: Int) = TicketDetailFragment().apply { arguments = Bundle().apply { putInt("id", id) } }
    }

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        _b = FragmentTicketDetailBinding.inflate(inflater, container, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        ticketId = arguments?.getInt("id") ?: 0
        b.tStatus.adapter = ArrayAdapter(requireContext(), android.R.layout.simple_spinner_dropdown_item, STATUSES)
        b.tStatus.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) {
                if (suppressStatusCallback) return
                lifecycleScope.launch {
                    try { ApiClient.api().updateTicket(ticketId, mapOf("status" to STATUSES[position])) } catch (e: Exception) {}
                }
            }
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {}
        }
        b.sendReplyBtn.setOnClickListener { sendReply() }
        load()
    }

    private fun load() {
        lifecycleScope.launch {
            try {
                val resp = ApiClient.api().getTicket(ticketId)
                val d = resp.body() ?: return@launch
                if (_b == null) return@launch
                b.tSubject.text = "${d.ticket.code ?: ""} · ${d.ticket.subject}"
                b.tMeta.text = "${d.ticket.priority} priority · ${d.ticket.category} · ${d.ticket.requester}"
                b.tDescription.text = d.ticket.description
                suppressStatusCallback = true
                b.tStatus.setSelection(STATUSES.indexOf(d.ticket.status).coerceAtLeast(0))
                suppressStatusCallback = false

                b.repliesList.removeAllViews()
                if (d.replies.isEmpty()) {
                    addLine("No replies yet.")
                } else {
                    for (r in d.replies) addLine("${r.author} (${r.author_role}) · ${r.created_at}\n${r.body}")
                }
            } catch (e: Exception) {
                if (_b != null) addLine("Could not load ticket: ${e.message}")
            }
        }
    }

    private fun addLine(text: String) {
        val tv = TextView(requireContext())
        tv.text = text
        tv.setTextColor(resources.getColor(com.itguy.assetmanager.R.color.text, null))
        tv.setPadding(0, 0, 0, 16)
        b.repliesList.addView(tv)
    }

    private fun sendReply() {
        val body = b.replyInput.text?.toString()?.trim().orEmpty()
        if (body.isBlank()) return
        lifecycleScope.launch {
            try {
                ApiClient.api().replyTicket(ticketId, ReplyRequest(body))
                b.replyInput.setText("")
                load()
            } catch (e: Exception) {}
        }
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
