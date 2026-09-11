package com.itguy.assetmanager.ui.employees

import android.app.AlertDialog
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.EditText
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import android.widget.Toast
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.Repository
import com.itguy.assetmanager.data.model.Employee
import com.itguy.assetmanager.data.model.NameOnly
import com.itguy.assetmanager.data.model.NamedItem
import com.itguy.assetmanager.databinding.FragmentEmployeeEditBinding
import kotlinx.coroutines.launch

/** Add/edit an employee -- same dedicated-screen + real-Spinner pattern as
 * the Asset and Contract forms (previously this was a plain AlertDialog with
 * free-text Department/Designation fields instead of managed dropdowns). */
class EmployeeEditFragment : Fragment() {
    private var _b: FragmentEmployeeEditBinding? = null
    private val b get() = _b!!
    private var employeeId: String? = null
    private var current: Employee = Employee()
    private var departments: List<NamedItem> = emptyList()
    private var designations: List<NamedItem> = emptyList()

    private val NONE = "-- select --"
    private val ADD_NEW = "＋ Add new…"

    companion object {
        fun newInstance(employeeId: String?): EmployeeEditFragment {
            val f = EmployeeEditFragment()
            f.arguments = Bundle().apply { putString("employeeId", employeeId) }
            return f
        }
    }

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        _b = FragmentEmployeeEditBinding.inflate(inflater, container, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        employeeId = arguments?.getString("employeeId")
        b.deleteBtn.visibility = if (employeeId != null) View.VISIBLE else View.GONE
        b.saveBtn.setOnClickListener { save() }
        b.deleteBtn.setOnClickListener { confirmDelete() }
        load()
    }

    private fun load() {
        b.formProgress.visibility = View.VISIBLE
        lifecycleScope.launch {
            try {
                val api = ApiClient.api()
                departments = api.departments().body().orEmpty()
                designations = api.designations().body().orEmpty()
                current = if (employeeId != null) {
                    api.listEmployees().body().orEmpty().firstOrNull { it.id == employeeId } ?: Employee()
                } else Employee()
                if (_b == null) return@launch
                bindDepartmentSpinner()
                bindDesignationSpinner()
                populateFields()
            } catch (e: Exception) {
                if (_b != null) { b.formError.text = "Could not load form: ${e.message}"; b.formError.visibility = View.VISIBLE }
            } finally {
                _b?.formProgress?.visibility = View.GONE
            }
        }
    }

    private fun populateFields() {
        b.fEmpCode.setText(current.EmpCode)
        b.fEmployeeID.setText(current.EmployeeID)
        b.fEmployeeName.setText(current.EmployeeName)
        b.fEmail.setText(current.Email)
    }

    private fun bindDepartmentSpinner() {
        val sel = current.Department
        val names = departments.map { it.name }
        val list = if (sel.isNotBlank() && names.none { it == sel }) mutableListOf(NONE, sel) + names + ADD_NEW
        else mutableListOf(NONE) + names + ADD_NEW
        setSpinner(b.fDepartment, list, sel) { newVal ->
            ApiClient.api().addDepartment(NameOnly(newVal))
            departments = ApiClient.api().departments().body().orEmpty()
            val list2 = mutableListOf(NONE) + departments.map { it.name } + ADD_NEW
            setSpinner(b.fDepartment, list2, newVal) {}
        }
    }

    private fun bindDesignationSpinner() {
        val sel = current.Designation
        val names = designations.map { it.name }
        val list = if (sel.isNotBlank() && names.none { it == sel }) mutableListOf(NONE, sel) + names + ADD_NEW
        else mutableListOf(NONE) + names + ADD_NEW
        setSpinner(b.fDesignation, list, sel) { newVal ->
            ApiClient.api().addDesignation(NameOnly(newVal))
            designations = ApiClient.api().designations().body().orEmpty()
            val list2 = mutableListOf(NONE) + designations.map { it.name } + ADD_NEW
            setSpinner(b.fDesignation, list2, newVal) {}
        }
    }

