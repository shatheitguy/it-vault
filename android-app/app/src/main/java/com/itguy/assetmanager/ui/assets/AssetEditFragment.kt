package com.itguy.assetmanager.ui.assets

import android.app.AlertDialog
import android.app.DatePickerDialog
import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.EditText
import androidx.activity.result.contract.ActivityResultContracts
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.model.*
import com.itguy.assetmanager.databinding.FragmentAssetEditBinding
import kotlinx.coroutines.launch
import java.util.Calendar

class AssetEditFragment : Fragment() {

    private var _b: FragmentAssetEditBinding? = null
    private val b get() = _b!!
    private var assetId: String? = null
    private var current: Asset = Asset()

    private var categories: List<NamedItem> = emptyList()
    private var manufacturers: List<NamedItem> = emptyList()
    private var models: List<ModelItem> = emptyList()
    private var locations: List<LocationItem> = emptyList()
    private var employees: List<Employee> = emptyList()

    private val STATUSES = listOf("Available", "Checked-Out", "Under-Maintenance", "Storage", "Retired")
    private val ADD_NEW = "＋ Add new…"
    private val NONE = "-- select --"

    private val scanLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        result.data?.getStringExtra(ScanActivity.EXTRA_RESULT)?.let { applyScannedText(it); return@registerForActivityResult }
        result.data?.getStringExtra(ScanActivity.EXTRA_TEXT_RESULT)?.let { applyOcrText(it) }
    }

    companion object {
        fun newInstance(assetId: String?): AssetEditFragment {
            val f = AssetEditFragment()
            f.arguments = Bundle().apply { putString("assetId", assetId) }
            return f
        }
    }

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        _b = FragmentAssetEditBinding.inflate(inflater, container, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        assetId = arguments?.getString("assetId")
        b.deleteBtn.visibility = if (assetId != null) View.VISIBLE else View.GONE

        setupDatePicker(b.fPurchaseDate)
        setupDatePicker(b.fNotesReceived)

        b.scanBtn.setOnClickListener { scanLauncher.launch(Intent(requireContext(), ScanActivity::class.java)) }
        b.saveBtn.setOnClickListener { save() }
        b.deleteBtn.setOnClickListener { confirmDelete() }

        loadReferenceDataAndAsset()
    }

    private fun setupDatePicker(edit: EditText) {
        edit.setOnClickListener {
            val cal = Calendar.getInstance()
            DatePickerDialog(requireContext(), { _, y, m, d ->
                edit.setText(String.format("%04d-%02d-%02d", y, m + 1, d))
            }, cal.get(Calendar.YEAR), cal.get(Calendar.MONTH), cal.get(Calendar.DAY_OF_MONTH)).show()
        }
    }

    private fun loadReferenceDataAndAsset() {
        b.formProgress.visibility = View.VISIBLE
        lifecycleScope.launch {
            try {
                val api = ApiClient.api()
                categories = api.categories().body().orEmpty()
                manufacturers = api.manufacturers().body().orEmpty()
                models = api.models().body().orEmpty()
                locations = api.locations().body().orEmpty()
                employees = api.listEmployees().body().orEmpty()

                current = if (assetId != null) {
                    api.getAsset(assetId!!).body() ?: Asset()
                } else Asset()

                if (_b == null) return@launch
                bindStatusSpinner()
                bindCategorySpinner()
                bindLocationSpinner()
                bindManufacturerSpinner()
                bindModelSpinner(current.Manufacturer)
                bindEmployeeSpinner()
                populatePlainFields()
            } catch (e: Exception) {
                if (_b != null) { b.formError.text = "Could not load form: ${e.message}"; b.formError.visibility = View.VISIBLE }
            } finally {
                _b?.formProgress?.visibility = View.GONE
            }
        }
    }

    private fun populatePlainFields() {
        b.fName.setText(current.Name)
        b.fSerial.setText(current.Serial)
        b.fMacAddress.setText(current.MacAddress)
        b.fPurchaseDate.setText(current.PurchaseDate)
        b.fWarrantyMonths.setText(if (current.WarrantyMonths > 0) current.WarrantyMonths.toString() else "12")
        b.fPrice.setText(current.Price)
        b.fReceivedBy.setText(current.ReceivedBy)
        b.fNotesReceived.setText(current.NotesReceived)
        b.fNote.setText(current.Note)
    }

    // ---- Status (fixed list) ----
    private fun bindStatusSpinner() {
        val adapter = ArrayAdapter(requireContext(), android.R.layout.simple_spinner_dropdown_item, STATUSES)
        b.fStatus.adapter = adapter
        val idx = STATUSES.indexOf(current.Status.ifBlank { "Available" }).coerceAtLeast(0)
        b.fStatus.setSelection(idx)
    }

    // ---- Category (Type) ----
    private fun bindCategorySpinner() {
        val labels = mutableListOf(NONE) + categories.map { it.name } + ADD_NEW
        val sel = current.Type
        val list = if (sel.isNotBlank() && categories.none { it.name == sel }) {
            (mutableListOf(NONE, sel) + categories.map { it.name } + ADD_NEW)
        } else labels
        setSpinner(b.fType, list, sel) { newVal ->
            ApiClient.api().addCategory(NameOnly(newVal))
            categories = ApiClient.api().categories().body().orEmpty()
            bindCategorySpinnerWithSelection(newVal)
        }
    }
    private fun bindCategorySpinnerWithSelection(sel: String) {
        val list = mutableListOf(NONE) + categories.map { it.name } + ADD_NEW
        setSpinner(b.fType, list, sel) { newVal ->
            ApiClient.api().addCategory(NameOnly(newVal))
            categories = ApiClient.api().categories().body().orEmpty()
            bindCategorySpinnerWithSelection(newVal)
        }
    }

    // ---- Location ----
    private fun bindLocationSpinner() {
        val sel = current.Location
        val names = locations.map { it.name }
        val list = if (sel.isNotBlank() && names.none { it == sel }) mutableListOf(NONE, sel) + names + ADD_NEW
        else mutableListOf(NONE) + names + ADD_NEW
        setSpinner(b.fLocation, list, sel) { newVal ->
            ApiClient.api().addLocation(NameOnly(newVal))
            locations = ApiClient.api().locations().body().orEmpty()
            val list2 = mutableListOf(NONE) + locations.map { it.name } + ADD_NEW
            setSpinner(b.fLocation, list2, newVal) {}
        }
    }

    // ---- Manufacturer + Model (Model filtered by chosen Manufacturer) ----
    private fun bindManufacturerSpinner() {
        val sel = current.Manufacturer
        val names = manufacturers.map { it.name }
        val list = if (sel.isNotBlank() && names.none { it == sel }) mutableListOf(NONE, sel) + names + ADD_NEW
        else mutableListOf(NONE) + names + ADD_NEW
        setSpinner(b.fManufacturer, list, sel, onSelected = { chosen ->
            bindModelSpinner(if (chosen == NONE) "" else chosen)
        }, onAddNew = { newVal ->
            ApiClient.api().addManufacturer(NameOnly(newVal))
            manufacturers = ApiClient.api().manufacturers().body().orEmpty()
            val list2 = mutableListOf(NONE) + manufacturers.map { it.name } + ADD_NEW
            setSpinner(b.fManufacturer, list2, newVal, onSelected = { chosen -> bindModelSpinner(if (chosen == NONE) "" else chosen) }, onAddNew = null)
        })
    }

    private fun bindModelSpinner(forManufacturer: String) {
        val filtered = if (forManufacturer.isBlank()) models else models.filter { it.manufacturer == forManufacturer }
        val sel = current.Model
        val names = filtered.map { it.name }
        val list = if (sel.isNotBlank() && names.none { it == sel }) mutableListOf(NONE, sel) + names + ADD_NEW
        else mutableListOf(NONE) + names + ADD_NEW
        setSpinner(b.fModel, list, sel) { newVal ->
            val mfrId = manufacturers.firstOrNull { it.name == forManufacturer }?.id
            val body = mapOf("name" to newVal, "manufacturer_id" to mfrId)
            ApiClient.api().addModel(body)
            models = ApiClient.api().models().body().orEmpty()
            bindModelSpinner(forManufacturer)
        }
    }

    // ---- Employee ----
    private fun bindEmployeeSpinner() {
        val labels = mutableListOf(NONE) + employees.map { "${it.EmployeeName} (${it.EmployeeID})" }
        val currentLabel = employees.firstOrNull { it.EmployeeID == current.EmployeeID }?.let { "${it.EmployeeName} (${it.EmployeeID})" } ?: NONE
        val adapter = ArrayAdapter(requireContext(), android.R.layout.simple_spinner_dropdown_item, labels)
        b.fEmployeeID.adapter = adapter
        val idx = labels.indexOf(currentLabel).coerceAtLeast(0)
        b.fEmployeeID.setSelection(idx)
    }

    private fun setSpinner(
        spinner: android.widget.Spinner,
        items: List<String>,
        selected: String,
        onSelected: ((String) -> Unit)? = null,
        onAddNew: (suspend (String) -> Unit)?
    ) {
        val adapter = ArrayAdapter(requireContext(), android.R.layout.simple_spinner_dropdown_item, items)
        spinner.adapter = adapter
        val idx = items.indexOf(selected.ifBlank { NONE }).let { if (it < 0) 0 else it }
        spinner.setSelection(idx)
        spinner.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) {
                val value = items[position]
                if (value == ADD_NEW && onAddNew != null) {
                    promptNewValue { text -> lifecycleScope.launch { onAddNew(text) } }
                    spinner.setSelection(idx) // revert visually until the new item is added & re-selected
                } else {
                    onSelected?.invoke(value)
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
        val name = b.fName.text?.toString()?.trim().orEmpty()
        if (name.isBlank()) { b.formError.text = "Name is required"; b.formError.visibility = View.VISIBLE; return }

        val employeeLabel = b.fEmployeeID.selectedItem?.toString() ?: NONE
        val employeeId = if (employeeLabel == NONE) "" else {
            val idx = employeeLabel.lastIndexOf("(")
            if (idx >= 0) employeeLabel.substring(idx + 1, employeeLabel.length - 1) else ""
        }

        val asset = current.copy(
            Name = name,
            Type = spinnerText(b.fType),
            Serial = b.fSerial.text?.toString()?.trim().orEmpty(),
            MacAddress = b.fMacAddress.text?.toString()?.trim().orEmpty(),
            Location = spinnerText(b.fLocation),
            Status = b.fStatus.selectedItem?.toString() ?: "Available",
            Manufacturer = spinnerText(b.fManufacturer),
            Model = spinnerText(b.fModel),
            ReceivedBy = b.fReceivedBy.text?.toString()?.trim().orEmpty(),
            NotesReceived = b.fNotesReceived.text?.toString()?.trim().orEmpty(),
            Note = b.fNote.text?.toString()?.trim().orEmpty(),
            PurchaseDate = b.fPurchaseDate.text?.toString()?.trim().orEmpty(),
            WarrantyMonths = b.fWarrantyMonths.text?.toString()?.toIntOrNull() ?: 12,
            Price = b.fPrice.text?.toString()?.trim().ifNullOrBlank("0"),
            EmployeeID = employeeId
        )

        b.formProgress.visibility = View.VISIBLE
        b.saveBtn.isEnabled = false
        lifecycleScope.launch {
            try {
                val api = ApiClient.api()
                val id = assetId
                if (id == null) {
                    val resp = api.createAsset(asset)
                    if (resp.isSuccessful && resp.body()?.ok == true) {
                        requireActivity().onBackPressedDispatcher.onBackPressed()
                    } else {
                        showFormError(resp)
                    }
                } else {
                    val resp = api.updateAsset(id, asset)
                    if (resp.isSuccessful && resp.body()?.ok == true) {
                        requireActivity().onBackPressedDispatcher.onBackPressed()
                    } else {
                        showFormError(resp)
                    }
                }
            } catch (e: Exception) {
                if (_b != null) { b.formError.text = "Save failed: ${e.message}"; b.formError.visibility = View.VISIBLE }
            } finally {
                _b?.formProgress?.visibility = View.GONE
                _b?.saveBtn?.isEnabled = true
            }
        }
    }

    private fun <T> showFormError(resp: retrofit2.Response<T>) {
        if (_b == null) return
        val msg = try {
            resp.errorBody()?.string()?.let { org.json.JSONObject(it).optString("error") }
        } catch (e: Exception) { null } ?: "Save failed"
        b.formError.text = msg
        b.formError.visibility = View.VISIBLE
    }

    private fun confirmDelete() {
        AlertDialog.Builder(requireContext())
            .setTitle("Delete asset?")
            .setMessage("This moves it to Trash.")
            .setPositiveButton("Delete") { _, _ ->
                val id = assetId ?: return@setPositiveButton
                lifecycleScope.launch {
                    try {
                        ApiClient.api().deleteAsset(id)
                        requireActivity().onBackPressedDispatcher.onBackPressed()
                    } catch (e: Exception) {
                        if (_b != null) { b.formError.text = "Delete failed: ${e.message}"; b.formError.visibility = View.VISIBLE }
                    }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    /** Mirrors the web app's camera-scan logic: JSON payload -> fill matching fields, otherwise treat as a raw Serial Number. */
    private fun applyScannedText(text: String) {
        try {
            val obj = org.json.JSONObject(text)
            val keys = obj.keys().asSequence().associate { it.lowercase().replace(Regex("[^a-z0-9]"), "") to obj.optString(it) }
            fun pick(vararg names: String): String? = names.firstNotNullOfOrNull { keys[it]?.takeIf { v -> v.isNotBlank() } }
            pick("name", "assetname")?.let { b.fName.setText(it) }
            pick("serial", "serialnumber", "sn")?.let { b.fSerial.setText(it) }
            pick("mac", "macaddress")?.let { b.fMacAddress.setText(it) }
            pick("type", "category", "itemcategory")?.let { current = current.copy(Type = it); bindCategorySpinnerWithSelection(it) }
            pick("location", "site")?.let { locSel -> current = current.copy(Location = locSel); bindLocationSpinner() }
        } catch (e: Exception) {
            // not JSON -> treat as a plain serial number (the common case for a SN barcode sticker)
            b.fSerial.setText(text)
        }
    }

    /** Best-effort OCR label parser: looks for common "S/N: X", "Model: X",
     * "MAC: X" style lines -- also handling the label and value sitting on
     * separate lines, which is common on printed asset stickers -- and
     * fills the matching fields (e.g. "SNO" -> Serial, "Model" -> Model). */
    private fun applyOcrText(text: String) {
        val lines = text.lines().map { it.trim() }.filter { it.isNotBlank() }

        fun findLabeled(aliasesLongestFirst: List<String>): String? {
            val aliasPattern = aliasesLongestFirst.joinToString("|") { Regex.escape(it) }
            val sameLine = Regex("""(?i)\b($aliasPattern)\b\.?\s*[:\-]\s*(.+)""")
            for (line in lines) {
                sameLine.find(line)?.let { m -> val v = m.groupValues[2].trim(); if (v.isNotBlank()) return v }
            }
            for (i in lines.indices) {
                val norm = lines[i].trimEnd(':').trim()
                if (aliasesLongestFirst.any { it.equals(norm, ignoreCase = true) } && i + 1 < lines.size) {
                    val v = lines[i + 1].trim()
                    if (v.isNotBlank()) return v
                }
            }
            return null
        }

        val serial = findLabeled(listOf("serial number", "serial no", "serial#", "s/n", "sno", "sn", "serial"))
        val model = findLabeled(listOf("model number", "model no", "model"))
        val mfr = findLabeled(listOf("manufacturer", "brand", "make"))
        var mac = findLabeled(listOf("mac address", "mac id", "mac"))
        if (mac == null) mac = Regex("""([0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}""").find(text)?.value

        val filled = mutableListOf<String>()
        if (serial != null) { b.fSerial.setText(serial); filled.add("Serial") }
        if (mac != null) { b.fMacAddress.setText(mac); filled.add("MAC") }
        if (mfr != null || model != null) {
            current = current.copy(Manufacturer = mfr ?: current.Manufacturer, Model = model ?: current.Model)
            bindManufacturerSpinner()
            if (mfr != null) filled.add("Manufacturer")
            if (model != null) filled.add("Model")
        }

        val msg = if (filled.isEmpty()) "Couldn't recognize S/N, Model, or MAC on that label -- try getting closer or better lighting"
        else "✓ Filled from label: ${filled.joinToString(", ")}"
        android.widget.Toast.makeText(requireContext(), msg, android.widget.Toast.LENGTH_LONG).show()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _b = null
    }
}

private fun String?.ifNullOrBlank(fallback: String): String = if (this.isNullOrBlank()) fallback else this
