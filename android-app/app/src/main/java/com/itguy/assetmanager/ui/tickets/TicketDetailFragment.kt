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
import com.itguy.assetmanager.data.OfflineCache
import com.itguy.assetmanager.data.model.TicketDetail
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
                paintStatusPill(STATUSES[position])
                lifecycleScope.launch {
                    try { ApiClient.api().updateTicket(ticketId, mapOf("status" to STATUSES[position])) } catch (e: Exception) {}
                }
            }
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {}
        }
        b.sendReplyBtn.setOnClickListener { sendReply() }
        load()
    }

    /**
     * Show the conversation already on the phone, then refresh it.
     *
     * A ticket is mostly its replies, and those were fetched every single
     * time it was opened -- so a ticket read a minute ago still opened empty
     * and filled in a moment later. The last fetch is kept per ticket now, so
     * it opens with what you last saw and updates underneath.
     */
    private fun load() {
        OfflineCache.loadTicketDetail(ticketId)?.let { render(it, cached = true) }

        lifecycleScope.launch {
            try {
                val resp = ApiClient.api().getTicket(ticketId)
                val d = resp.body() ?: return@launch
                OfflineCache.saveTicketDetail(ticketId, d)
                if (_b == null) return@launch
                render(d, cached = false)
            } catch (e: Exception) {
                if (_b != null && OfflineCache.loadTicketDetail(ticketId) == null) {
                    addLine("Could not load ticket: ${e.message}")
                }
            }
        }
    }

    private fun render(d: TicketDetail, cached: Boolean) {
        // the code identifies the ticket, the subject says what it is about:
        // the subject leads and the code joins the line below it, so a long
        // subject is not pushed off the screen by a reference number
        b.tSubject.text = d.ticket.subject.ifBlank { "(no subject)" }
        b.tMeta.text = listOfNotNull(
            d.ticket.code?.takeIf { it.isNotBlank() },
            d.ticket.priority.takeIf { it.isNotBlank() }?.let { "$it priority" },
            d.ticket.category.takeIf { it.isNotBlank() },
            d.ticket.requester.takeIf { it.isNotBlank() },
        ).joinToString(" · ")
        b.tDescription.text = d.ticket.description.ifBlank { "Nothing else was written." }
        paintStatusPill(d.ticket.status)
        suppressStatusCallback = true
        b.tStatus.setSelection(STATUSES.indexOf(d.ticket.status).coerceAtLeast(0))
        suppressStatusCallback = false

        b.repliesList.removeAllViews()
        if (d.replies.isEmpty()) {
            addLine("No replies yet.")
        } else {
            d.replies.forEachIndexed { i, r ->
                addReply(i > 0, "${r.author} · ${r.author_role} · ${r.created_at}", r.body)
            }
        }
    }

    /** The same pill the ticket wears in the list, so the two agree. */
    private fun paintStatusPill(status: String) {
        if (_b == null) return
        val tint = com.itguy.assetmanager.ui.StatusTint.of(status)
        b.tStatusPill.text = status
        b.tStatusPill.setTextColor(tint)
        b.tStatusPill.background = android.graphics.drawable.GradientDrawable().apply {
            cornerRadius = 100f
            setColor((tint and 0x00FFFFFF) or 0x1A000000)
        }
    }

    private fun px(v: Float) = (v * resources.displayMetrics.density).toInt()

    /** One reply: who and when in soft grey, what they said underneath. */
    private fun addReply(divider: Boolean, who: String, body: String) {
        val ctx = requireContext()
        if (divider) {
            b.repliesList.addView(View(ctx).apply {
                layoutParams = android.widget.LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, px(1f))
                setBackgroundColor(
                    resources.getColor(com.itguy.assetmanager.R.color.divider, null))
            })
        }
        val block = android.widget.LinearLayout(ctx).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(0, px(14f), 0, px(14f))
        }
        block.addView(TextView(ctx).apply {
            text = who
            setTextColor(resources.getColor(com.itguy.assetmanager.R.color.text_soft, null))
            textSize = 11.5f
        })
        block.addView(TextView(ctx).apply {
            text = body
            setTextColor(resources.getColor(com.itguy.assetmanager.R.color.text_strong, null))
            textSize = 14f
            setLineSpacing(0f, 1.2f)
            setPadding(0, px(5f), 0, 0)
        })
        b.repliesList.addView(block)
    }

    private fun addLine(text: String) {
        val tv = TextView(requireContext())
        tv.text = text
        tv.setTextColor(resources.getColor(com.itguy.assetmanager.R.color.text_faint, null))
        tv.textSize = 13f
        tv.setPadding(0, px(14f), 0, px(14f))
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
