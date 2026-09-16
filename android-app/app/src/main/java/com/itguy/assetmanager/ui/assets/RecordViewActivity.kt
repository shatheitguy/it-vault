package com.itguy.assetmanager.ui.assets

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.print.PrintAttributes
import android.print.PrintManager
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.OfflineCache
import com.itguy.assetmanager.data.Prefs
import com.itguy.assetmanager.data.model.Asset
import com.itguy.assetmanager.data.model.Employee
import kotlinx.coroutines.launch
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * The asset record -- the A4 sheet with every field on it -- shown and printed
 * from the phone.
 *
 * The QR label has a server route, so [LabelViewActivity] just loads it. The
 * record sheet does not: on the web it is built in the browser from the asset
 * the page already holds. So this builds the same sheet here, from the asset
 * this app already holds, which has the useful side effect of printing from
 * the cache when there is no network -- and a store room is usually where
 * there is no network.
 */
class RecordViewActivity : AppCompatActivity() {

    companion object {
        private const val EXTRA_ID = "asset_id"
        private const val EXTRA_TAG = "asset_tag"
        private const val EXTRA_PRINT_NOW = "print_now"

        /** Millimetres of page left clear for the letterhead, matching
         * LETTERHEAD_CLEARANCE_MM in the web app -- the same paper, so the
         * same gap. */
        private const val LETTERHEAD_CLEARANCE_MM = 38

        fun intent(ctx: Context, assetId: String, assetTag: String, printNow: Boolean): Intent =
            Intent(ctx, RecordViewActivity::class.java)
                .putExtra(EXTRA_ID, assetId)
                .putExtra(EXTRA_TAG, assetTag)
                .putExtra(EXTRA_PRINT_NOW, printNow)
    }

    private lateinit var web: WebView
    private var printed = false
    private var jobName = "asset"

    /** Set when the server actually answered for this asset. */
    private var serverAnswered = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        Prefs.init(applicationContext)
        super.onCreate(savedInstanceState)

        val assetId = intent.getStringExtra(EXTRA_ID).orEmpty()
        val assetTag = intent.getStringExtra(EXTRA_TAG).orEmpty().ifBlank { "asset" }
        val printNow = intent.getBooleanExtra(EXTRA_PRINT_NOW, false)
        jobName = assetTag

        title = "Asset record · $assetTag"
        supportActionBar?.setDisplayHomeAsUpEnabled(true)

