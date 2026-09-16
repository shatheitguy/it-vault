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

        fun intent(ctx: Context, assetId: String, assetTag: String, printNow: Boolean): Intent =
            Intent(ctx, RecordViewActivity::class.java)
                .putExtra(EXTRA_ID, assetId)
                .putExtra(EXTRA_TAG, assetTag)
                .putExtra(EXTRA_PRINT_NOW, printNow)
    }

    private lateinit var web: WebView
    private var printed = false
    private var jobName = "asset"

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
            if (asset == null) {
                Toast.makeText(
                    this@RecordViewActivity,
                    "That asset is not on this phone yet, and the server could not be reached",
                    Toast.LENGTH_LONG,
                ).show()
                finish(); return@launch
            }
            val employee = fetchEmployee(asset.EmployeeID)
            // a base URL on the server so the logo in the header resolves;
            // the sheet itself is entirely local, so it renders with or
            // without one
            val base = Prefs.serverUrl.trimEnd('/')
            web.loadDataWithBaseURL(
                if (base.isBlank()) null else "$base/",
                buildHtml(asset, employee),
                "text/html",
                "utf-8",
                null,
            )
        }
    }

    /** The server's copy if it answers, otherwise the one already cached. */
    private suspend fun fetchAsset(id: String): Asset? {
        try {
            ApiClient.api().getAsset(id).body()?.let { if (it.id != null) return it }
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

    private fun buildHtml(a: Asset, emp: Employee?): String {
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
        // months, spelled out: the number on its own has had people reading it
        // as years
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
        return """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
@page{size:A4;margin:14mm}
body{font-family:'Segoe UI',Roboto,Arial,sans-serif;color:#111;background:#fff;margin:0;padding:10px}
.card{border:1px solid #222;border-radius:8px;max-width:720px;margin:0 auto;overflow:hidden}
.hd{background:#101622;color:#fff;padding:12px 16px;font-weight:600;display:flex;align-items:center;gap:10px}
.hd img{height:24px}
.idbar{background:#f4f6fa;border-bottom:2px solid #101622;padding:12px 16px;text-align:center}
.idbar .tag{font-size:24px;font-weight:800;letter-spacing:1px;color:#101622;font-family:ui-monospace,Consolas,monospace}
.idbar .nm{font-size:13px;color:#555;margin-top:2px}
.bd{padding:12px 16px}
table{width:100%;border-collapse:collapse}
td.k{width:38%;padding:5px 8px;color:#555;font-weight:600;border-bottom:1px solid #eee;vertical-align:top}
td.v{padding:5px 8px;border-bottom:1px solid #eee;word-break:break-word}
.sig{margin-top:14px;padding:10px;border:1px dashed #999;border-radius:6px;font-size:12px}
.sig .t{font-weight:700;letter-spacing:.5px;margin-bottom:26px}
.sig .l{border-top:1px solid #777;width:60%;padding-top:4px;color:#666}
@media print{body{-webkit-print-color-adjust:exact;print-color-adjust:exact;padding:0}}
</style></head><body>
<div class="card">
  <div class="hd"><img src="/logo.png" onerror="this.style.display='none'"><span>${esc(brand)} — Asset record</span></div>
  <div class="idbar"><div class="tag">${esc(a.AssetTag.ifBlank { "—" })}</div><div class="nm">${esc(a.Name)}</div></div>
  <div class="bd"><table>$rows</table>
    <div class="sig"><div class="t">SIGNATURE / ACKNOWLEDGEMENT</div><div class="l">Name and signature · date</div></div>
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
