package com.itguy.assetmanager.data

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkRequest
import com.google.gson.Gson
import com.itguy.assetmanager.data.model.Asset
import com.itguy.assetmanager.data.model.Contract
import com.itguy.assetmanager.data.model.Employee
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.text.SimpleDateFormat
import java.util.Locale

/**
 * Replays the offline outbox to the server and refreshes the local cache.
 *
 * Conflict rule ("whichever was edited latest wins"): before pushing an *edit*
 * of an existing record, the server's own last-modified time is compared to
 * when the edit was made on the phone. If the server copy is newer, the phone's
 * queued edit is dropped and the server wins; otherwise the phone's edit is
 * pushed and becomes the newest. Creates and deletes are always applied.
 *
 * Wall-clock caveat: this compares the phone clock against the server clock, so
 * a badly wrong device clock skews the decision. For normal use (clocks within
 * a minute or two) it does what you'd expect.
 */
object SyncManager {

    data class Result(val pushed: Int, val skipped: Int, val failed: Int, val remaining: Int)

    private val gson = Gson()
    private val mutex = Mutex()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    @Volatile private var registered = false

    /** Server timestamps are "yyyy-MM-dd HH:mm:ss" in the server's local zone. */
    private val fmt = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US)

    private fun serverMillis(s: String?): Long =
        try { if (s.isNullOrBlank()) 0L else fmt.parse(s)?.time ?: 0L } catch (e: Exception) { 0L }

    /**
     * Start listening for the network coming back, so a queued edit syncs on
     * its own without the user opening anything. Safe to call more than once.
     */
    fun startAutoSync(context: Context) {
        if (registered) return
        val app = context.applicationContext
        val cm = app.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager ?: return
        val req = NetworkRequest.Builder()
            .addCapability(android.net.NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .build()
        try {
            cm.registerNetworkCallback(req, object : ConnectivityManager.NetworkCallback() {
                override fun onAvailable(network: Network) {
                    if (SyncStore.pendingCount() > 0) scope.launch { runCatching { syncNow(app) } }
                }
            })
            registered = true
        } catch (e: Exception) { /* some OEMs cap callbacks -- sync still works manually */ }
    }

    /**
     * Push the outbox (best effort, stopping the push loop on the first genuine
     * network failure so ordering is preserved) then pull fresh data into the
     * cache. Serialised so two triggers can't run it at once.
     */
    suspend fun syncNow(context: Context): Result = mutex.withLock {
        if (!NetworkUtils.isOnline(context)) return Result(0, 0, 0, SyncStore.pendingCount())
        val api = ApiClient.api()

        // server snapshot used for the last-write-wins comparison
        val assetTs = HashMap<String, Long>()
        val contractTs = HashMap<String, Long>()
        val employeeTs = HashMap<String, Long>()
        try {
            api.listAssets().body()?.forEach { it.id?.let { id -> assetTs[id] = serverMillis(it.updatedAt) } }
            api.contracts().body()?.forEach { contractTs[it.id.toString()] = serverMillis(it.updatedAt) }
            api.listEmployees().body()?.forEach { it.id?.let { id -> employeeTs[id] = serverMillis(it.updatedAt) } }
        } catch (e: Exception) {
            return Result(0, 0, 0, SyncStore.pendingCount())   // can't reach server after all
        }

        var pushed = 0; var skipped = 0; var failed = 0
        for (op in SyncStore.all()) {
            try {
                val ok = when (op.entity) {
                    SyncStore.Entity.ASSET -> pushAsset(op, assetTs)
                    SyncStore.Entity.CONTRACT -> pushContract(op, contractTs)
                    SyncStore.Entity.EMPLOYEE -> pushEmployee(op, employeeTs)
                    else -> PushOutcome.DROP
                }
                when (ok) {
                    PushOutcome.PUSHED -> { SyncStore.remove(op.localId); pushed++ }
                    PushOutcome.SKIPPED -> { SyncStore.remove(op.localId); skipped++ }
                    PushOutcome.DROP -> SyncStore.remove(op.localId)
                    PushOutcome.RETRY -> { failed++; break }   // network gone; keep order, try later
                }
            } catch (e: java.io.IOException) { failed++; break }
            catch (e: Exception) { SyncStore.remove(op.localId); failed++ }
        }

        // pull fresh server state so the cache reflects reality (our pushes +
        // anything changed elsewhere)
        try {
            api.listAssets().body()?.let { OfflineCache.saveAssets(it) }
            api.contracts().body()?.let { OfflineCache.saveContracts(it) }
            api.listEmployees().body()?.let { OfflineCache.saveEmployees(it) }
        } catch (e: Exception) { }

        return Result(pushed, skipped, failed, SyncStore.pendingCount())
    }

    private enum class PushOutcome { PUSHED, SKIPPED, DROP, RETRY }

    private suspend fun pushAsset(op: SyncStore.PendingOp, ts: Map<String, Long>): PushOutcome {
        val api = ApiClient.api()
        return when (op.op) {
            SyncStore.Op.CREATE -> {
                val a = gson.fromJson(op.payload, Asset::class.java)
                if (api.createAsset(a).isSuccessful) PushOutcome.PUSHED else PushOutcome.RETRY
            }
            SyncStore.Op.UPDATE -> {
                val server = ts[op.serverId] ?: return PushOutcome.DROP   // gone on server
                if (server > op.editedAt) return PushOutcome.SKIPPED       // server edited later
                val a = gson.fromJson(op.payload, Asset::class.java)
                if (api.updateAsset(op.serverId, a).isSuccessful) PushOutcome.PUSHED else PushOutcome.RETRY
            }
            SyncStore.Op.DELETE ->
                if (api.deleteAsset(op.serverId).isSuccessful) PushOutcome.PUSHED else PushOutcome.RETRY
            else -> PushOutcome.DROP
        }
    }

    private suspend fun pushContract(op: SyncStore.PendingOp, ts: Map<String, Long>): PushOutcome {
        val api = ApiClient.api()
        return when (op.op) {
            SyncStore.Op.CREATE -> {
                val c = gson.fromJson(op.payload, Contract::class.java)
                if (api.addContract(c).isSuccessful) PushOutcome.PUSHED else PushOutcome.RETRY
            }
            SyncStore.Op.UPDATE -> {
                val server = ts[op.serverId] ?: return PushOutcome.DROP
                if (server > op.editedAt) return PushOutcome.SKIPPED
                val c = gson.fromJson(op.payload, Contract::class.java)
                if (api.updateContract(c).isSuccessful) PushOutcome.PUSHED else PushOutcome.RETRY
            }
            SyncStore.Op.DELETE ->
                if (api.deleteContract(com.itguy.assetmanager.data.model.IdRequest(op.serverId.toIntOrNull() ?: 0)).isSuccessful)
                    PushOutcome.PUSHED else PushOutcome.RETRY
            else -> PushOutcome.DROP
        }
    }

    private suspend fun pushEmployee(op: SyncStore.PendingOp, ts: Map<String, Long>): PushOutcome {
        val api = ApiClient.api()
        return when (op.op) {
            SyncStore.Op.CREATE -> {
                val e = gson.fromJson(op.payload, Employee::class.java)
                if (api.createEmployee(e).isSuccessful) PushOutcome.PUSHED else PushOutcome.RETRY
            }
            SyncStore.Op.UPDATE -> {
                val server = ts[op.serverId] ?: return PushOutcome.DROP
                if (server > op.editedAt) return PushOutcome.SKIPPED
                val e = gson.fromJson(op.payload, Employee::class.java)
                if (api.updateEmployee(op.serverId, e).isSuccessful) PushOutcome.PUSHED else PushOutcome.RETRY
            }
            SyncStore.Op.DELETE ->
                if (api.deleteEmployee(op.serverId).isSuccessful) PushOutcome.PUSHED else PushOutcome.RETRY
            else -> PushOutcome.DROP
        }
    }
}
