package com.itguy.assetmanager.ui.backup

import android.app.AlertDialog
import android.app.DownloadManager
import android.content.Context
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.Prefs
import com.itguy.assetmanager.data.model.BackupItem
import com.itguy.assetmanager.databinding.FragmentBackupRestoreBinding
import com.itguy.assetmanager.ui.Refreshable
import com.itguy.assetmanager.ui.generic.SimpleAdapter
import com.itguy.assetmanager.ui.generic.SimpleRow
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import java.io.File
import java.io.FileOutputStream

class BackupRestoreFragment : Fragment(), Refreshable {
    private var _b: FragmentBackupRestoreBinding? = null
    private val b get() = _b!!
    private val SCOPES = listOf("all", "config", "assets")

    private val restoreFileLauncher = registerForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri != null) uploadRestore(uri)
    }

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        _b = FragmentBackupRestoreBinding.inflate(inflater, container, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        b.recycler.layoutManager = LinearLayoutManager(requireContext())
        b.scopeSpinner.adapter = ArrayAdapter(requireContext(), android.R.layout.simple_spinner_dropdown_item, SCOPES.map { it.uppercase() })
        b.createBackupBtn.setOnClickListener { downloadNewBackup() }
        b.restoreBtn.setOnClickListener { restoreFileLauncher.launch("*/*") }
        refresh()
    }

    override fun refresh() {
        lifecycleScope.launch {
            try {
                val list = ApiClient.api().listBackups().body().orEmpty()
                if (_b == null) return@launch
                val adapter = SimpleAdapter(onClick = { row -> onBackupTapped(row.payload as BackupItem) })
                b.recycler.adapter = adapter
                adapter.submit(list.map { bkp ->
                    SimpleRow(bkp.file, "${bkp.scope} · ${bkp.created} · ${formatSize(bkp.size)}", bkp)
                })
                b.emptyText.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
            } catch (e: Exception) {
                Toast.makeText(requireContext(), "Could not load backups: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun formatSize(bytes: Long): String = when {
        bytes >= 1_000_000 -> "%.1f MB".format(bytes / 1_000_000.0)
        bytes >= 1_000 -> "%.1f KB".format(bytes / 1_000.0)
        else -> "$bytes B"
    }

    private fun downloadNewBackup() {
        val scope = SCOPES[b.scopeSpinner.selectedItemPosition]
        downloadUrl(Prefs.serverUrl + "api/backup?scope=" + scope, "backup_$scope.sql")
        Toast.makeText(requireContext(), "Creating backup, check your notifications…", Toast.LENGTH_SHORT).show()
    }

    private fun onBackupTapped(bkp: BackupItem) {
        val options = arrayOf("Download", "Delete")
        AlertDialog.Builder(requireContext())
            .setTitle(bkp.file)
            .setItems(options) { _, which ->
                when (which) {
                    0 -> downloadUrl(Prefs.serverUrl + "api/backups/" + bkp.file + "/download", bkp.file)
                    1 -> confirmDelete(bkp)
                }
            }
            .show()
    }

    private fun confirmDelete(bkp: BackupItem) {
        AlertDialog.Builder(requireContext())
            .setTitle("Delete backup?")
            .setMessage(bkp.file)
            .setPositiveButton("Delete") { _, _ ->
                lifecycleScope.launch {
                    try { ApiClient.api().deleteBackup(bkp.file); refresh() }
                    catch (e: Exception) { Toast.makeText(requireContext(), "Delete failed: ${e.message}", Toast.LENGTH_SHORT).show() }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun downloadUrl(url: String, filename: String) {
        try {
            val request = DownloadManager.Request(Uri.parse(url))
            request.addRequestHeader("X-Api-Key", Prefs.apiKey)
            request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, filename)
            val dm = requireContext().getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
            dm.enqueue(request)
        } catch (e: Exception) {
            Toast.makeText(requireContext(), "Download failed: ${e.message}", Toast.LENGTH_SHORT).show()
        }
    }

    private fun uploadRestore(uri: Uri) {
        AlertDialog.Builder(requireContext())
            .setTitle("Restore from this file?")
            .setMessage("This applies every statement in the backup file to the live database. Existing data with matching IDs will be overwritten.")
            .setPositiveButton("Restore") { _, _ ->
                lifecycleScope.launch {
                    try {
                        val tmp = File.createTempFile("restore_", ".sql", requireContext().cacheDir)
                        requireContext().contentResolver.openInputStream(uri)?.use { input ->
                            FileOutputStream(tmp).use { output -> input.copyTo(output) }
                        }
                        val body = tmp.asRequestBody("application/sql".toMediaTypeOrNull())
                        val part = MultipartBody.Part.createFormData("file", "restore.sql", body)
                        val resp = ApiClient.api().restore(part)
                        tmp.delete()
                        val r = resp.body()
                        if (resp.isSuccessful && r?.ok == true) {
                            Toast.makeText(requireContext(), "✓ Restored (${r.statements ?: 0} statements applied)", Toast.LENGTH_LONG).show()
                        } else {
                            Toast.makeText(requireContext(), "✕ ${r?.error ?: "Restore failed"}", Toast.LENGTH_LONG).show()
                        }
                    } catch (e: Exception) {
                        Toast.makeText(requireContext(), "✕ Restore failed: ${e.message}", Toast.LENGTH_LONG).show()
                    }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
