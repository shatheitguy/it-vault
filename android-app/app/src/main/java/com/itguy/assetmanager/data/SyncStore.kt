package com.itguy.assetmanager.data

import android.content.Context
import android.content.SharedPreferences
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken

/**
 * The offline outbox. Every add/edit/delete the user makes while the server
 * can't be reached is written here as a [PendingOp] and replayed by
 * [SyncManager] once a connection returns. Persisted to disk so a queued edit
 * survives the app being closed, a reboot, or days offline.
 *
 * Each op carries the wall-clock time of the edit ([editedAt], epoch millis),
 * which is what the "newest edit wins" conflict rule compares against the
 * server's own last-modified time.
 */
object SyncStore {

    /** Entity kinds the outbox understands. Values are stable on-disk keys. */
    object Entity {
        const val ASSET = "asset"
        const val CONTRACT = "contract"
        const val EMPLOYEE = "employee"
    }

    /** What happened to the record. */
    object Op {
        const val CREATE = "create"
        const val UPDATE = "update"
        const val DELETE = "delete"
    }

    /**
     * One queued change.
     * @param localId    stable id for this queue entry (dedup / removal)
     * @param entity     one of [Entity]
     * @param op         one of [Op]
     * @param serverId   the record's server id (blank for a not-yet-synced create)
     * @param payload    JSON of the full entity for create/update; empty for delete
     * @param editedAt   epoch millis when the user made the edit (for last-write-wins)
     */
    data class PendingOp(
        val localId: String,
        val entity: String,
        val op: String,
        var serverId: String,
        val payload: String,
        val editedAt: Long
    )

    private const val FILE = "itvault_sync_outbox"
    private lateinit var prefs: SharedPreferences
    private val gson = Gson()
    private val lock = Any()

    fun init(context: Context) {
        if (::prefs.isInitialized) return
        prefs = context.applicationContext.getSharedPreferences(FILE, Context.MODE_PRIVATE)
    }

    fun all(): List<PendingOp> = synchronized(lock) {
        val json = prefs.getString("ops", null) ?: return emptyList()
        return try {
            gson.fromJson(json, object : TypeToken<List<PendingOp>>() {}.type) ?: emptyList()
        } catch (e: Exception) { emptyList() }
    }

    fun pendingCount(): Int = all().size

    /**
     * Queue a change. If an unsynced op for the *same* record already exists we
     * collapse onto it so a record edited five times offline syncs once:
     *  - a later edit replaces an earlier queued create/update's payload
     *  - a delete after an unsynced create just drops the create (never existed
     *    on the server, so nothing to send)
     */
    fun enqueue(op: PendingOp) = synchronized(lock) {
        val list = all().toMutableList()
        val existingIdx = list.indexOfFirst {
            it.entity == op.entity && it.serverId.isNotBlank() && it.serverId == op.serverId
        }
        if (existingIdx >= 0) {
            val existing = list[existingIdx]
            if (op.op == Op.DELETE && existing.op == Op.CREATE) {
                list.removeAt(existingIdx)          // created then deleted offline: no-op
                persist(list)
                return
            }
            // keep the original op kind (a create stays a create) but take the
            // newest payload and edit time
            list[existingIdx] = existing.copy(
                op = if (existing.op == Op.CREATE) Op.CREATE else op.op,
                payload = op.payload.ifBlank { existing.payload },
                editedAt = op.editedAt
            )
            persist(list)
            return
        }
        list.add(op)
        persist(list)
    }

    fun remove(localId: String) = synchronized(lock) {
        persist(all().filterNot { it.localId == localId })
    }

    /** After a create finally syncs, later queued ops for it need the real id. */
    fun rebindServerId(entity: String, tempId: String, realId: String) = synchronized(lock) {
        persist(all().map {
            if (it.entity == entity && it.serverId == tempId) it.copy(serverId = realId) else it
        })
    }

    fun clear() = synchronized(lock) { persist(emptyList()) }

    private fun persist(list: List<PendingOp>) {
        prefs.edit().putString("ops", gson.toJson(list)).apply()
    }
}
