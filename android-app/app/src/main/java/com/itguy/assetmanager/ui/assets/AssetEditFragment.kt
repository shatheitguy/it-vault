package com.itguy.assetmanager.ui.assets

import android.app.AlertDialog
import android.app.DatePickerDialog
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.EditText
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.FileProvider
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.Repository
import com.itguy.assetmanager.data.model.*
import com.itguy.assetmanager.databinding.FragmentAssetEditBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
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

    private val STATUSES = listOf("Available", "Checked-Out", "Under-Maintenance", "Reserved", "Retired", "Lost/Stolen")
    private val ADD_NEW = "＋ Add new…"
    private val NONE = "-- select --"
    private val ALLOWED_INVOICE_EXT = setOf("pdf", "png", "jpg", "jpeg", "gif", "webp", "bmp", "tif", "tiff")

    private val scanLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        result.data?.getStringExtra(ScanActivity.EXTRA_RESULT)?.let { applyScannedText(it); return@registerForActivityResult }
        result.data?.getStringExtra(ScanActivity.EXTRA_TEXT_RESULT)?.let { applyOcrText(it) }
    }

    // Invoice/proof attachment: a newly-picked file isn't uploaded until Save
    // (mirrors the web form -- for a brand-new asset there's no _id to attach
    // it to until the asset itself is created).
    private var pickedInvoiceUri: Uri? = null
    private var pickedInvoiceName: String = ""
    private val pickInvoiceLauncher = registerForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri == null) return@registerForActivityResult
        val name = queryFileName(uri)
        val ext = name.substringAfterLast('.', "").lowercase()
        if (ext !in ALLOWED_INVOICE_EXT) {
            Toast.makeText(requireContext(), "Only PDF/image files allowed", Toast.LENGTH_LONG).show()
            return@registerForActivityResult
        }
        pickedInvoiceUri = uri
        pickedInvoiceName = name
        b.invoiceFileName.text = "$name (will be uploaded on save)"
    }

    companion object {
        /** [assignNow] opens the Assign dialog as soon as the asset has
         * loaded, so the action can be reached in one tap from the list
         * instead of only from inside this screen. */
        fun newInstance(assetId: String?, assignNow: Boolean = false): AssetEditFragment {
            val f = AssetEditFragment()
            f.arguments = Bundle().apply {
                putString("assetId", assetId)
                putBoolean("assignNow", assignNow)
            }
            return f
        }

        /** Opens a blank Add Asset form pre-filled from e.g. a Network Scan
         * result -- nothing is saved until the user hits Save, same as the
         * QR/label scanner and the web app's "add scanned device" flow. */
        fun newInstanceWithPrefill(name: String = "", mac: String = "", type: String = "", location: String = ""): AssetEditFragment {
            val f = AssetEditFragment()
            f.arguments = Bundle().apply {
                putString("assetId", null)
                putString("prefillName", name)
                putString("prefillMac", mac)
                putString("prefillType", type)
                putString("prefillLocation", location)
            }
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
        // Signed Date is set only by Check Out (see checkoutAsset()), never
        // freely edited here -- matches the web form's lock.
        b.fNotesReceived.isEnabled = false

        b.scanBtn.setOnClickListener { scanLauncher.launch(Intent(requireContext(), ScanActivity::class.java)) }
        b.saveBtn.setOnClickListener { save() }
        b.deleteBtn.setOnClickListener { confirmDelete() }
        b.invoicePickBtn.setOnClickListener { pickInvoiceLauncher.launch("*/*") }
        b.invoiceViewBtn.setOnClickListener { viewInvoice() }
        b.invoiceRemoveBtn.setOnClickListener { removeInvoice() }
        b.checkOutBtn.setOnClickListener { openCheckoutDialog() }
        b.checkInBtn.setOnClickListener { confirmCheckin() }

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
                // Each reference list is fetched independently and tolerates
                // failure, so the form still opens offline -- spinners just
                // fall back to the value already on the record.
                suspend fun <T> safe(block: suspend () -> List<T>): List<T> =
                    try { block() } catch (e: Exception) { emptyList() }
                categories = safe { api.categories().body().orEmpty() }
                manufacturers = safe { api.manufacturers().body().orEmpty() }
                models = safe { api.models().body().orEmpty() }
                locations = safe { api.locations().body().orEmpty() }
                employees = safe { api.listEmployees().body().orEmpty() }.ifEmpty {
                    com.itguy.assetmanager.data.OfflineCache.loadEmployees().orEmpty()
                }

                current = if (assetId != null) {
                    // editing: server copy if reachable, else the cached one
                    try { api.getAsset(assetId!!).body() }
                    catch (e: Exception) { null }
                    ?: com.itguy.assetmanager.data.OfflineCache.loadAssets()?.find { it.id == assetId }
                    ?: Asset()
                } else Asset(
                    AssetTag = try { api.nextAssetTag().body()?.tag.orEmpty() } catch (e: Exception) { "" },
                    Name = arguments?.getString("prefillName").orEmpty(),
                    MacAddress = arguments?.getString("prefillMac").orEmpty(),
                    Type = arguments?.getString("prefillType").orEmpty(),
                    Location = arguments?.getString("prefillLocation").orEmpty()
                )

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
        b.fAssetTag.setText(current.AssetTag)
        b.fName.setText(current.Name)
        b.fSerial.setText(current.Serial)
        b.fMacAddress.setText(current.MacAddress)
        b.fPurchaseDate.setText(current.PurchaseDate)
        b.fWarrantyMonths.setText(if (current.WarrantyMonths > 0) current.WarrantyMonths.toString() else "12")
        b.fPrice.setText(current.Price)
        b.fReceivedBy.setText(current.ReceivedBy)
        b.fNotesReceived.setText(current.NotesReceived)
        b.fNote.setText(current.Note)
        renderInvoiceState()

        val isExisting = assetId != null
        b.checkOutBtn.visibility = if (isExisting && current.Status != "Checked-Out") View.VISIBLE else View.GONE
        b.checkInBtn.visibility = if (isExisting && current.Status == "Checked-Out") View.VISIBLE else View.GONE

        // Opened from the list's Assign action: show the dialog straight away,
        // and only once, so returning to this screen does not reopen it.
        if (arguments?.getBoolean("assignNow") == true && b.checkOutBtn.visibility == View.VISIBLE) {
            arguments?.putBoolean("assignNow", false)
            b.checkOutBtn.post { if (isAdded) openCheckoutDialog() }
        }
    }

    /** Assign to an employee -- same "Signed Date defaults to today, only
     * changeable here" rule as the web Check Out dialog. */
    private fun openCheckoutDialog() {
        val id = assetId ?: return
        val ctx = requireContext()
        val pad = (16 * resources.displayMetrics.density).toInt()
        val layout = android.widget.LinearLayout(ctx).apply { orientation = android.widget.LinearLayout.VERTICAL; setPadding(pad, pad, pad, pad) }

        val userLabels = employees.map { it.EmployeeName.ifBlank { it.EmployeeID } }
        val userSpinner = android.widget.Spinner(ctx).apply {
            adapter = ArrayAdapter(ctx, android.R.layout.simple_spinner_dropdown_item, userLabels)
        }
        val today = java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US).format(java.util.Date())
        val signedDateField = EditText(ctx).apply { hint = "Signed date"; setText(today); isFocusable = false }
        signedDateField.setOnClickListener {
            val cal = Calendar.getInstance()
            DatePickerDialog(ctx, { _, y, m, d -> signedDateField.setText(String.format("%04d-%02d-%02d", y, m + 1, d)) },
                cal.get(Calendar.YEAR), cal.get(Calendar.MONTH), cal.get(Calendar.DAY_OF_MONTH)).show()
        }
        val expectedField = EditText(ctx).apply { hint = "Expected return (optional)" }
        expectedField.setOnClickListener {
            val cal = Calendar.getInstance()
            DatePickerDialog(ctx, { _, y, m, d -> expectedField.setText(String.format("%04d-%02d-%02d", y, m + 1, d)) },
                cal.get(Calendar.YEAR), cal.get(Calendar.MONTH), cal.get(Calendar.DAY_OF_MONTH)).show()
        }
        val noteField = EditText(ctx).apply { hint = "Note (optional)" }

        layout.addView(android.widget.TextView(ctx).apply { text = "Assign to"; setTextColor(resources.getColor(com.itguy.assetmanager.R.color.muted, null)) })
        layout.addView(userSpinner)
        layout.addView(signedDateField)
        layout.addView(expectedField)
        layout.addView(noteField)

        AlertDialog.Builder(ctx)
            .setTitle("Check Out Asset")
            .setView(layout)
            .setPositiveButton("Check Out") { _, _ ->
                val idx = userSpinner.selectedItemPosition
                if (idx < 0 || employees.isEmpty()) { Toast.makeText(ctx, "No employee selected", Toast.LENGTH_SHORT).show(); return@setPositiveButton }
                val username = employees[idx].EmployeeID
                val req = CheckoutRequest(
                    username = username,
                    signed_date = signedDateField.text?.toString()?.trim().orEmpty(),
                    expected = expectedField.text?.toString()?.trim().orEmpty(),
                    note = noteField.text?.toString()?.trim().orEmpty()
                )
                lifecycleScope.launch {
                    try {
                        ApiClient.api().checkoutAsset(id, req)
                        loadReferenceDataAndAsset()
                    } catch (e: Exception) {
                        Toast.makeText(ctx, "Check out failed: ${e.message}", Toast.LENGTH_LONG).show()
                    }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun confirmCheckin() {
        val id = assetId ?: return
        AlertDialog.Builder(requireContext())
            .setTitle("Check in this asset?")
            .setPositiveButton("Check In") { _, _ ->
                lifecycleScope.launch {
                    try {
                        ApiClient.api().checkinAsset(id)
                        loadReferenceDataAndAsset()
                    } catch (e: Exception) {
                        if (_b != null) Toast.makeText(requireContext(), "Check in failed: ${e.message}", Toast.LENGTH_LONG).show()
                    }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun renderInvoiceState() {
        val file = current.InvoiceFile
        if (pickedInvoiceUri != null) {
            b.invoiceFileName.text = "$pickedInvoiceName (will be uploaded on save)"
            b.invoiceViewBtn.visibility = View.GONE
            b.invoiceRemoveBtn.visibility = View.GONE
        } else if (!file.isNullOrBlank()) {
            b.invoiceFileName.text = file
            b.invoiceViewBtn.visibility = View.VISIBLE
            b.invoiceRemoveBtn.visibility = View.VISIBLE
        } else {
            b.invoiceFileName.text = "No file attached"
            b.invoiceViewBtn.visibility = View.GONE
            b.invoiceRemoveBtn.visibility = View.GONE
        }
    }

    private fun queryFileName(uri: Uri): String {
        var name = "invoice"
        try {
            requireContext().contentResolver.query(uri, null, null, null, null)?.use { c ->
                val idx = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                if (idx >= 0 && c.moveToFirst()) name = c.getString(idx) ?: name
            }
        } catch (e: Exception) { }
        return name
    }

    private suspend fun uploadPickedInvoice(id: String) {
        val uri = pickedInvoiceUri ?: return
        try {
            val bytes = withContext(Dispatchers.IO) {
                requireContext().contentResolver.openInputStream(uri)?.use { it.readBytes() }
            } ?: return
            val ext = pickedInvoiceName.substringAfterLast('.', "pdf")
            val mime = when (ext.lowercase()) {
                "pdf" -> "application/pdf"
                "png" -> "image/png"
                "gif" -> "image/gif"
                "webp" -> "image/webp"
                "bmp" -> "image/bmp"
                "tif", "tiff" -> "image/tiff"
                else -> "image/jpeg"
            }
            val body = bytes.toRequestBody(mime.toMediaTypeOrNull())
            val part = MultipartBody.Part.createFormData("file", pickedInvoiceName, body)
            ApiClient.api().uploadInvoice(id, part)
            pickedInvoiceUri = null
        } catch (e: Exception) {
            if (_b != null) Toast.makeText(requireContext(), "Invoice upload failed: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }

    /**
     * Downloads the attachment and hands it to whatever can open it.
     *
     * Three things made this a dead end. The HTTP status was never checked, so
     * a 401 or a 404 produced the same "Could not open invoice" as a genuine
     * failure -- with nothing to say which. ACTION_VIEW on its own needs a
     * *default* handler to be registered, and on a phone with no default PDF
     * viewer it throws rather than asking; a chooser asks. And when nothing on
     * the device can view the type at all, there is still usually something
     * that can receive it, so the last resort is Share rather than a shrug.
     */
    private fun viewInvoice() {
        // the server stores a bare filename; File(..).name keeps it that way
        // rather than trusting whatever arrives into a path
        val file = current.InvoiceFile?.let { File(it).name }
        if (file.isNullOrBlank()) return
        lifecycleScope.launch {
            try {
                val resp = ApiClient.api().downloadInvoice(file)
                if (!resp.isSuccessful) {
                    val why = when (resp.code()) {
                        401, 403 -> "not signed in any more -- sign in again"
                        404 -> "the file is no longer on the server"
                        else -> "server returned HTTP ${resp.code()}"
                    }
                    toastIfAlive("Could not open invoice: $why")
                    return@launch
                }
                val body = resp.body() ?: run {
                    toastIfAlive("Could not open invoice: the server sent nothing")
                    return@launch
                }
                val dir = File(requireContext().cacheDir, "downloads").apply { mkdirs() }
                val outFile = File(dir, file)
                withContext(Dispatchers.IO) {
                    body.byteStream().use { input ->
                        outFile.outputStream().use { output -> input.copyTo(output) }
                    }
                }
                if (outFile.length() == 0L) {
                    toastIfAlive("Could not open invoice: the file came back empty")
                    return@launch
                }
                if (_b == null) return@launch

                val ctx = requireContext()
                val uri = FileProvider.getUriForFile(
                    ctx, "${ctx.packageName}.fileprovider", outFile
                )
                val mime = ctx.contentResolver.getType(uri)
                    ?: android.webkit.MimeTypeMap.getSingleton()
                        .getMimeTypeFromExtension(file.substringAfterLast('.', "").lowercase())
                    ?: "*/*"

                val view = Intent(Intent.ACTION_VIEW).apply {
                    setDataAndType(uri, mime)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
                // A chooser does not need a default handler to be set, which is
                // the usual reason ACTION_VIEW silently fails on a fresh phone.
                val chooser = Intent.createChooser(view, "Open invoice").apply {
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
                try {
                    startActivity(chooser)
                } catch (e: android.content.ActivityNotFoundException) {
                    // nothing can view it; something can almost certainly take it
                    val send = Intent(Intent.ACTION_SEND).apply {
                        type = mime
                        putExtra(Intent.EXTRA_STREAM, uri)
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    }
                    try {
                        startActivity(Intent.createChooser(send, "Send invoice to…"))
                    } catch (e2: Exception) {
                        toastIfAlive("No app on this phone can open a $mime file")
                    }
                }
            } catch (e: Exception) {
                toastIfAlive("Could not open invoice: ${e.message}")
            }
        }
    }

    private fun toastIfAlive(msg: String) {
        if (_b != null && isAdded) {
            Toast.makeText(requireContext(), msg, Toast.LENGTH_LONG).show()
        }
    }

    private fun removeInvoice() {
        val id = assetId ?: return
        AlertDialog.Builder(requireContext())
            .setTitle("Remove invoice file?")
            .setPositiveButton("Remove") { _, _ ->
                lifecycleScope.launch {
                    try {
                        ApiClient.api().deleteInvoiceFile(id)
                        current = current.copy(InvoiceFile = null)
                        if (_b != null) renderInvoiceState()
                    } catch (e: Exception) {
                        if (_b != null) Toast.makeText(requireContext(), "Remove failed: ${e.message}", Toast.LENGTH_LONG).show()
                    }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
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
            AssetTag = b.fAssetTag.text?.toString()?.trim().orEmpty(),
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
                when (val r = Repository.saveAsset(requireContext(), asset, assetId)) {
                    is Repository.SaveResult.Synced -> {
                        // an invoice can only be attached to a real server id
                        val id = r.serverId ?: assetId
                        if (pickedInvoiceUri != null && id != null) uploadPickedInvoice(id)
                        requireActivity().onBackPressedDispatcher.onBackPressed()
                    }
                    is Repository.SaveResult.Queued -> {
                        android.widget.Toast.makeText(requireContext(),
                            "Saved offline — will sync when you're back online" +
                                (if (pickedInvoiceUri != null) " (invoice uploads once online)" else ""),
                            android.widget.Toast.LENGTH_LONG).show()
                        requireActivity().onBackPressedDispatcher.onBackPressed()
                    }
                    is Repository.SaveResult.Error -> {
                        if (_b != null) { b.formError.text = r.message; b.formError.visibility = View.VISIBLE }
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
                        val r = Repository.deleteAsset(requireContext(), id)
                        if (r is Repository.SaveResult.Queued) {
                            android.widget.Toast.makeText(requireContext(),
                                "Deleted offline — will sync when online",
                                android.widget.Toast.LENGTH_LONG).show()
                        }
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
        val parsed = LabelParser.parse(text)

        parsed.serial?.let { b.fSerial.setText(it) }
        parsed.mac?.let { b.fMacAddress.setText(it) }
        if (parsed.manufacturer != null || parsed.model != null) {
            current = current.copy(
                Manufacturer = parsed.manufacturer ?: current.Manufacturer,
                Model = parsed.model ?: current.Model
            )
            bindManufacturerSpinner()
        }

        val msg = if (parsed.isEmpty)
            "Couldn't recognize Serial, Model, or MAC on that label -- try getting closer or better lighting"
        else "✓ Filled from label: ${parsed.filledNames.joinToString(", ")}"
        android.widget.Toast.makeText(requireContext(), msg, android.widget.Toast.LENGTH_LONG).show()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _b = null
    }
}

private fun String?.ifNullOrBlank(fallback: String): String = if (this.isNullOrBlank()) fallback else this
