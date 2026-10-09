package com.itguy.assetmanager.ui.settings

import androidx.appcompat.app.AlertDialog
import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.Prefs
import com.itguy.assetmanager.ui.AppIcon
import com.itguy.assetmanager.databinding.FragmentSettingsBinding
import com.itguy.assetmanager.ui.login.LoginActivity
import kotlinx.coroutines.launch

class SettingsFragment : Fragment() {
    private var _b: FragmentSettingsBinding? = null
    private val b get() = _b!!

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        _b = FragmentSettingsBinding.inflate(inflater, container, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        b.serverText.text = Prefs.serverUrl
        loadProfile()
        setupThemePicker()

        b.saveProfileBtn.setOnClickListener { saveProfile() }
        b.changePassBtn.setOnClickListener { changePassword() }
        b.changeServerBtn.setOnClickListener { confirmChangeServer() }

        refreshSyncStatus()
        b.syncNowBtn.setOnClickListener { syncNow() }
        b.exportXmlBtn.setOnClickListener {
            exportLauncher.launch(com.itguy.assetmanager.data.XmlExport.suggestedFileName())
        }

        setupUpdates()
    }

    private fun setupUpdates() {
        b.versionText.text =
            "IT-Vault v${com.itguy.assetmanager.ui.update.AppUpdater.currentVersionName(requireContext())}"
        b.checkUpdateBtn.setOnClickListener {
            b.checkUpdateBtn.isEnabled = false
            showUpdate("Checking for updates…")
            com.itguy.assetmanager.ui.update.AppUpdater.checkManual(requireActivity()) { msg ->
                if (_b == null) return@checkManual
                showUpdate(msg)
                b.checkUpdateBtn.isEnabled = true
            }
        }
    }

    /** The update's own status line, which lives with the update button. */
    private fun showUpdate(text: String) {
        if (_b == null) return
        b.updateStatus.text = text
        b.updateStatus.visibility = View.VISIBLE
    }

    /** SAF: the user picks where the .xml lands (Downloads, Drive, etc.). */
    private val exportLauncher = registerForActivityResult(
        androidx.activity.result.contract.ActivityResultContracts.CreateDocument("application/xml")
    ) { uri -> if (uri != null) writeXmlTo(uri) }

    private fun refreshSyncStatus() {
        if (_b == null) return
        val n = com.itguy.assetmanager.data.SyncStore.pendingCount()
        b.syncStatus.text = if (n == 0) "All changes synced"
            else "$n change${if (n == 1) "" else "s"} waiting to sync"
        b.syncNowBtn.isEnabled = true
    }

    private fun syncNow() {
        if (!com.itguy.assetmanager.data.NetworkUtils.isOnline(requireContext())) {
            showMsg("You're offline — changes will sync automatically when you reconnect.")
            return
        }
        b.syncNowBtn.isEnabled = false
        b.syncStatus.text = "Syncing…"
        lifecycleScope.launch {
            val r = try { com.itguy.assetmanager.data.SyncManager.syncNow(requireContext()) }
                    catch (e: Exception) { null }
            if (_b == null) return@launch
            if (r == null) { showMsg("Sync failed — try again in a moment.") }
            else {
                val parts = mutableListOf<String>()
                if (r.pushed > 0) parts.add("${r.pushed} sent")
                if (r.skipped > 0) parts.add("${r.skipped} kept server copy (newer)")
                if (r.remaining > 0) parts.add("${r.remaining} still pending")
                showMsg(if (parts.isEmpty()) "Everything is up to date." else parts.joinToString(", "))
            }
            refreshSyncStatus()
        }
    }

    private fun writeXmlTo(uri: android.net.Uri) {
        lifecycleScope.launch {
            try {
                val xml = com.itguy.assetmanager.data.XmlExport.build()
                withContextIO {
                    requireContext().contentResolver.openOutputStream(uri)?.use {
                        it.write(xml.toByteArray(Charsets.UTF_8))
                    }
                }
                showMsg("Exported to the file you chose.")
            } catch (e: Exception) {
                showMsg("Export failed: ${e.message}")
            }
        }
    }

