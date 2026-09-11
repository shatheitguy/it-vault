package com.itguy.assetmanager.ui.contracts

import android.app.AlertDialog
import android.app.DatePickerDialog
import android.content.Context
import android.print.PrintAttributes
import android.print.PrintManager
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.ArrayAdapter
import android.widget.EditText
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import android.widget.Toast
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.Repository
import com.itguy.assetmanager.data.Prefs
import com.itguy.assetmanager.data.model.Asset
import com.itguy.assetmanager.data.model.Contract
import com.itguy.assetmanager.data.model.Employee
import com.itguy.assetmanager.data.model.IdRequest
import com.itguy.assetmanager.data.model.LocationItem
import com.itguy.assetmanager.data.model.NamedItem
import com.itguy.assetmanager.data.model.NameOnly
import com.itguy.assetmanager.databinding.FragmentContractEditBinding
import kotlinx.coroutines.launch
import java.util.Calendar

/** Add/edit a Contract -- AMC (Annual Maintenance Contract) with an outside
 * company, license, subscription, warranty, or support agreement. Follows
 * the same modal-style layout and Save/Delete pattern as the Asset form. */
class ContractEditFragment : Fragment() {
    private var _b: FragmentContractEditBinding? = null
    private val b get() = _b!!
    private var contractId = 0
    private var current: Contract = Contract()
    private var assets: List<Asset> = emptyList()
    private var employees: List<Employee> = emptyList()
    private var locations: List<LocationItem> = emptyList()
    private var departments: List<NamedItem> = emptyList()
    private var printWebView: WebView? = null

    private var TYPES: List<String> = listOf("AMC", "License", "Subscription", "Warranty", "Support", "Lease", "Other")
    private val ADD_NEW = "＋ Add new…"

    companion object {
        fun newInstance(contractId: Int) = ContractEditFragment().apply {
            arguments = Bundle().apply { putInt("id", contractId) }
        }
    }

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        _b = FragmentContractEditBinding.inflate(inflater, container, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        contractId = arguments?.getInt("id") ?: 0
        b.deleteBtn.visibility = if (contractId != 0) View.VISIBLE else View.GONE
        b.printBtn.visibility = if (contractId != 0) View.VISIBLE else View.GONE

        setupDatePicker(b.fStart)
        setupDatePicker(b.fEnd)
        b.saveBtn.setOnClickListener { save() }
        b.deleteBtn.setOnClickListener { confirmDelete() }
        b.printBtn.setOnClickListener { printContract() }

        load()
    }

    private fun setupDatePicker(edit: EditText) {
        edit.setOnClickListener {
            val cal = Calendar.getInstance()
            DatePickerDialog(requireContext(), { _, y, m, d ->
                edit.setText(String.format("%04d-%02d-%02d", y, m + 1, d))
            }, cal.get(Calendar.YEAR), cal.get(Calendar.MONTH), cal.get(Calendar.DAY_OF_MONTH)).show()
        }
    }

    private fun load() {
        b.formProgress.visibility = View.VISIBLE
        lifecycleScope.launch {
            try {
                val api = ApiClient.api()
                assets = api.listAssets().body().orEmpty()
                employees = api.listEmployees().body().orEmpty()
                locations = api.locations().body().orEmpty()
                departments = api.departments().body().orEmpty()
                val types = api.contractTypes().body().orEmpty().map { it.name }
                if (types.isNotEmpty()) TYPES = types
                current = if (contractId != 0) {
                    api.contracts().body().orEmpty().firstOrNull { it.id == contractId } ?: Contract()
                } else Contract()
                if (_b == null) return@launch
                bindTypeSpinner()
                bindAssetSpinner()
                bindEmployeeSpinner()
                bindLocationSpinner()
                bindDepartmentSpinner()
                populateFields()
            } catch (e: Exception) {
                if (_b != null) { b.formError.text = "Could not load form: ${e.message}"; b.formError.visibility = View.VISIBLE }
            } finally {
                _b?.formProgress?.visibility = View.GONE
            }
        }
    }

    private fun populateFields() {
        b.fName.setText(current.name)
        b.fVendor.setText(current.vendor)
        b.fCost.setText(if (current.cost > 0) current.cost.toString() else "")
        b.fStart.setText(current.start_date)
        b.fEnd.setText(current.end_date)
        b.fLicenseKey.setText(current.license_key)
        b.fNote.setText(current.note)
    }

