package com.itguy.assetmanager.ui.settings

import android.app.AlertDialog
import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.Prefs
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

        b.saveProfileBtn.setOnClickListener { saveProfile() }
        b.changePassBtn.setOnClickListener { changePassword() }
        b.changeServerBtn.setOnClickListener { confirmChangeServer() }
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
        AlertDialog.Builder(requireContext())
            .setTitle("Change server?")
            .setMessage("You'll be logged out and asked to connect to a server again.")
            .setPositiveButton("Continue") { _, _ ->
                Prefs.clear()
                ApiClient.reset()
                startActivity(Intent(requireContext(), LoginActivity::class.java))
                requireActivity().finish()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
