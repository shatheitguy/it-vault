package com.itguy.assetmanager.ui.generic

import android.app.AlertDialog
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.model.IdRequest
import com.itguy.assetmanager.data.model.NameOnly
import com.itguy.assetmanager.databinding.FragmentDirectoryBinding
import com.itguy.assetmanager.ui.Refreshable
import kotlinx.coroutines.launch

enum class ListKind { CATALOG, TRASH, AUDIT }

/** One reusable read/add/delete list screen for every simple reference-style
 * section (Product Catalog, Trash, Audit Log) -- all driven straight from
 * the server's REST API, no WebView involved. Contracts has its own
 * dedicated list+edit screens (see ui.contracts) since it needs a real form. */
class GenericListFragment : Fragment(), Refreshable {
    private var _b: FragmentDirectoryBinding? = null
    private val b get() = _b!!
    private lateinit var kind: ListKind
    private var catalogTab = 0 // 0=categories 1=manufacturers 2=models 3=contract types

    companion object {
        fun newInstance(kind: ListKind) = GenericListFragment().apply {
            arguments = Bundle().apply { putString("kind", kind.name) }
        }
    }

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        _b = FragmentDirectoryBinding.inflate(inflater, container, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        kind = ListKind.valueOf(arguments?.getString("kind") ?: ListKind.CATALOG.name)
        b.recycler.layoutManager = LinearLayoutManager(requireContext())
        b.searchWrap.visibility = View.GONE

        if (kind == ListKind.CATALOG) {
            b.tabs.visibility = View.VISIBLE
            b.tabs.addTab(b.tabs.newTab().setText("Categories"))
            b.tabs.addTab(b.tabs.newTab().setText("Manufacturers"))
            b.tabs.addTab(b.tabs.newTab().setText("Models"))
            b.tabs.addTab(b.tabs.newTab().setText("Contract Types"))
            b.tabs.addOnTabSelectedListener(object : com.google.android.material.tabs.TabLayout.OnTabSelectedListener {
                override fun onTabSelected(t: com.google.android.material.tabs.TabLayout.Tab) { catalogTab = t.position; load() }
                override fun onTabUnselected(t: com.google.android.material.tabs.TabLayout.Tab) {}
                override fun onTabReselected(t: com.google.android.material.tabs.TabLayout.Tab) {}
            })
        } else {
            b.tabs.visibility = View.GONE
        }

        b.addFab.visibility = if (kind == ListKind.TRASH || kind == ListKind.AUDIT) View.GONE else View.VISIBLE
        b.addFab.setOnClickListener { onAdd() }

        load()
    }

    override fun refresh() = load()

    private fun onAdd() {
        when (kind) {
            ListKind.CATALOG -> when (catalogTab) {
                0 -> promptName("New category") { name -> lifecycleScope.launch { ApiClient.api().addCategory(NameOnly(name)); load() } }
                1 -> promptName("New manufacturer") { name -> lifecycleScope.launch { ApiClient.api().addManufacturer(NameOnly(name)); load() } }
                2 -> promptName("New model") { name -> lifecycleScope.launch { ApiClient.api().addModel(mapOf("name" to name)); load() } }
                3 -> promptName("New contract type") { name -> lifecycleScope.launch { ApiClient.api().addContractType(NameOnly(name)); load() } }
            }
            else -> {}
        }
    }

    private fun promptName(title: String, onValue: (String) -> Unit) {
        val edit = EditText(requireContext())
        AlertDialog.Builder(requireContext()).setTitle(title).setView(edit)
            .setPositiveButton("Add") { _, _ -> edit.text?.toString()?.trim()?.takeIf { it.isNotBlank() }?.let(onValue) }
            .setNegativeButton("Cancel", null).show()
    }

    private fun load() {
        lifecycleScope.launch {
            try {
                when (kind) {
                    ListKind.CATALOG -> when (catalogTab) {
                        0 -> {
                            val list = ApiClient.api().categories().body().orEmpty()
                            render(list.map { SimpleRow(it.name, payload = it) }) { row ->
                                val i = row.payload as com.itguy.assetmanager.data.model.NamedItem
                                ApiClient.api().deleteCategory(IdRequest(i.id)); load()
                            }
                        }
                        1 -> {
                            val list = ApiClient.api().manufacturers().body().orEmpty()
                            render(list.map { SimpleRow(it.name, payload = it) }) { row ->
                                val i = row.payload as com.itguy.assetmanager.data.model.NamedItem
                                ApiClient.api().deleteManufacturer(IdRequest(i.id)); load()
                            }
                        }
                        2 -> {
                            val list = ApiClient.api().models().body().orEmpty()
                            render(list.map { SimpleRow(it.name, it.manufacturer ?: "", it) }) { row ->
                                val i = row.payload as com.itguy.assetmanager.data.model.ModelItem
                                ApiClient.api().deleteModel(IdRequest(i.id)); load()
                            }
                        }
                        else -> {
                            val list = ApiClient.api().contractTypes().body().orEmpty()
                            render(list.map { SimpleRow(it.name, payload = it) }) { row ->
                                val i = row.payload as com.itguy.assetmanager.data.model.NamedItem
                                ApiClient.api().deleteContractType(IdRequest(i.id)); load()
                            }
                        }
                    }
                    ListKind.TRASH -> {
                        val list = ApiClient.api().trash().body().orEmpty()
                        val adapter = SimpleAdapter(onClick = { row ->
                            val a = row.payload as com.itguy.assetmanager.data.model.Asset
                            AlertDialog.Builder(requireContext()).setTitle("Restore \"${a.Name}\"?")
                                .setPositiveButton("Restore") { _, _ -> lifecycleScope.launch { ApiClient.api().restoreAsset(a.id ?: return@launch); load() } }
                                .setNegativeButton("Cancel", null).show()
                        })
                        b.recycler.adapter = adapter
                        adapter.submit(list.map { SimpleRow(it.Name, "${it.Type} · ${it.Serial} — tap to restore", it) })
                        b.emptyText.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
                        b.emptyText.text = "Trash is empty"
                    }
                    ListKind.AUDIT -> {
                        val list = ApiClient.api().audit().body().orEmpty()
                        val adapter = SimpleAdapter()
                        b.recycler.adapter = adapter
                        adapter.submit(list.map { SimpleRow("${it.actor ?: "system"} · ${it.action ?: ""}", "${it.detail ?: ""} — ${it.ts}") })
                        b.emptyText.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
                        b.emptyText.text = "No audit entries"
                    }
                }
            } catch (e: Exception) {
                if (_b != null) { b.emptyText.text = "Could not load: ${e.message}"; b.emptyText.visibility = View.VISIBLE }
            }
        }
    }

    private fun render(rows: List<SimpleRow>, onDelete: suspend (SimpleRow) -> Unit) {
        if (_b == null) return
        val adapter = SimpleAdapter(onDelete = { row -> lifecycleScope.launch { onDelete(row) } })
        b.recycler.adapter = adapter
        adapter.submit(rows)
        b.emptyText.visibility = if (rows.isEmpty()) View.VISIBLE else View.GONE
        b.emptyText.text = "None yet"
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
