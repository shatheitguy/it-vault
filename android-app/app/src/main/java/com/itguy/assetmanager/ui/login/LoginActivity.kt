package com.itguy.assetmanager.ui.login

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.view.animation.AccelerateDecelerateInterpolator
import android.view.animation.OvershootInterpolator
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.Prefs
import com.itguy.assetmanager.data.ApiService
import com.itguy.assetmanager.data.model.LoginRequest
import com.itguy.assetmanager.data.model.Verify2faRequest
import com.itguy.assetmanager.databinding.ActivityLoginBinding
import com.itguy.assetmanager.ui.MainActivity
import kotlinx.coroutines.launch

class LoginActivity : AppCompatActivity() {

    private lateinit var b: ActivityLoginBinding
    private var pendingApi: ApiService? = null
    private var pendingUser: String = ""
    private var tfaMethods: List<String> = emptyList()
    private var tfaActive: String = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        Prefs.init(applicationContext)
        Prefs.applyThemeMode()
        super.onCreate(savedInstanceState)

        if (Prefs.isLoggedIn) {
            startActivity(Intent(this, MainActivity::class.java))
            finish()
            return
        }

        b = ActivityLoginBinding.inflate(layoutInflater)
        setContentView(b.root)

        if (Prefs.serverUrl.isNotBlank()) b.serverInput.setText(Prefs.serverUrl)

        b.loginBtn.setOnClickListener { attemptLogin() }
        b.verify2faBtn.setOnClickListener { verify2fa() }
        b.switchMethodBtn.setOnClickListener {
            tfaActive = if (tfaActive == "email") tfaMethods.first { it != "email" } else "email"
            renderTfaStep()
        }
        b.resendCodeBtn.setOnClickListener { resendEmailCode() }
        b.backToLoginBtn.setOnClickListener { backToStep1() }

        playEntranceAnimation()
    }

    /** A gentle fade+rise for the card, with the logo popping in slightly
     * after -- mirrors the same entrance the web login page now does. */
    private fun playEntranceAnimation() {
        b.loginRoot.translationY = 40f
        b.loginRoot.animate().alpha(1f).translationY(0f).setDuration(420)
            .setInterpolator(AccelerateDecelerateInterpolator()).start()

        b.loginLogo.scaleX = 0.6f; b.loginLogo.scaleY = 0.6f; b.loginLogo.alpha = 0f
        b.loginLogo.animate().alpha(1f).scaleX(1f).scaleY(1f).setStartDelay(120).setDuration(420)
            .setInterpolator(OvershootInterpolator(2.2f)).start()
    }

    private fun shakeCard() {
        b.loginRoot.animate().translationX(-14f).setDuration(60).withEndAction {
            b.loginRoot.animate().translationX(14f).setDuration(90).withEndAction {
                b.loginRoot.animate().translationX(-8f).setDuration(80).withEndAction {
                    b.loginRoot.animate().translationX(0f).setDuration(70).start()
                }.start()
            }.start()
        }.start()
    }

    private fun setBusy(busy: Boolean) {
        b.loginProgress.visibility = if (busy) View.VISIBLE else View.GONE
        b.loginBtn.isEnabled = !busy
        b.verify2faBtn.isEnabled = !busy
    }

    private fun showError(msg: String) {
        b.loginError.text = msg
        b.loginError.visibility = View.VISIBLE
        shakeCard()
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
                val body = loginResp.body()
                if (!loginResp.isSuccessful || body?.ok != true) {
                    setBusy(false)
                    showError(body?.error ?: "Login failed -- check username/password and server address")
                    return@launch
                }

                if (body.need_2fa) {
                    setBusy(false)
                    pendingApi = api
                    pendingUser = user
                    Prefs.serverUrl = base
                    tfaMethods = body.methods ?: emptyList()
                    tfaActive = tfaMethods.firstOrNull() ?: "totp"
                    showStep2fa()
                    return@launch
                }

                finishLogin(api, base, user, body.role ?: "")
            } catch (e: Exception) {
                setBusy(false)
                showError("Could not reach that server (${e.message ?: "connection failed"}). Check the address and that the server is running.")
            }
        }
    }

    private fun showStep2fa() {
        b.step1.visibility = View.GONE
        b.step2fa.visibility = View.VISIBLE
        b.loginError.visibility = View.GONE
        b.code2fa.setText("")
        renderTfaStep()
    }

    private fun backToStep1() {
        pendingApi = null
        b.step2fa.visibility = View.GONE
        b.step1.visibility = View.VISIBLE
        b.loginError.visibility = View.GONE
        b.passInput.setText("")
    }

    private fun renderTfaStep() {
        val isEmail = tfaActive == "email"
        b.tfaMsg.text = if (isEmail) "We emailed a 6-digit code to your address"
                         else "Enter the 6-digit code from your authenticator app"
        if (tfaMethods.size > 1) {
            b.switchMethodBtn.visibility = View.VISIBLE
            b.switchMethodBtn.text = if (isEmail) "Use authenticator app instead" else "Use email code instead"
        } else {
            b.switchMethodBtn.visibility = View.GONE
        }
        b.resendCodeBtn.visibility = if (isEmail) View.VISIBLE else View.GONE
    }

    private fun verify2fa() {
        val api = pendingApi ?: return
        val code = b.code2fa.text?.toString()?.trim().orEmpty()
        b.loginError.visibility = View.GONE
        if (code.isBlank()) { showError("Enter the code."); return }
        setBusy(true)
        lifecycleScope.launch {
            try {
                val resp = api.verifyLogin2fa(Verify2faRequest(tfaActive, code))
                val body = resp.body()
                if (!resp.isSuccessful || body?.ok != true) {
                    setBusy(false)
                    showError(body?.error ?: "Invalid code")
                    return@launch
                }
                finishLogin(api, Prefs.serverUrl, pendingUser, body.role ?: "")
            } catch (e: Exception) {
                setBusy(false)
                showError("Could not reach the server (${e.message ?: "connection failed"}).")
            }
        }
    }

    private fun resendEmailCode() {
        val api = pendingApi ?: return
        lifecycleScope.launch {
            try {
                val r = api.resendLoginEmailCode()
                showError(if (r.isSuccessful) "Code resent." else (r.body()?.error ?: "Could not resend code."))
            } catch (e: Exception) {
                showError("Could not reach the server.")
            }
        }
    }

    private suspend fun finishLogin(api: ApiService, base: String, user: String, roleFromLogin: String) {
        // fetch (or generate) a persistent API key so the app never needs to log in again
        val meResp = api.me()
        var key = meResp.body()?.apiKey.orEmpty()
        val role = meResp.body()?.role ?: roleFromLogin
        val display = meResp.body()?.display ?: user

        if (key.isBlank()) {
            val keyResp = api.generateApiKey()
            key = keyResp.body()?.apiKey.orEmpty()
        }

        if (key.isBlank()) {
            setBusy(false)
            showError("Logged in, but could not obtain a persistent API key from the server. Try again.")
            return
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
    }
}