    private suspend fun <T> withContextIO(block: suspend () -> T): T =
        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) { block() }

    private fun setupThemePicker() {
        when (Prefs.themeMode) {
            "light" -> b.themeLight.isChecked = true
            "dark" -> b.themeDark.isChecked = true
            else -> b.themeSystem.isChecked = true
        }
        bindAppIcon()
        paintThemePills()
        b.themeGroup.setOnCheckedChangeListener { _, checkedId ->
            paintThemePills()
            val mode = when (checkedId) {
                b.themeLight.id -> "light"
                b.themeDark.id -> "dark"
                else -> "system"
            }
            if (mode != Prefs.themeMode) {
                Prefs.themeMode = mode
                requireActivity().recreate()
            }
        }
    }

    /** The three theme pills, filled in the install's own accent. */
    private fun paintThemePills() {
        if (_b == null) return
        listOf(b.themeSystem, b.themeLight, b.themeDark)
            .forEach { com.itguy.assetmanager.ui.Pills.paint(it, it.isChecked) }
    }

    /**
     * Puts anyone left on an alternative launcher icon back on the default.
     *
     * The control that offered a branded home-screen shortcut is gone, and so
     * is the colour picker before it. Both were answers to "make the icon
     * match our branding" that did not actually do that: the app icon is
     * compiled into the app, and a pinned shortcut sitting beside the real
     * icon is a second entry for the same thing rather than a themed one.
     *
     * This stays because the aliases are still in the manifest -- disabling a
     * component a launcher is currently showing would take the icon off the
     * home screen entirely -- so the reset needs somewhere to run.
     */
    private fun bindAppIcon() {
        if (AppIcon.current(requireContext()) != AppIcon.Variant.DEFAULT) {
            AppIcon.apply(requireContext(), AppIcon.Variant.DEFAULT)
        }
    }

    private fun loadProfile() {
        lifecycleScope.launch {
            try {
                val resp = ApiClient.api().profile()
                val p = resp.body() ?: return@launch
                if (_b == null) return@launch
                b.displayInput.setText((p["display"] as? String).orEmpty())
                b.emailInput.setText((p["email"] as? String).orEmpty())
            } catch (e: Exception) {}
        }
    }

    private fun showMsg(text: String) {
        if (_b == null) return
        b.settingsMsg.text = text
        b.settingsMsg.visibility = View.VISIBLE
    }

    private fun saveProfile() {
        val body = mapOf(
            "display" to b.displayInput.text?.toString()?.trim().orEmpty(),
            "email" to b.emailInput.text?.toString()?.trim().orEmpty()
        )
        lifecycleScope.launch {
            try {
                val resp = ApiClient.api().updateProfile(body)
                showMsg(if (resp.isSuccessful) "✓ Profile saved" else "✕ Save failed")
                if (resp.isSuccessful) Prefs.displayName = b.displayInput.text?.toString()?.trim().orEmpty()
            } catch (e: Exception) { showMsg("✕ ${e.message}") }
        }
    }

    private fun changePassword() {
        val old = b.oldPassInput.text?.toString().orEmpty()
        val new = b.newPassInput.text?.toString().orEmpty()
        if (old.isBlank() || new.isBlank()) { showMsg("Enter both old and new password"); return }
        lifecycleScope.launch {
            try {
                val resp = ApiClient.api().updateProfile(mapOf("old" to old, "new" to new))
                if (resp.isSuccessful) {
                    showMsg("✓ Password updated")
                    b.oldPassInput.setText(""); b.newPassInput.setText("")
                } else {
                    showMsg("✕ Old password incorrect")
                }
            } catch (e: Exception) { showMsg("✕ ${e.message}") }
        }
    }

    private fun confirmChangeServer() {
        com.itguy.assetmanager.ui.BrandDialog(requireContext())
            .setTitle("Change server?")
            .setMessage("You'll be logged out and asked to connect to a server again.")
            .setPositiveButton("Continue") { _, _ ->
                Prefs.clear()
                ApiClient.reset()
                // don't carry one deployment's name/logo over to the next server
                com.itguy.assetmanager.data.Branding.clear(requireContext())
                startActivity(Intent(requireContext(), LoginActivity::class.java))
                requireActivity().finish()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
