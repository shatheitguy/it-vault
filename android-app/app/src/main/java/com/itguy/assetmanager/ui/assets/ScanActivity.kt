package com.itguy.assetmanager.ui.assets

import android.Manifest
import android.animation.ValueAnimator
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.view.animation.LinearInterpolator
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import com.itguy.assetmanager.databinding.ActivityScanBinding
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Reads the QR printed on an IT-Vault asset tag. Nothing else.
 *
 * It used to read every barcode symbology ML Kit knows, plus the text on a
 * label through OCR, because it fed the asset form -- a serial off a
 * manufacturer's sticker was a useful thing to catch. That form no longer
 * has a scan button: this is reached from the bottom bar, and the one
 * question it answers is "which asset is this?". So it takes QR codes, and
 * of those only the ones carrying an address this app understands. A
 * shipping barcode on the same shelf is not an answer to that question, and
 * silently treating one as a search term sends you to an empty list with no
 * hint as to why.
 */
class ScanActivity : AppCompatActivity() {

    companion object {
        const val EXTRA_RESULT = "scan_result"

        /**
         * What an IT-Vault tag's QR carries: /p/<code> on tags printed now,
         * /a/<tag> or /asset/<id> on older ones. The host is not checked --
         * the same server is reached by LAN address, hostname and domain
         * depending on where you are standing, and refusing a tag because it
         * names one of its own other addresses would be nonsense.
         */
        private val TAG_URL = Regex("/(?:p|a|asset)/([^/?#\\s]+)")
    }

    private lateinit var b: ActivityScanBinding
    private val handled = AtomicBoolean(false)
    private val cameraExecutor = Executors.newSingleThreadExecutor()
    private var sweep: ValueAnimator? = null
    private var lastRejectAt = 0L

    private val permissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) startCamera() else {
                Toast.makeText(this, "Camera permission is required to scan", Toast.LENGTH_LONG).show()
                finish()
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityScanBinding.inflate(layoutInflater)
        setContentView(b.root)
        b.closeBtn.setOnClickListener { finish() }
        startSweep()

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            == PackageManager.PERMISSION_GRANTED
        ) {
            startCamera()
        } else {
            permissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    /** The line crossing the frame. It is the only thing on screen that says
     * the camera is alive: a still viewfinder in a dim store room looks
     * identical to a frozen one. */
    private fun startSweep() {
        b.scanFrame.post {
            val travel = (b.scanFrame.height - b.scanLine.height).toFloat()
            if (travel <= 0f) return@post
            sweep = ValueAnimator.ofFloat(0f, travel).apply {
                duration = 1700
                repeatCount = ValueAnimator.INFINITE
                repeatMode = ValueAnimator.REVERSE
                interpolator = LinearInterpolator()
                addUpdateListener { b.scanLine.translationY = it.animatedValue as Float }
                start()
            }
        }
    }

    private fun startCamera() {
        val providerFuture = ProcessCameraProvider.getInstance(this)
        providerFuture.addListener({
            val provider = providerFuture.get()
            val preview = Preview.Builder().build()
                .also { it.setSurfaceProvider(b.previewView.surfaceProvider) }

            // QR only: every other symbology is a thing this screen has no
            // answer for, and asking ML Kit for fewer formats is also faster
            val scanner = BarcodeScanning.getClient(
                BarcodeScannerOptions.Builder()
                    .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
                    .build()
            )

            val analysis = ImageAnalysis.Builder()
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
            analysis.setAnalyzer(cameraExecutor) { proxy -> analyze(proxy, scanner) }

            try {
                provider.unbindAll()
                provider.bindToLifecycle(this, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis)
            } catch (e: Exception) {
                Toast.makeText(this, "Could not start camera: ${e.message}", Toast.LENGTH_LONG).show()
                finish()
            }
        }, ContextCompat.getMainExecutor(this))
    }

    @androidx.camera.core.ExperimentalGetImage
    private fun analyze(proxy: ImageProxy, scanner: com.google.mlkit.vision.barcode.BarcodeScanner) {
        val mediaImage = proxy.image
        if (mediaImage == null) { proxy.close(); return }
        val image = InputImage.fromMediaImage(mediaImage, proxy.imageInfo.rotationDegrees)
        scanner.process(image)
            .addOnSuccessListener { barcodes ->
                val value = barcodes.firstNotNullOfOrNull { it.rawValue }
                if (value == null) return@addOnSuccessListener
                val code = TAG_URL.find(value)?.groupValues?.get(1)
                if (code.isNullOrBlank()) {
                    rejected()
                } else if (handled.compareAndSet(false, true)) {
                    setResult(RESULT_OK, Intent().putExtra(EXTRA_RESULT, code))
                    finish()
                }
            }
            .addOnCompleteListener { proxy.close() }
    }

    /** A QR that is not one of ours. Say so on the hint line and keep
     * scanning -- closing the camera to show an error, on a code the user
     * may not even have meant to point at, is worse than a line of text. */
    private fun rejected() {
        val now = System.currentTimeMillis()
        if (now - lastRejectAt < 1500) return      // the same code, every frame
        lastRejectAt = now
        runOnUiThread {
            if (isFinishing) return@runOnUiThread
            b.scanHint.text = "That QR is not an IT-Vault asset tag"
            b.scanHint.postDelayed({
                if (!isFinishing && !handled.get()) {
                    b.scanHint.text = "Hold the QR on the asset tag inside the frame"
                }
            }, 2200)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        sweep?.cancel()
        cameraExecutor.shutdown()
    }
}