    private fun setSpinner(spinner: android.widget.Spinner, items: List<String>, selected: String, onAddNew: suspend (String) -> Unit) {
        val adapter = ArrayAdapter(requireContext(), android.R.layout.simple_spinner_dropdown_item, items)
        spinner.adapter = adapter
        val idx = items.indexOf(selected.ifBlank { NONE }).let { if (it < 0) 0 else it }
        spinner.setSelection(idx)
        spinner.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) {
                val value = items[position]
                if (value == ADD_NEW) {
                    promptNewValue { text -> lifecycleScope.launch { onAddNew(text) } }
                    spinner.setSelection(idx)
                }
            }
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {}
        }
    }

    private fun promptNewValue(onValue: (String) -> Unit) {
        val edit = EditText(requireContext())
        AlertDialog.Builder(requireContext())
            .setTitle("New value")
            .setView(edit)
            .setPositiveButton("Add") { _, _ ->
                val v = edit.text?.toString()?.trim().orEmpty()
                if (v.isNotBlank()) onValue(v)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun spinnerText(spinner: android.widget.Spinner): String {
        val v = spinner.selectedItem?.toString() ?: return ""
        return if (v == NONE || v == ADD_NEW) "" else v
    }

    private fun save() {
        b.formError.visibility = View.GONE
        val id = b.fEmployeeID.text?.toString()?.trim().orEmpty()
        val name = b.fEmployeeName.text?.toString()?.trim().orEmpty()
        if (id.isBlank() && name.isBlank()) { b.formError.text = "ID or Name required"; b.formError.visibility = View.VISIBLE; return }

        val emp = current.copy(
            EmployeeID = id,
            EmpCode = b.fEmpCode.text?.toString()?.trim().orEmpty(),
            EmployeeName = name,
            Department = spinnerText(b.fDepartment),
            Designation = spinnerText(b.fDesignation),
            Email = b.fEmail.text?.toString()?.trim().orEmpty()
        )

        b.formProgress.visibility = View.VISIBLE
        b.saveBtn.isEnabled = false
        lifecycleScope.launch {
            try {
                when (val r = Repository.saveEmployee(requireContext(), emp, employeeId)) {
                    is Repository.SaveResult.Synced ->
                        requireActivity().onBackPressedDispatcher.onBackPressed()
                    is Repository.SaveResult.Queued -> {
                        Toast.makeText(requireContext(),
                            "Saved offline — will sync when online", Toast.LENGTH_LONG).show()
                        requireActivity().onBackPressedDispatcher.onBackPressed()
                    }
                    is Repository.SaveResult.Error ->
                        if (_b != null) { b.formError.text = r.message; b.formError.visibility = View.VISIBLE }
                }
            } catch (e: Exception) {
                if (_b != null) { b.formError.text = "Save failed: ${e.message}"; b.formError.visibility = View.VISIBLE }
            } finally {
                _b?.formProgress?.visibility = View.GONE
                _b?.saveBtn?.isEnabled = true
            }
        }
    }

    private fun confirmDelete() {
        val id = employeeId ?: return
        AlertDialog.Builder(requireContext())
            .setTitle("Delete this employee?")
            .setMessage("This cannot be undone.")
            .setPositiveButton("Delete") { _, _ ->
                lifecycleScope.launch {
                    try {
                        val r = Repository.deleteEmployee(requireContext(), id)
                        if (r is Repository.SaveResult.Queued)
                            Toast.makeText(requireContext(), "Deleted offline — will sync when online", Toast.LENGTH_LONG).show()
                        requireActivity().onBackPressedDispatcher.onBackPressed()
                    } catch (e: Exception) {
                        if (_b != null) { b.formError.text = "Delete failed: ${e.message}"; b.formError.visibility = View.VISIBLE }
                    }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
