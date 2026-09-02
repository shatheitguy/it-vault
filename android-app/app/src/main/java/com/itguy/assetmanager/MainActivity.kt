package com.itguy.assetmanager

import android.Manifest
import android.annotation.SuppressLint
import android.app.DownloadManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.provider.MediaStore
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.webkit.CookieManager
import android.webkit.PermissionRequest
import android.webkit.URLUtil
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import com.google.android.material.button.MaterialButton
import com.google.android.material.textfield.TextInputEditText
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * Single-Activity client, same shape as the Nextcloud Android app: on first
 * launch you type in your server's address, we remember it, and from then on
 * this just shows that server's own web UI inside a WebView with native
 * camera / file-upload / download plumbing wired up so the QR scanner, invoice
 * uploads, and exports all work like a real app instead of a browser tab.
 */
class MainActivity : AppCompatActivity() {

    private val prefs by lazy { getSharedPreferences("itguy_assets", Context.MODE_PRIVATE) }
    private var serverBaseUrl: String
        get() = prefs.getString("server_url", "") ?: ""
        set(value) = prefs.edit().putString("server_url", value).apply()

    private lateinit var setupGroup: View
    private lateinit var serverInput: TextInputEditText
    private lateinit var setupError: TextView
    private lateinit var connectBtn: MaterialButton
    private lateinit var setupProgress: ProgressBar
    private lateinit var swipeRefresh: SwipeRefreshLayout
    private lateinit var webView: WebView
    private lateinit var pageProgress: ProgressBar

    private var pendingPermissionRequest: PermissionRequest? = null
    private var pendingFileCallback: ValueCallback<Array<Uri>>? = null
    private var pendingCameraCaptureUri: Uri? = null

