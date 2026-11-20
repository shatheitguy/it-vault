package com.itguy.assetmanager.ui.settings

import android.content.Context
import android.net.Uri
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.itguy.assetmanager.R
import com.itguy.assetmanager.data.ApiError
import com.itguy.assetmanager.databinding.FragmentSectionBinding
import com.itguy.assetmanager.ui.Refreshable
import kotlinx.coroutines.launch

/** One settings section, drawn from its description in [SettingsSections]. */
class SectionFragment : Fragment(), Refreshable {
    companion object {
        fun newInstance(id: String) = SectionFragment().apply { arguments = Bundle().apply { putString("id", id) } }
    }

    private var _b: FragmentSectionBinding? = null
    private val b get() = _b!!
    private var onPicked: ((Uri) -> Unit)? = null
    private val picker = registerForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri != null) onPicked?.invoke(uri)
        onPicked = null
    }
    private val loaders = mutableListOf<() -> Unit>()

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, s: Bundle?): View {
        _b = FragmentSectionBinding.inflate(inflater, container, false); return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        val id = arguments?.getString("id").orEmpty()
        val section = SettingsSections.byId(requireContext(), id) ?: MoreSections.byId(id) ?: return
        b.sectionRefresh.setOnRefreshListener { refresh(); b.sectionRefresh.isRefreshing = false }
        section.groups.forEach { addGroup(it) }
        refresh()
    }

    override fun refresh() { loaders.forEach { it() } }

    private fun addGroup(g: Group) {
        val ctx = requireContext()
        b.sectionBody.addView(sectionTitle(ctx, g.title, g.subtitle))
        val (card, inner) = sectionCard(ctx)
        b.sectionBody.addView(card)
        val msg = message(ctx)
        val form = Form(ctx)
        val fieldsBox = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL }
        inner.addView(fieldsBox)
        form.build(fieldsBox, g.fields)

        fun say(text: String?, ok: Boolean) {
            if (_b == null) return
            if (text.isNullOrBlank()) { msg.visibility = View.GONE; return }
            msg.text = (if (ok) "✓ " else "✕ ") + text
            msg.setTextColor(ctx.getColor(if (ok) R.color.stat_green else R.color.stat_red))
            msg.visibility = View.VISIBLE
        }
        fun run(block: suspend () -> Unit) = viewLifecycleOwner.lifecycleScope.launch {
            try { block() }
            catch (e: ApiError) { say(e.message, false) }
            catch (e: Exception) { say("Could not reach the server: ${e.message ?: e.javaClass.simpleName}", false) }
        }

        val host = object : GroupHost {
            override val context: Context get() = ctx
            override val body: LinearLayout = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL }
            override fun say(msg: String?, ok: Boolean) = say(msg, ok)
            override fun launch(block: suspend () -> Unit) { run(block) }
            override fun pickFile(mime: String, onPicked: (Uri) -> Unit) { this@SectionFragment.onPicked = onPicked; picker.launch(mime) }
            override fun reload() { loaders.forEach { it() } }
            override fun onRefresh(block: () -> Unit) { loaders += block }
        }
        if (g.custom != null) { inner.addView(host.body); g.custom.invoke(host) }

        val buttons = mutableListOf<View>()
        g.save?.let { save ->
            buttons += pillButton(ctx, g.saveLabel, true).apply {
                setOnClickListener { isEnabled = false; run { try { say(save(form) ?: "Saved", true) } finally { isEnabled = true } } }
            }
        }
        g.actions.forEach { a ->
            buttons += pillButton(ctx, a.label, a.primary && g.save == null).apply {
                setOnClickListener {
                    val go = { isEnabled = false; run { try { a.run(form)?.let { say(it, true) } } finally { isEnabled = true } } }
                    if (a.confirm == null) go()
                    else com.itguy.assetmanager.ui.BrandDialog(ctx).setTitle(a.label).setMessage(a.confirm)
                        .setPositiveButton(a.label) { _, _ -> go() }.setNegativeButton("Cancel", null).show()
                }
            }
        }
        if (buttons.isNotEmpty()) inner.addView(buttonRow(ctx, buttons))
        inner.addView(msg)

        g.load?.let { load ->
            loaders += { run { val o = load(); if (_b != null) form.fill(o) } }
        }
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null; loaders.clear() }
}
