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
import kotlinx.coroutines.delay
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

    /**
     * The least time it stays on screen.
     *
     * On a fast LAN the warm-up finishes in a couple of hundred
     * milliseconds, and an animation nobody can see is not an animation --
     * this is the whole of what "there is no animation on the landing
     * screen" turned out to mean, once the overlay was no longer being torn
     * down by setContentView. A slower server extends it; nothing shortens
     * it.
     */
    private const val MIN_VISIBLE_MS = 1900L

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
        val started = System.currentTimeMillis()
        val animators = startGlitch(view)

        scope.launch {
            val online = warmCaches { step -> status.text = step }
            status.text = if (online) "READY" else "OFFLINE  ·  USING SAVED DATA"
            // hold the last line long enough to read, and the animation long
            // enough to have been seen
            val shown = System.currentTimeMillis() - started
            val hold = (if (online) MIN_VISIBLE_MS else MIN_VISIBLE_MS + 600) - shown
            if (hold > 0) delay(hold)
            animators.forEach { it.cancel() }
            view.animate().alpha(0f).setDuration(280).withEndAction {
                (view.parent as? ViewGroup)?.removeView(view)
            }.start()
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
        // The dropdowns every form is built from. Small, they change about
        // once a month, and without them a form cannot draw itself from the
        // cache at all -- which is what made opening a record wait on the
        // network even when the record itself was already here.
        step("SYNCING LISTS") {
            ApiClient.api().categories().body()?.let { OfflineCache.saveCategories(it) }
            ApiClient.api().manufacturers().body()?.let { OfflineCache.saveManufacturers(it) }
            ApiClient.api().models().body()?.let { OfflineCache.saveModels(it) }
            ApiClient.api().locations().body()?.let { OfflineCache.saveLocations(it) }
            ApiClient.api().departments().body()?.let { OfflineCache.saveDepartments(it) }
            ApiClient.api().contractTypes().body()?.let { OfflineCache.saveContractTypes(it) }
        }
        return reached
    }

    /**
     * The glitch, in three parts.
     *
     * The title is drawn three times -- a red copy and a cyan copy behind a
     * white one -- and the coloured pair pull apart in short bursts on a
     * timer that is mostly still: a constant shake is a distraction, an
     * occasional one reads as a machine working. On the same bursts the whole
     * block slips sideways a pixel or two and the white copy dips in opacity,
     * which is what makes it look like a signal rather than a wobble.
     *
     * And a bar sweeps down over the mark, continuously, because that is the
     * part that is visible from across a room.
     */
    private fun startGlitch(root: View): List<ValueAnimator> {
        val red = root.findViewById<TextView>(R.id.bootTitleRed)
        val cyan = root.findViewById<TextView>(R.id.bootTitleCyan)
        val white = root.findViewById<TextView>(R.id.bootTitle)
        val block = root.findViewById<View>(R.id.bootTitleWrap)
        val sweep = root.findViewById<View>(R.id.bootSweep)
        val logoWrap = root.findViewById<View>(R.id.bootLogoWrap)

        val split = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 1400
            repeatCount = ValueAnimator.INFINITE
            addUpdateListener {
                val f = it.animatedFraction
                // three short bursts per cycle, still the rest of the time
                val busy = f < 0.08f || (f in 0.42f..0.48f) || f > 0.93f
                val d = if (busy) Random.nextFloat() * 7f - 3.5f else 0f
                red.translationX = d
                cyan.translationX = -d
                red.alpha = if (busy) 0.9f else 0.32f
                cyan.alpha = if (busy) 0.9f else 0.32f
                // the tear: the whole line jumps, and the top copy thins out
                block.translationX = if (busy) Random.nextFloat() * 4f - 2f else 0f
                white.alpha = if (busy) 0.78f else 1f
            }
            start()
        }

        val scan = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 1100
            repeatCount = ValueAnimator.INFINITE
            addUpdateListener {
                val f = it.animatedFraction
                val h = logoWrap.height.toFloat()
                if (h <= 0f) return@addUpdateListener
                sweep.translationY = f * (h - sweep.height)
                // brightest crossing the middle, gone at the edges, so it
                // reads as a pass rather than a bar parked at the bottom
                sweep.alpha = 1f - kotlin.math.abs(f - 0.5f) * 1.7f
            }
            start()
        }

        return listOf(split, scan)
    }
}
