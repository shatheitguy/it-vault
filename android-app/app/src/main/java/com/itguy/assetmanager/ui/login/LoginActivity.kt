package com.itguy.assetmanager.ui.login

import android.content.Intent
import android.os.Bundle
import android.view.View
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.Prefs
import com.itguy.assetmanager.data.model.LoginRequest
import com.itguy.assetmanager.databinding.ActivityLoginBinding
import com.itguy.assetmanager.ui.MainActivity
import kotlinx.coroutines.launch

class LoginActivity : AppCompatActivity() {

    private lateinit var b: ActivityLoginBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Prefs.init(applicationContext)

        if (Prefs.isLoggedIn) {
            startActivity(Intent(this, MainActivity::class.java))
            finish()
            return
        }

        b = ActivityLoginBinding.inflate(layoutInflater)
        setContentView(b.root)

        if (Prefs.serverUrl.isNotBlank()) b.serverInput.setText(Prefs.serverUrl)

        b.loginBtn.setOnClickListener { attemptLogin() }
    }

    private fun setBusy(busy: Boolean) {
        b.loginProgress.visibility = if (busy) View.VISIBLE else View.GONE
        b.loginBtn.isEnabled = !busy
    }

    private fun showError(msg: String) {
        b.loginError.text = msg
        b.loginError.visibility = View.VISIBLE
    }

    private fun attemptLogin() {
        val serverRaw = b.serverInput.text?.toString().orEmpty()
        val user = b.userInput.text?.toString()?.trim().orEmpty()
        val pass = b.passInput.text?.toString().orEmpty()
        b.loginError.visibility = View.GONE

        if (serverRaw.isBlank()) { showError("Enter your server address"); return }
        if (user.isBlank() || pass.isBlank()) { showError("Enter username and password"); return }

        val base = ApiClient.normalize(serverRaw)
        setBusy(true)

        lifecycleScope.launch {
            try {
                val api = ApiClient.apiWithCookies(base)
                val loginResp = api.login(LoginRequest(user, pass))
                if (!loginResp.isSuccessful || loginResp.body()?.ok != true) {
                    setBusy(false)
                    showError(loginResp.body()?.error ?: "Login failed -- check username/password and server address")
                    return@launch
                }

                // fetch (or generate) a persistent API key so the app never needs to log in again
                var meResp = api.me()
                var key = meResp.body()?.apiKey.orEmpty()
                val role = meResp.body()?.role ?: loginResp.body()?.role ?: ""
                val display = meResp.body()?.display ?: user

                if (key.isBlank()) {
                    val keyResp = api.generateApiKey()
                    key = keyResp.body()?.apiKey.orEmpty()
                }

                if (key.isBlank()) {
                    setBusy(false)
                    showError("Logged in, but could not obtain a persistent API key from the server. Try again.")
                    return@launch
                }

                Prefs.serverUrl = base
                Prefs.apiKey = key
                Prefs.username = user
                Prefs.role = role
                Prefs.displayName = display
                ApiClient.reset()

                setBusy(false)
                startActivity(Intent(this@LoginActivity, MainActivity::class.java))
                finish()
            } catch (e: Exception) {
                setBusy(false)
                showError("Could not reach that server (${e.message ?: "connection failed"}). Check the address and that the server is running.")
            }
        }
    }
}
