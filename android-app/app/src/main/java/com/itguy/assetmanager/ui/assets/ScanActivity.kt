package com.itguy.assetmanager.ui.assets

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import com.itguy.assetmanager.databinding.ActivityScanBinding
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/** Camera scanner for the Add/Edit Asset form -- real native ML Kit, not a
 * browser API. Two modes: (1) continuous live QR/barcode detection, and
 * (2) tap-to-capture text recognition (OCR) for reading a printed asset
 * label (S/N, Model, MAC…) that isn't a barcode at all. */
class ScanActivity : AppCompatActivity() {

    companion object {
        const val EXTRA_RESULT = "scan_result"
        const val EXTRA_TEXT_RESULT = "scan_text_result"
    }

    private lateinit var b: ActivityScanBinding
    private val handled = AtomicBoolean(false)
    private val ocrBusy = AtomicBoolean(false)
    private val cameraExecutor = Executors.newSingleThreadExecutor()
    private var imageCapture: ImageCapture? = null
    private val textRecognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)

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
        b.scanTextBtn.setOnClickListener { captureAndReadText() }

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

            val capture = ImageCapture.Builder()
                .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
                .build()
            imageCapture = capture

            try {
                provider.unbindAll()
                provider.bindToLifecycle(this, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis, capture)
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

    @androidx.camera.core.ExperimentalGetImage
    private fun captureAndReadText() {
        if (!ocrBusy.compareAndSet(false, true)) return
        val capture = imageCapture
        if (capture == null) { ocrBusy.set(false); return }
        b.scanTextBtn.isEnabled = false
        b.scanHint.text = "Reading label…"
        capture.takePicture(cameraExecutor, object : ImageCapture.OnImageCapturedCallback() {
            override fun onCaptureSuccess(image: ImageProxy) {
                val mediaImage = image.image
                if (mediaImage == null) { image.close(); ocrFailed("Could not read the camera frame"); return }
                val input = InputImage.fromMediaImage(mediaImage, image.imageInfo.rotationDegrees)
                textRecognizer.process(input)
                    .addOnSuccessListener { result ->
                        val text = result.text
                        if (text.isBlank()) {
                            ocrFailed("No text found on that label -- try getting closer or better lighting")
                        } else if (handled.compareAndSet(false, true)) {
                            val data = Intent().putExtra(EXTRA_TEXT_RESULT, text)
                            setResult(RESULT_OK, data)
                            finish()
                        }
                    }
                    .addOnFailureListener { e -> ocrFailed("Text recognition failed: ${e.message}") }
                    .addOnCompleteListener { image.close() }
            }
            override fun onError(exception: ImageCaptureException) {
                ocrFailed("Capture failed: ${exception.message}")
            }
        })
    }

    private fun ocrFailed(msg: String) {
        runOnUiThread {
            ocrBusy.set(false)
            b.scanTextBtn.isEnabled = true
            b.scanHint.text = "Point the camera at a QR code or barcode"
            Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        cameraExecutor.shutdown()
        textRecognizer.close()
    }
}