    private val cameraPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            val req = pendingPermissionRequest
            pendingPermissionRequest = null
            if (req == null) return@registerForActivityResult
            if (granted) req.grant(req.resources) else req.deny()
        }

    private val fileChooserLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            val callback = pendingFileCallback
            pendingFileCallback = null
            if (callback == null) return@registerForActivityResult
            val results: Array<Uri>? = when {
                result.resultCode != RESULT_OK -> null
                result.data?.dataUris != null -> result.data?.dataUris
                result.data?.data != null -> arrayOf(result.data!!.data!!)
                pendingCameraCaptureUri != null -> arrayOf(pendingCameraCaptureUri!!)
                else -> null
            }
            callback.onReceiveValue(results)
        }

    private val Intent?.dataUris: Array<Uri>?
        get() {
            val clip = this?.clipData ?: return null
            return Array(clip.itemCount) { i -> clip.getItemAt(i).uri }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        setupGroup = findViewById(R.id.setupGroup)
        serverInput = findViewById(R.id.serverInput)
        setupError = findViewById(R.id.setupError)
        connectBtn = findViewById(R.id.connectBtn)
        setupProgress = findViewById(R.id.setupProgress)
        swipeRefresh = findViewById(R.id.swipeRefresh)
        webView = findViewById(R.id.webView)
        pageProgress = findViewById(R.id.pageProgress)

        connectBtn.setOnClickListener { tryConnect(serverInput.text?.toString().orEmpty()) }
        swipeRefresh.setOnRefreshListener { webView.reload() }

        setupWebView()

        onBackPressedDispatcher.addCallback(this, object : androidx.activity.OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) {
                    webView.goBack()
                } else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })

        val saved = serverBaseUrl
        if (saved.isNotBlank()) {
            showWebView(saved)
        } else {
            showSetup()
        }
    }

    private fun showSetup() {
        setupGroup.visibility = View.VISIBLE
        swipeRefresh.visibility = View.GONE
    }

    private fun showWebView(baseUrl: String) {
        setupGroup.visibility = View.GONE
        swipeRefresh.visibility = View.VISIBLE
        webView.loadUrl(baseUrl)
    }

    private fun normalizeServerInput(raw: String): String? {
        var v = raw.trim()
        if (v.isEmpty()) return null
        if (!v.startsWith("http://") && !v.startsWith("https://")) v = "http://$v"
        return if (v.endsWith("/")) v else "$v/"
    }

    private fun tryConnect(raw: String) {
        val url = normalizeServerInput(raw)
        if (url == null) {
            setupError.text = getString(R.string.error_empty_address)
            setupError.visibility = View.VISIBLE
            return
        }
        setupError.visibility = View.GONE
        setupProgress.visibility = View.VISIBLE
        connectBtn.isEnabled = false
        Thread {
            val reachable = try {
                val conn = URL(url).openConnection() as HttpURLConnection
                conn.connectTimeout = 6000
                conn.readTimeout = 6000
                conn.requestMethod = "GET"
                conn.connect()
                val code = conn.responseCode
                conn.disconnect()
                code in 200..499 // any real HTTP response means "this is a server"
            } catch (e: Exception) {
                false
            }
            runOnUiThread {
                setupProgress.visibility = View.GONE
                connectBtn.isEnabled = true
                if (reachable) {
                    serverBaseUrl = url
                    showWebView(url)
                } else {
                    setupError.text = getString(R.string.error_unreachable)
                    setupError.visibility = View.VISIBLE
                }
            }
        }.start()
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        val s = webView.settings
        s.javaScriptEnabled = true
        s.domStorageEnabled = true
        s.databaseEnabled = true
        s.mediaPlaybackRequiresUserGesture = false
        s.mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
        s.setSupportMultipleWindows(false)
        s.userAgentString = s.userAgentString + " ITGuyAssetsApp/1.0"
        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true)

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: android.webkit.WebResourceRequest): Boolean {
                val url = request.url
                val server = Uri.parse(serverBaseUrl)
                return if (url.host != null && url.host == server.host) {
                    false // same server -> let the WebView load it normally
                } else {
                    try { startActivity(Intent(Intent.ACTION_VIEW, url)) } catch (e: Exception) {}
                    true
                }
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView, newProgress: Int) {
                swipeRefresh.isRefreshing = false
                if (newProgress >= 100) {
                    pageProgress.visibility = View.GONE
                } else {
                    pageProgress.visibility = View.VISIBLE
                    pageProgress.progress = newProgress
                }
            }

            // the in-app QR/barcode camera scanner needs getUserMedia() to work
            override fun onPermissionRequest(request: PermissionRequest) {
                val needsCamera = request.resources.any { it == PermissionRequest.RESOURCE_VIDEO_CAPTURE }
                if (!needsCamera) { request.grant(request.resources); return }
                if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                    request.grant(request.resources)
                } else {
                    pendingPermissionRequest = request
                    cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
                }
            }

            // invoice / logo / catalog-import / "upload photo instead" file inputs
            override fun onShowFileChooser(
                webView: WebView,
                filePathCallback: ValueCallback<Array<Uri>>,
                params: FileChooserParams
            ): Boolean {
                pendingFileCallback = filePathCallback
                pendingCameraCaptureUri = null

                val intents = mutableListOf<Intent>()
                try {
                    val photoFile = File.createTempFile("scan_", ".jpg", cacheDir)
                    val photoUri = FileProvider.getUriForFile(this@MainActivity, "$packageName.fileprovider", photoFile)
                    pendingCameraCaptureUri = photoUri
                    val captureIntent = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
                    captureIntent.putExtra(MediaStore.EXTRA_OUTPUT, photoUri)
                    intents.add(captureIntent)
                } catch (e: Exception) { /* camera capture unavailable, still offer file picker below */ }

                val contentIntent = Intent(Intent.ACTION_GET_CONTENT)
                contentIntent.addCategory(Intent.CATEGORY_OPENABLE)
                contentIntent.type = params.acceptTypes?.firstOrNull { it.isNotBlank() && it != "*/*" } ?: "*/*"
                contentIntent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, params.mode == FileChooserParams.MODE_OPEN_MULTIPLE)

                val chooser = Intent.createChooser(contentIntent, "Choose a file")
                if (intents.isNotEmpty()) chooser.putExtra(Intent.EXTRA_INITIAL_INTENTS, intents.toTypedArray())
                fileChooserLauncher.launch(chooser)
                return true
            }
        }

        webView.setDownloadListener { url, _, contentDisposition, mimeType, _ ->
            try {
                val request = DownloadManager.Request(Uri.parse(url))
                val cookie = CookieManager.getInstance().getCookie(url)
                if (cookie != null) request.addRequestHeader("cookie", cookie)
                val filename = URLUtil.guessFileName(url, contentDisposition, mimeType)
                request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, filename)
                val dm = getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
                dm.enqueue(request)
                Toast.makeText(this, "Downloading $filename…", Toast.LENGTH_SHORT).show()
            } catch (e: Exception) {
                Toast.makeText(this, "Download failed: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        }
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.main_menu, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        return when (item.itemId) {
            R.id.action_reload -> { webView.reload(); true }
            R.id.action_change_server -> {
                serverBaseUrl = ""
                CookieManager.getInstance().removeAllCookies(null)
                webView.loadUrl("about:blank")
                serverInput.setText("")
                showSetup()
                true
            }
            else -> super.onOptionsItemSelected(item)
        }
    }
}
