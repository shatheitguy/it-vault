package com.itguy.assetmanager.ui

import android.animation.ValueAnimator
import android.app.Activity
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.lifecycle.LifecycleCoroutineScope
import com.itguy.assetmanager.R
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.OfflineCache
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.random.Random

/**
 * The screen between opening the app and the dashboard having something on it.
 *
 * Two jobs, and the second is the one that matters:
 *
 * It says what the app is doing. Landing on an empty dashboard that fills in
 * a second later reads as broken rather than busy.
 *
 * And it warms every cache while it is up. Before this, a list was only ever
 * cached once you had visited its screen with a signal -- so the first time
 * you opened Contracts in a store room with no bars, there was nothing to
 * show. Pulling all of them here means the whole app is populated from the
 * moment it opens, network or not.
 */
object BootOverlay {

    /** Shows the overlay, warms the caches, then fades it away. */
    fun show(activity: Activity, scope: LifecycleCoroutineScope) {
        val view = activity.layoutInflater.inflate(R.layout.view_boot, null)
        activity.addContentView(
            view,
            ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            ),
        )
        val status = view.findViewById<TextView>(R.id.bootStatus)
        val glitch = startGlitch(view)

        scope.launch {
            val online = warmCaches { step -> status.text = step }
            status.text = if (online) "READY" else "OFFLINE  ·  USING SAVED DATA"
            // long enough to read the last line, short enough not to be a wait
            view.postDelayed({
                glitch.cancel()
                view.animate().alpha(0f).setDuration(260).withEndAction {
                    (view.parent as? ViewGroup)?.removeView(view)
                }.start()
            }, if (online) 260 else 900)
        }
    }

    /**
     * Pull every list the app can show, into the cache.
     *
     * Each one is guarded on its own: a deployment without contracts, or a
     * user without rights to the directory, must not stop the rest being
     * cached. Returns false when the first call could not reach the server at
     * all, which is what "offline" means here.
     */
    private suspend fun warmCaches(onStep: (String) -> Unit): Boolean {
        var reached = false
        suspend fun step(label: String, block: suspend () -> Unit) {
            withContext(Dispatchers.Main) { onStep(label) }
            try {
                block()
                reached = true
            } catch (_: Exception) {
                // a screen this user cannot see, or a server that is not
                // there: neither is a reason to stop warming the others
            }
        }

        // body() is null on a non-2xx, and a null body must not be cached as
        // an empty list -- that would replace real saved data with nothing.
        step("CONNECTING TO SERVER") {
            ApiClient.api().dashboard().body()?.let { OfflineCache.saveDashboard(it) }
        }
        step("SYNCING ASSETS") {
            ApiClient.api().listAssets().body()?.let { OfflineCache.saveAssets(it) }
        }
        step("SYNCING CONTRACTS") {
            ApiClient.api().contracts().body()?.let { OfflineCache.saveContracts(it) }
        }
        step("SYNCING DIRECTORY") {
            ApiClient.api().listEmployees().body()?.let { OfflineCache.saveEmployees(it) }
        }
        step("SYNCING TICKETS") {
            ApiClient.api().listTickets().body()?.let { OfflineCache.saveTickets(it) }
        }
        return reached
    }

    /**
     * The glitch: a red copy and a cyan copy of the title, jittered a pixel or
     * two either side of the white one, on a timer that is mostly still. A
     * constant shake is a distraction; an occasional one reads as a machine
     * working.
     */
    private fun startGlitch(root: View): ValueAnimator {
        val red = root.findViewById<TextView>(R.id.bootTitleRed)
        val cyan = root.findViewById<TextView>(R.id.bootTitleCyan)
        return ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 1400
            repeatCount = ValueAnimator.INFINITE
            addUpdateListener {
                val f = it.animatedFraction
                // three short bursts per cycle, still the rest of the time
                val busy = f < 0.08f || (f in 0.42f..0.48f) || f > 0.93f
                val d = if (busy) Random.nextFloat() * 5f - 2.5f else 0f
                red.translationX = d
                cyan.translationX = -d
                red.alpha = if (busy) 0.85f else 0.35f
                cyan.alpha = if (busy) 0.85f else 0.35f
            }
            start()
        }
    }
}
