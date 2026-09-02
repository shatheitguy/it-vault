package com.itguy.assetmanager.ui.assets

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
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

/** Live camera QR / barcode scanner for the Add/Edit Asset form -- a real
 * native scanner (CameraX + ML Kit), not a browser API, so it works
 * regardless of what WebView/browser engine is on the device. */
class ScanActivity : AppCompatActivity() {

    companion object { const val EXTRA_RESULT = "scan_result" }

    private lateinit var b: ActivityScanBinding
    private val handled = AtomicBoolean(false)
    private val cameraExecutor = Executors.newSingleThreadExecutor()

    private val permissionLauncher = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
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

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            startCamera()
        } else {
            permissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    private fun startCamera() {
        val providerFuture = ProcessCameraProvider.getInstance(this)
        providerFuture.addListener({
            val provider = providerFuture.get()
            val preview = Preview.Builder().build().also { it.setSurfaceProvider(b.previewView.surfaceProvider) }

            val scannerOptions = BarcodeScannerOptions.Builder()
                .setBarcodeFormats(
                    Barcode.FORMAT_QR_CODE, Barcode.FORMAT_CODE_128, Barcode.FORMAT_CODE_39,
                    Barcode.FORMAT_CODE_93, Barcode.FORMAT_CODABAR, Barcode.FORMAT_EAN_13,
                    Barcode.FORMAT_EAN_8, Barcode.FORMAT_ITF, Barcode.FORMAT_UPC_A,
                    Barcode.FORMAT_UPC_E, Barcode.FORMAT_DATA_MATRIX, Barcode.FORMAT_PDF417
                ).build()
            val scanner = BarcodeScanning.getClient(scannerOptions)

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
                val value = barcodes.firstOrNull()?.rawValue
                if (value != null && handled.compareAndSet(false, true)) {
                    val data = Intent().putExtra(EXTRA_RESULT, value)
                    setResult(RESULT_OK, data)
                    finish()
                }
            }
            .addOnCompleteListener { proxy.close() }
    }

    override fun onDestroy() {
        super.onDestroy()
        cameraExecutor.shutdown()
    }
}