    private fun bindTypeSpinner() {
        val sel = current.type.ifBlank { "AMC" }
        val list = if (TYPES.none { it == sel }) mutableListOf(sel) + TYPES + ADD_NEW else TYPES + ADD_NEW
        val adapter = ArrayAdapter(requireContext(), android.R.layout.simple_spinner_dropdown_item, list)
        b.fType.adapter = adapter
        val idx = list.indexOf(sel).coerceAtLeast(0)
        b.fType.setSelection(idx)
        toggleLicenseKeyField(list[idx])
        b.fType.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) {
                val value = list[position]
                if (value == ADD_NEW) {
                    promptNewType()
                    b.fType.setSelection(idx)
                } else {
                    toggleLicenseKeyField(value)
                }
            }
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {}
        }
    }

    private fun promptNewType() {
        val edit = EditText(requireContext())
        AlertDialog.Builder(requireContext())
            .setTitle("New contract type")
            .setView(edit)
            .setPositiveButton("Add") { _, _ ->
                val v = edit.text?.toString()?.trim().orEmpty()
                if (v.isNotBlank()) {
                    lifecycleScope.launch {
                        ApiClient.api().addContractType(NameOnly(v))
                        val types = ApiClient.api().contractTypes().body().orEmpty().map { it.name }
                        if (types.isNotEmpty()) TYPES = types
                        current = current.copy(type = v)
                        if (_b != null) bindTypeSpinner()
                    }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun toggleLicenseKeyField(type: String) {
        b.fLicenseKeyWrap.visibility = if (type == "License") View.VISIBLE else View.GONE
    }

    private fun bindAssetSpinner() {
        val labels = mutableListOf("-- none --") + assets.map { "${it.Name} (${it.Serial.ifBlank { "no S/N" }}) — ID ${it.AssetTag.ifBlank { it.id ?: "" }}" }
        val adapter = ArrayAdapter(requireContext(), android.R.layout.simple_spinner_dropdown_item, labels)
        b.fAsset.adapter = adapter
        val idx = assets.indexOfFirst { it.id == current.asset_id }
        b.fAsset.setSelection(if (idx >= 0) idx + 1 else 0)
    }

    private fun bindEmployeeSpinner() {
        val labels = mutableListOf("-- none --") + employees.map { it.EmployeeName.ifBlank { it.EmployeeID } }
        b.fEmployee.adapter = ArrayAdapter(requireContext(), android.R.layout.simple_spinner_dropdown_item, labels)
        val idx = employees.indexOfFirst { it.EmployeeID == current.employee_id }
        b.fEmployee.setSelection(if (idx >= 0) idx + 1 else 0)
    }

    private fun bindLocationSpinner() {
        val sel = current.location
        val labels = mutableListOf("-- none --") + locations.map { it.name } + ADD_NEW
        b.fLocation.adapter = ArrayAdapter(requireContext(), android.R.layout.simple_spinner_dropdown_item, labels)
        val idx = locations.indexOfFirst { it.name == sel }
        val selIdx = if (idx >= 0) idx + 1 else 0
        b.fLocation.setSelection(selIdx)
        b.fLocation.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) {
                if (labels[position] == ADD_NEW) {
                    promptNewValue("New location") { v ->
                        lifecycleScope.launch {
                            ApiClient.api().addLocation(NameOnly(v))
                            locations = ApiClient.api().locations().body().orEmpty()
                            current = current.copy(location = v)
                            if (_b != null) bindLocationSpinner()
                        }
                    }
                    b.fLocation.setSelection(selIdx)
                }
            }
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {}
        }
    }

    private fun bindDepartmentSpinner() {
        val sel = current.department
        val labels = mutableListOf("-- none --") + departments.map { it.name } + ADD_NEW
        b.fDepartment.adapter = ArrayAdapter(requireContext(), android.R.layout.simple_spinner_dropdown_item, labels)
        val idx = departments.indexOfFirst { it.name == sel }
        val selIdx = if (idx >= 0) idx + 1 else 0
        b.fDepartment.setSelection(selIdx)
        b.fDepartment.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) {
                if (labels[position] == ADD_NEW) {
                    promptNewValue("New department") { v ->
                        lifecycleScope.launch {
                            ApiClient.api().addDepartment(NameOnly(v))
                            departments = ApiClient.api().departments().body().orEmpty()
                            current = current.copy(department = v)
                            if (_b != null) bindDepartmentSpinner()
                        }
                    }
                    b.fDepartment.setSelection(selIdx)
                }
            }
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {}
        }
    }

    private fun promptNewValue(title: String, onValue: (String) -> Unit) {
        val edit = EditText(requireContext())
        AlertDialog.Builder(requireContext())
            .setTitle(title)
            .setView(edit)
            .setPositiveButton("Add") { _, _ ->
                val v = edit.text?.toString()?.trim().orEmpty()
                if (v.isNotBlank()) onValue(v)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun save() {
        b.formError.visibility = View.GONE
        val name = b.fName.text?.toString()?.trim().orEmpty()
        if (name.isBlank()) { b.formError.text = "Name is required"; b.formError.visibility = View.VISIBLE; return }

        val assetIdx = b.fAsset.selectedItemPosition
        val assetId = if (assetIdx > 0) assets[assetIdx - 1].id else null
        val empIdx = b.fEmployee.selectedItemPosition
        val employeeId = if (empIdx > 0) employees[empIdx - 1].EmployeeID else ""
        val locIdx = b.fLocation.selectedItemPosition
        val location = if (locIdx > 0) locations[locIdx - 1].name else ""
        val depIdx = b.fDepartment.selectedItemPosition
        val department = if (depIdx > 0) departments[depIdx - 1].name else ""

        val type = b.fType.selectedItem?.toString()?.takeIf { it != ADD_NEW } ?: current.type
        val contract = current.copy(
            name = name,
            type = type,
            vendor = b.fVendor.text?.toString()?.trim().orEmpty(),
            cost = b.fCost.text?.toString()?.toDoubleOrNull() ?: 0.0,
            start_date = b.fStart.text?.toString()?.trim().orEmpty(),
            end_date = b.fEnd.text?.toString()?.trim().orEmpty(),
            asset_id = assetId,
            employee_id = employeeId,
            location = location,
            department = department,
            license_key = if (type == "License") b.fLicenseKey.text?.toString()?.trim().orEmpty() else "",
            note = b.fNote.text?.toString()?.trim().orEmpty()
        )

        b.formProgress.visibility = View.VISIBLE
        b.saveBtn.isEnabled = false
        lifecycleScope.launch {
            try {
                val toSave = if (contractId == 0) contract else contract.copy(id = contractId)
                when (val r = Repository.saveContract(requireContext(), toSave, isNew = contractId == 0)) {
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
        AlertDialog.Builder(requireContext())
            .setTitle("Delete this contract?")
            .setMessage("This cannot be undone.")
            .setPositiveButton("Delete") { _, _ ->
                lifecycleScope.launch {
                    try {
                        val r = Repository.deleteContract(requireContext(), contractId)
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

    /** Uses Android's native print framework (WebView -> PrintDocumentAdapter)
     * so this genuinely opens the system print/PDF dialog, same idea as the
     * web app's window.print() on the printable contract record. */
    private fun printContract() {
        val html = buildPrintHtml()
        val webView = WebView(requireContext())
        printWebView = webView
        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView, url: String) {
                val printManager = requireContext().getSystemService(Context.PRINT_SERVICE) as PrintManager
                val jobName = "Contract - ${current.name.ifBlank { "record" }}"
                val adapter = view.createPrintDocumentAdapter(jobName)
                val attrs = PrintAttributes.Builder().setMediaSize(PrintAttributes.MediaSize.ISO_A4).build()
                printManager.print(jobName, adapter, attrs)
            }
        }
        webView.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null)
    }

    private fun buildPrintHtml(): String {
        fun row(k: String, v: String) = "<tr><td style='width:38%;padding:5px 8px;color:#555;font-weight:600;border-bottom:1px solid #eee'>$k</td><td style='padding:5px 8px;border-bottom:1px solid #eee'>${v.ifBlank { "—" }}</td></tr>"
        val assetLabel = assets.firstOrNull { it.id == current.asset_id }
            ?.let { "${it.Name} (${it.Serial.ifBlank { "no S/N" }}) — ID ${it.AssetTag.ifBlank { it.id ?: "" }}" } ?: "—"
        val employeeLabel = employees.firstOrNull { it.EmployeeID == current.employee_id }
            ?.let { it.EmployeeName.ifBlank { it.EmployeeID } } ?: "—"
        val logoUrl = Prefs.serverUrl.trimEnd('/') + "/logo.png"
        val letterheadUrl = Prefs.serverUrl.trimEnd('/') + "/letterhead.png"
        return """
            <html><body style='font-family:sans-serif;padding:16px;color:#111'>
            <img id='lh' src='$letterheadUrl' style='display:none;width:100%;max-height:160px;object-fit:contain;margin-bottom:12px'
              onload="if(this.naturalWidth>2){this.style.display='block';document.getElementById('plainhd').style.display='none';}"
              onerror="this.style.display='none'">
            <div id='plainhd' style='display:flex;align-items:center;gap:10px;margin-bottom:12px'>
              <img src='$logoUrl' style='height:28px' onerror="this.style.display='none'">
              <h2 style='margin:0'>IT-Vault &mdash; Contract record</h2>
            </div>
            <table style='width:100%;border-collapse:collapse'>
            ${row("Name", current.name)}
            ${row("Type", current.type)}
            ${row("Vendor / Company", current.vendor)}
            ${row("Cost", current.cost.toString())}
            ${row("Start Date", current.start_date)}
            ${row("End / Renewal Date", current.end_date)}
            ${row("Linked Asset", assetLabel)}
            ${row("Employee", employeeLabel)}
            ${row("Location", current.location)}
            ${row("Department", current.department)}
            ${if (current.type == "License" && current.license_key.isNotBlank()) row("License Key", current.license_key) else ""}
            ${row("Note", current.note)}
            </table>
            </body></html>
        """.trimIndent()
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null; printWebView = null }
}
