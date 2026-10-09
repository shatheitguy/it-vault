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
        // Themed before the first frame from the cached palette, so signing
        // back in to a server you have used before does not flash red first.
        com.itguy.assetmanager.data.Palette.apply(b.root)

        if (Prefs.serverUrl.isNotBlank()) b.serverInput.setText(Prefs.serverUrl)

        // The band at the top is the install's own colour, so the status bar
        // has to be too -- a white strip above a red band looks like a bug.
        // Icons go light for the same reason.
        window.statusBarColor = resolveAccent()
        androidx.core.view.WindowCompat.getInsetsController(window, b.root)
            .isAppearanceLightStatusBars = false

        // Their name and their mark, as soon as the phone has seen them once.
        // Before that it is ours, which is also the honest answer: no server
        // has been contacted yet.
        com.itguy.assetmanager.data.Branding.apply(this, b.brandName, b.loginLogo)
        if (Prefs.brandName.isNotBlank()) b.brandTagline.text = "Asset management"

        b.forgotBtn.setOnClickListener { openPasswordReset() }

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

    /** The accent as the theme currently resolves it -- the server's colour
     * once branding has synced, ours until then. */
    private fun resolveAccent(): Int {
        val tv = android.util.TypedValue()
        return if (theme.resolveAttribute(
                com.google.android.material.R.attr.colorPrimary, tv, true)) tv.data
        else androidx.core.content.ContextCompat.getColor(this, com.itguy.assetmanager.R.color.accent)
    }

    /**
     * Resetting a password is a job for the server's own page: it sends the
     * code, and the code never leaves the server now. The app's part is to
     * open it at the right address rather than leaving someone stuck on a
     * screen with no way forward.
     */
    private fun openPasswordReset() {
        val raw = b.serverInput.text?.toString().orEmpty().ifBlank { Prefs.serverUrl }
        if (raw.isBlank()) {
            showError("Enter your server address first, then tap Forgot password.")
            return
        }
        val url = ApiClient.normalize(raw)
        try {
            startActivity(Intent(Intent.ACTION_VIEW, android.net.Uri.parse(url)))
        } catch (e: Exception) {
            showError("Could not open $url")
        }
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

    /** Set once the person has been told about an unencrypted address. */
    private var cleartextAccepted = false

    private fun attemptLogin() {
        val serverRaw = b.serverInput.text?.toString().orEmpty()
        val user = b.userInput.text?.toString()?.trim().orEmpty()
        val pass = b.passInput.text?.toString().orEmpty()
        b.loginError.visibility = View.GONE

        if (serverRaw.isBlank()) { showError("Enter your server address"); return }
        if (user.isBlank() || pass.isBlank()) { showError("Enter username and password"); return }

        val base = ApiClient.normalize(serverRaw)
        // Said once, before the password goes anywhere. Not a block: plenty
        // of installs are reachable only over a VPN where this is fine, and
        // the person in front of the phone knows which theirs is.
        if (ApiClient.isPublicCleartext(serverRaw) && !cleartextAccepted) {
            setBusy(false)
            com.google.android.material.dialog.MaterialAlertDialogBuilder(this)
                .setTitle("This address is not encrypted")
                .setMessage(
                    "You are connecting to a public address over plain HTTP. " +
                    "Your password and the key this app stores afterwards " +
                    "travel unencrypted and can be read on the way.\n\n" +
                    "If the server is on your own network or reached over a " +
                    "VPN this is usually fine. Otherwise ask IT for an " +
                    "https:// address."
                )
                .setPositiveButton("Connect anyway") { _, _ ->
                    cleartextAccepted = true
                    attemptLogin()
                }
                .setNegativeButton("Cancel", null)
                .show()
            return
        }
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