        web = WebView(this)
        setContentView(web)
        web.settings.builtInZoomControls = true
        web.settings.displayZoomControls = false
        web.settings.loadWithOverviewMode = true
        web.settings.useWideViewPort = true
        web.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView, url: String) {
                if (printNow && !printed) {
                    printed = true
                    view.postDelayed({ doPrint() }, 250)
                }
            }
        }

        if (assetId.isBlank()) {
            Toast.makeText(this, "Missing asset", Toast.LENGTH_LONG).show()
            finish(); return
        }

        lifecycleScope.launch {
            val asset = fetchAsset(assetId)
            // whether the record came from the server matters for the
            // signature block: the cached copy does not carry one, and
            // "not signed yet" would be a claim we cannot make from it
            val fromServer = serverAnswered
            if (asset == null) {
                Toast.makeText(
                    this@RecordViewActivity,
                    "That asset is not on this phone yet, and the server could not be reached",
                    Toast.LENGTH_LONG,
                ).show()
                finish(); return@launch
            }
            val employee = fetchEmployee(asset.EmployeeID)
            val letterhead = letterheadDataUri()
            // a base URL on the server so the letterhead and the logo
            // resolve; the sheet itself is local, so it still renders (and
            // prints) with neither
            val base = if (Prefs.serverUrl.isBlank()) null
                       else ApiClient.normalize(Prefs.serverUrl)
            web.loadDataWithBaseURL(
                base,
                buildHtml(asset, employee, letterhead, fromServer),
                "text/html",
                "utf-8",
                null,
            )
        }
    }

    /** The server's copy if it answers, otherwise the one already cached. */
    private suspend fun fetchAsset(id: String): Asset? {
        try {
            ApiClient.api().getAsset(id).body()?.let {
                if (it.id != null) { serverAnswered = true; return it }
            }
        } catch (_: Exception) {
            // offline: the cache below is the whole point
        }
        return OfflineCache.loadAssets()?.firstOrNull { it.id == id }
    }

    /** Who it is assigned to. EmployeeID is the only name the asset carries,
     * so the rest of the person comes from the directory, same as the web
     * sheet and the signed PDF do. */
    private suspend fun fetchEmployee(employeeId: String): Employee? {
        if (employeeId.isBlank()) return null
        val cached = OfflineCache.loadEmployees()?.firstOrNull { it.EmployeeID == employeeId }
        if (cached != null) return cached
        return try {
            ApiClient.api().listEmployees().body()?.firstOrNull { it.EmployeeID == employeeId }
        } catch (_: Exception) {
            null
        }
    }

    /** Whether this install prints on a letterhead. When it does, the sheet
     * leaves the top of the page clear and draws no header of its own --
     * exactly what the web does, so both come out of the printer alike.
     * Unreachable server means no letterhead to fetch either, so the header
     * bar is the right answer offline. */
    /**
     * The letterhead, as a data: URI, or null when this install has none.
     *
     * Two earlier attempts at this did not survive contact with a printer.
     * Asking /api/branding whether a letterhead exists only works against a
     * server new enough to answer, and an install that has not been updated
     * yet says "no" and prints the wrong document. Linking the image and
     * letting the WebView fetch it looks right on screen and then does not
     * come out of Android's print pipeline, which renders the page it was
     * given rather than re-fetching anything.
     *
     * Fetching the bytes here and inlining them settles both: the image is
     * part of the document by the time it is printed, and whether there is
     * one at all is answered by what came back rather than by a flag. The
     * route is public, so no credentials are involved, and it answers with a
     * 1x1 transparent pixel when nothing has been uploaded -- which is what
     * the size check below is looking for.
     */
    private suspend fun letterheadDataUri(): String? = withContext(Dispatchers.IO) {
        if (Prefs.serverUrl.isBlank()) return@withContext null
        // normalize() is what puts a scheme on an address typed as a bare
        // host or IP, which is how most of these installs are reached, and
        // java.net.URL will not take one without
        val base = ApiClient.normalize(Prefs.serverUrl)
        try {
            val conn = (java.net.URL(base + "letterhead.png").openConnection()
                as java.net.HttpURLConnection).apply {
                connectTimeout = 4000
                readTimeout = 8000
                requestMethod = "GET"
            }
            val bytes = conn.inputStream.use { it.readBytes() }
            conn.disconnect()
            // An install with no letterhead does not 404 here -- the route
            // answers with a 1x1 transparent PNG, so "something came back"
            // is not the same as "there is a letterhead". Measure it: the
            // bounds decode reads the header only, not the pixels.
            val bounds = android.graphics.BitmapFactory.Options().apply {
                inJustDecodeBounds = true
            }
            android.graphics.BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
            if (bounds.outWidth < 200 || bounds.outHeight < 200) return@withContext null
            "data:image/png;base64," +
                android.util.Base64.encodeToString(bytes, android.util.Base64.NO_WRAP)
        } catch (_: Exception) {
            // offline, or an older server: print the header bar instead
            null
        }
    }

    /**
     * The sheet, built to match what the web prints.
     *
     * The fields, their order, the ID bar, the signature block and the
     * letterhead handling are all the browser's, deliberately: an asset
     * record printed from a phone and one printed from a desk should be the
     * same document, not two that merely cover the same ground.
     */
    private fun buildHtml(a: Asset, emp: Employee?, letterhead: String?, fromServer: Boolean): String {
        val rows = StringBuilder()
        fun row(label: String, value: String?) {
            val v = value?.trim().orEmpty().ifBlank { "—" }
            rows.append("<tr><td class=\"k\">").append(esc(label))
                .append("</td><td class=\"v\">").append(esc(v)).append("</td></tr>")
        }

        row("Name", a.Name)
        row("Asset tag", a.AssetTag)
        row("Type", a.Type)
        row("Serial", a.Serial)
        row("Manufacturer", a.Manufacturer)
        row("Model", a.Model)
        row("MAC address", a.MacAddress)
        row("Location", a.Location)
        row("Status", a.Status)
        row("Purchase date", a.PurchaseDate)
        // months, spelled out: the number on its own has had people reading
        // it as years
        row("Warranty", if (a.WarrantyMonths > 0) "${a.WarrantyMonths} months" else "")
        row("Price", a.Price)
        row("Received by", a.ReceivedBy)
        row("Notes on receipt", a.NotesReceived)
        row("Notes", a.Note)
        if (a.EmployeeID.isNotBlank()) {
            row("Employee ID", a.EmployeeID)
            row("Employee name", emp?.EmployeeName ?: a.EmployeeID)
            row("Department", emp?.Department)
            row("Designation", emp?.Designation)
            row("Email", emp?.Email)
        }

        val brand = Prefs.brandName.ifBlank { "IT-Vault" }
        val sig = when {
            a.SignatureData.startsWith("data:image") ->
                "<img src=\"${a.SignatureData}\" class=\"sig-img\" alt=\"Signature\">"
            // the server said there is none
            fromServer -> "<div class=\"muted\">Not signed yet</div>"
            // printed from the cache, which never carries the signature: a
            // line to sign is honest, "not signed yet" would not be
            else -> "<div class=\"sig-line\">Name and signature · date</div>"
        }
        val header =
            if (letterhead != null) ""
            else "<div class=\"hd\"><img src=\"/logo.png\" onerror=\"this.style.display='none'\">" +
                "<span>${esc(brand)} — Asset record</span></div>"
        val backdrop =
            if (letterhead != null) "<img src=\"$letterhead\" class=\"lh\" alt=\"\">" else ""

        return """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
@page{size:A4;margin:${if (letterhead != null) "0" else "14mm"}}
body{font-family:'Segoe UI',Roboto,Arial,sans-serif;color:#111;background:#fff;margin:0;padding:10px}
.lh{position:absolute;top:0;left:0;width:210mm;height:297mm;object-fit:fill;z-index:-1}
.card{border:1px solid #222;border-radius:8px;max-width:720px;margin:${if (letterhead != null) "$LETTERHEAD_CLEARANCE_MM" + "mm auto 0" else "0 auto"};overflow:hidden;position:relative}
.hd{background:#101622;color:#fff;padding:12px 16px;font-weight:600;display:flex;align-items:center;gap:10px}
.hd img{height:26px}
.idbar{background:#f4f6fa;border-bottom:2px solid #101622;padding:12px 16px;text-align:center}
.idbar .tag{font-size:26px;font-weight:800;letter-spacing:1px;color:#101622;font-family:ui-monospace,Consolas,monospace}
.idbar .nm{font-size:13px;color:#555;margin-top:2px}
.bd{padding:14px 16px}
table{width:100%;border-collapse:collapse}
td.k{width:38%;padding:5px 8px;color:#555;font-weight:600;border-bottom:1px solid #eee;vertical-align:top}
td.v{padding:5px 8px;border-bottom:1px solid #eee;word-break:break-word}
.sig-block{margin-top:14px;padding:10px;border:1px dashed #999;border-radius:6px}
.sig-title{font-weight:700;margin-bottom:6px;font-size:12px;letter-spacing:.5px}
.sig-img{max-width:340px;max-height:160px;border:1px solid #ccc;border-radius:6px;background:#fff}
.sig-line{border-top:1px solid #777;width:60%;margin-top:26px;padding-top:4px;color:#666;font-size:12px}
.muted{color:#999;font-style:italic}
@media print{body{-webkit-print-color-adjust:exact;print-color-adjust:exact;padding:0}}
</style></head><body>
$backdrop
<div class="card">
  $header
  <div class="idbar"><div class="tag">${esc(a.AssetTag.ifBlank { "—" })}</div><div class="nm">${esc(a.Name)}</div></div>
  <div class="bd"><table>$rows</table>
    <div class="sig-block"><div class="sig-title">SIGNATURE / ACKNOWLEDGEMENT</div>$sig</div>
  </div>
</div></body></html>"""
    }

    private fun esc(s: String): String = s
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace("\"", "&quot;")

    private fun doPrint() {
        try {
            val pm = getSystemService(Context.PRINT_SERVICE) as PrintManager
            val job = "IT-Vault asset $jobName"
            pm.print(job, web.createPrintDocumentAdapter(job), PrintAttributes.Builder().build())
        } catch (e: Exception) {
            Toast.makeText(this, "Could not open the print dialog: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }

    override fun onSupportNavigateUp(): Boolean { finish(); return true }

    override fun onCreateOptionsMenu(menu: android.view.Menu): Boolean {
        menu.add("Print").setShowAsAction(android.view.MenuItem.SHOW_AS_ACTION_NEVER)
        return true
    }

    override fun onOptionsItemSelected(item: android.view.MenuItem): Boolean {
        if (item.title == "Print") { doPrint(); return true }
        return super.onOptionsItemSelected(item)
    }

    override fun onDestroy() {
        super.onDestroy()
        web.destroy()
    }
}
