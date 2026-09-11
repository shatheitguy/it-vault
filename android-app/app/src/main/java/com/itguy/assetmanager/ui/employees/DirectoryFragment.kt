package com.itguy.assetmanager.ui.employees

import android.app.AlertDialog
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import androidx.core.widget.addTextChangedListener
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.model.Employee
import com.itguy.assetmanager.data.model.NameOnly
import com.itguy.assetmanager.databinding.FragmentDirectoryBinding
import com.itguy.assetmanager.ui.MainActivity
import com.itguy.assetmanager.ui.Refreshable
import com.itguy.assetmanager.ui.generic.SimpleAdapter
import com.itguy.assetmanager.ui.generic.SimpleRow
import kotlinx.coroutines.launch

class DirectoryFragment : Fragment(), Refreshable {
    private var _b: FragmentDirectoryBinding? = null
    private val b get() = _b!!
    private lateinit var adapter: SimpleAdapter
    private var tab = 0 // 0=employees 1=departments 2=designations
    private var employees: List<Employee> = emptyList()

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        _b = FragmentDirectoryBinding.inflate(inflater, container, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        b.recycler.layoutManager = LinearLayoutManager(requireContext())

        b.tabs.visibility = View.VISIBLE
        b.tabs.addTab(b.tabs.newTab().setText("Employees"))
        b.tabs.addTab(b.tabs.newTab().setText("Departments"))
        b.tabs.addTab(b.tabs.newTab().setText("Designations"))
        b.tabs.addOnTabSelectedListener(object : com.google.android.material.tabs.TabLayout.OnTabSelectedListener {
            override fun onTabSelected(tabItem: com.google.android.material.tabs.TabLayout.Tab) { tab = tabItem.position; load() }
            override fun onTabUnselected(tabItem: com.google.android.material.tabs.TabLayout.Tab) {}
            override fun onTabReselected(tabItem: com.google.android.material.tabs.TabLayout.Tab) {}
        })

        b.searchInput.addTextChangedListener { renderEmployees(it?.toString().orEmpty()) }
        b.addFab.setOnClickListener { onAdd() }

        load()
    }

    override fun refresh() = load()

    private fun load() {
        lifecycleScope.launch {
            try {
                when (tab) {
                    0 -> {
                        b.searchWrap.visibility = View.VISIBLE
                        if (com.itguy.assetmanager.data.NetworkUtils.isOnline(requireContext())) {
                            employees = ApiClient.api().listEmployees().body().orEmpty()
                            com.itguy.assetmanager.data.OfflineCache.saveEmployees(employees)
                        } else {
                            employees = com.itguy.assetmanager.data.OfflineCache.loadEmployees().orEmpty()
                            b.emptyText.text = "📡 Offline — showing cached directory"
                        }
                        renderEmployees(b.searchInput.text?.toString().orEmpty())
                    }
                    1 -> {
                        b.searchWrap.visibility = View.GONE
                        val deps = ApiClient.api().departments().body().orEmpty()
                        renderNamed(deps.map { SimpleRow(it.name, payload = it) }) { row ->
                            val item = row.payload as com.itguy.assetmanager.data.model.NamedItem
                            ApiClient.api().deleteDepartment(com.itguy.assetmanager.data.model.IdRequest(item.id))
                            load()
                        }
                    }
                    2 -> {
                        b.searchWrap.visibility = View.GONE
                        val des = ApiClient.api().designations().body().orEmpty()
                        renderNamed(des.map { SimpleRow(it.name, payload = it) }) { row ->
                            val item = row.payload as com.itguy.assetmanager.data.model.NamedItem
                            ApiClient.api().deleteDesignation(com.itguy.assetmanager.data.model.IdRequest(item.id))
                            load()
                        }
                    }
                }
            } catch (e: Exception) {
                if (_b == null) return@launch
                // network hiccup: fall back to the cached directory on the
                // Employees tab rather than showing an error
                val cached = com.itguy.assetmanager.data.OfflineCache.loadEmployees()
                if (tab == 0 && cached != null) {
                    employees = cached
                    renderEmployees(b.searchInput.text?.toString().orEmpty())
                    b.emptyText.text = "📡 Offline — showing cached directory"
                } else {
                    b.emptyText.text = "Could not load: ${e.message}"; b.emptyText.visibility = View.VISIBLE
                }
            }
        }
    }

    private fun renderEmployees(query: String) {
        if (_b == null) return
        val filtered = if (query.isBlank()) employees else employees.filter {
            it.EmployeeName.contains(query, true) || it.EmployeeID.contains(query, true) || it.Department.contains(query, true)
        }
        val rows = filtered.map { e ->
            SimpleRow(e.EmployeeName.ifBlank { e.EmployeeID }, listOfNotNull(e.EmployeeID, e.Department.ifBlank { null }, e.Designation.ifBlank { null }).joinToString(" · "), e)
        }
        adapter = SimpleAdapter(onClick = { row -> openEmployeeForm((row.payload as Employee).id) }, onDelete = { row ->
            val e = row.payload as Employee
            lifecycleScope.launch { ApiClient.api().deleteEmployee(e.id ?: return@launch); load() }
        })
        b.recycler.adapter = adapter
        adapter.submit(rows)
        b.emptyText.visibility = if (rows.isEmpty()) View.VISIBLE else View.GONE
        b.emptyText.text = "No employees found"
    }

    private fun renderNamed(rows: List<SimpleRow>, onDelete: suspend (SimpleRow) -> Unit) {
        if (_b == null) return
        adapter = SimpleAdapter(onDelete = { row -> lifecycleScope.launch { onDelete(row) } })
        b.recycler.adapter = adapter
        adapter.submit(rows)
        b.emptyText.visibility = if (rows.isEmpty()) View.VISIBLE else View.GONE
        b.emptyText.text = "None yet"
    }

    private fun onAdd() {
        when (tab) {
            0 -> openEmployeeForm(null)
            1 -> promptName("New department") { name -> lifecycleScope.launch { ApiClient.api().addDepartment(NameOnly(name)); load() } }
            2 -> promptName("New designation") { name -> lifecycleScope.launch { ApiClient.api().addDesignation(NameOnly(name)); load() } }
        }
    }

    private fun openEmployeeForm(employeeId: String?) {
        (activity as? MainActivity)?.showFragment(
            EmployeeEditFragment.newInstance(employeeId),
            if (employeeId == null) "Add Employee" else "Edit Employee",
            addToBackStack = true
        )
    }

    private fun promptName(title: String, onValue: (String) -> Unit) {
        val edit = EditText(requireContext())
        AlertDialog.Builder(requireContext()).setTitle(title).setView(edit)
            .setPositiveButton("Add") { _, _ -> edit.text?.toString()?.trim()?.takeIf { it.isNotBlank() }?.let(onValue) }
            .setNegativeButton("Cancel", null).show()
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
