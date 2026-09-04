package com.itguy.assetmanager.ui.assets

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.print.PrintAttributes
import android.print.PrintManager
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.itguy.assetmanager.data.Prefs

/**
 * Shows an asset's QR label and prints it through Android's own print
 * service (which includes "Save as PDF").
 *
 * The server already renders this label at /label/<id> -- QR, asset fields,
 * org branding, print CSS -- and that route needs no auth, so this reuses it
 * rather than re-implementing QR rendering and layout natively. The only
 * native part is handing the loaded page to PrintManager.
 */
class LabelViewActivity : AppCompatActivity() {

    companion object {
        private const val EXTRA_ID = "asset_id"
        private const val EXTRA_TAG = "asset_tag"
        private const val EXTRA_PRINT_NOW = "print_now"

        fun intent(ctx: Context, assetId: String, assetTag: String, printNow: Boolean): Intent =
            Intent(ctx, LabelViewActivity::class.java)
                .putExtra(EXTRA_ID, assetId)
                .putExtra(EXTRA_TAG, assetTag)
                .putExtra(EXTRA_PRINT_NOW, printNow)
    }

    private lateinit var web: WebView
    private var printed = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        Prefs.init(applicationContext)
        super.onCreate(savedInstanceState)

        val assetId = intent.getStringExtra(EXTRA_ID).orEmpty()
        val assetTag = intent.getStringExtra(EXTRA_TAG).orEmpty().ifBlank { "asset" }
        val printNow = intent.getBooleanExtra(EXTRA_PRINT_NOW, false)

        title = if (printNow) "Print label · $assetTag" else "QR label · $assetTag"
        supportActionBar?.setDisplayHomeAsUpEnabled(true)

        web = WebView(this)
        setContentView(web)
        // the label page draws its QR with a bundled script, so JS is required
        web.settings.javaScriptEnabled = true
        web.settings.builtInZoomControls = true
        web.settings.displayZoomControls = false
        web.settings.loadWithOverviewMode = true
        web.settings.useWideViewPort = true

        web.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView, url: String) {
                if (printNow && !printed) {
                    printed = true
                    // small settle delay: the page draws its QR from script
                    // after load, so printing instantly can catch it empty
                    view.postDelayed({ doPrint(assetTag) }, 350)
                }
            }
            override fun shouldOverrideUrlLoading(view: WebView, req: WebResourceRequest): Boolean = false
        }

        val base = Prefs.serverUrl.trimEnd('/')
        if (base.isBlank() || assetId.isBlank()) {
            Toast.makeText(this, "Missing server address or asset", Toast.LENGTH_LONG).show()
            finish(); return
        }
        web.loadUrl("$base/label/$assetId")
    }

    private fun doPrint(assetTag: String) {
        try {
            val pm = getSystemService(Context.PRINT_SERVICE) as PrintManager
            val job = "IT-Vault label $assetTag"
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
        if (item.title == "Print") {
            doPrint(intent.getStringExtra(EXTRA_TAG).orEmpty().ifBlank { "asset" }); return true
        }
        return super.onOptionsItemSelected(item)
    }

    override fun onDestroy() {
        super.onDestroy()
        web.destroy()
    }
}
