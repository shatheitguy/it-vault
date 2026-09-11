package com.itguy.assetmanager.data

import android.content.Context
import com.google.gson.Gson
import com.itguy.assetmanager.data.model.Asset
import com.itguy.assetmanager.data.model.Contract
import com.itguy.assetmanager.data.model.Employee
import retrofit2.Response
import java.io.IOException
import java.util.UUID

/**
 * The single door every add / edit / delete goes through. Online, it writes
 * straight to the server exactly as before. Offline (or if the write hits a
 * network error mid-flight), it saves the change to the local cache so the UI
 * updates instantly and drops the change into [SyncStore] to be replayed when
 * a connection returns.
 *
 * A genuine server rejection (a duplicate serial, a validation 400) is NOT
 * queued -- that would loop forever -- it comes straight back as [Error].
 */
object Repository {

    private val gson = Gson()

    sealed class SaveResult {
        /** Written to the server now. [serverId] is the record's id when known. */
        data class Synced(val serverId: String?) : SaveResult()
        /** No connection: saved locally, will sync automatically later. */
        object Queued : SaveResult()
        /** The server refused it (validation, duplicate, permission). */
        data class Error(val message: String) : SaveResult()
    }

    // ---------------- assets ----------------

    suspend fun saveAsset(ctx: Context, asset: Asset, existingId: String?): SaveResult {
        val api = ApiClient.api()
        if (NetworkUtils.isOnline(ctx)) {
            try {
                val resp: Response<*> = if (existingId == null)
                    api.createAsset(asset) else api.updateAsset(existingId, asset)
                if (resp.isSuccessful) {
                    refreshAssetCache(ctx)
                    val newId = (resp.body() as? com.itguy.assetmanager.data.model.CreateAssetResponse)?.id
                    return SaveResult.Synced(newId ?: existingId)
                }
                return SaveResult.Error(httpError(resp))
            } catch (e: IOException) {
                /* network dropped -- fall through to queue */
            } catch (e: Exception) {
                return SaveResult.Error(e.message ?: "save failed")
            }
        }
        // offline path
        val id = existingId ?: "tmp-${UUID.randomUUID().hex()}"
        optimisticAsset(asset.copy(id = id), delete = false)
        SyncStore.enqueue(SyncStore.PendingOp(
            localId = UUID.randomUUID().toString(),
            entity = SyncStore.Entity.ASSET,
            op = if (existingId == null) SyncStore.Op.CREATE else SyncStore.Op.UPDATE,
            serverId = existingId ?: "",
            payload = gson.toJson(asset),
            editedAt = System.currentTimeMillis()
        ))
        return SaveResult.Queued
    }

    suspend fun deleteAsset(ctx: Context, id: String): SaveResult {
        val api = ApiClient.api()
        if (NetworkUtils.isOnline(ctx)) {
            try {
                val resp = api.deleteAsset(id)
                if (resp.isSuccessful) { refreshAssetCache(ctx); return SaveResult.Synced(id) }
                return SaveResult.Error(httpError(resp))
            } catch (e: IOException) { /* queue */ }
            catch (e: Exception) { return SaveResult.Error(e.message ?: "delete failed") }
        }
        optimisticAsset(Asset(id = id), delete = true)
        SyncStore.enqueue(SyncStore.PendingOp(
            UUID.randomUUID().toString(), SyncStore.Entity.ASSET, SyncStore.Op.DELETE,
            id, "", System.currentTimeMillis()))
        return SaveResult.Queued
    }

    // ---------------- contracts ----------------

    suspend fun saveContract(ctx: Context, contract: Contract, isNew: Boolean): SaveResult {
        val api = ApiClient.api()
        if (NetworkUtils.isOnline(ctx)) {
            try {
                val resp = if (isNew) api.addContract(contract) else api.updateContract(contract)
                if (resp.isSuccessful) { refreshContractCache(ctx); return SaveResult.Synced(contract.id.toString()) }
                return SaveResult.Error(httpError(resp))
            } catch (e: IOException) { /* queue */ }
            catch (e: Exception) { return SaveResult.Error(e.message ?: "save failed") }
        }
        optimisticContract(contract, delete = false)
        SyncStore.enqueue(SyncStore.PendingOp(
            UUID.randomUUID().toString(), SyncStore.Entity.CONTRACT,
            if (isNew) SyncStore.Op.CREATE else SyncStore.Op.UPDATE,
            if (isNew) "" else contract.id.toString(),
            gson.toJson(contract), System.currentTimeMillis()))
        return SaveResult.Queued
    }

    suspend fun deleteContract(ctx: Context, id: Int): SaveResult {
        val api = ApiClient.api()
        if (NetworkUtils.isOnline(ctx)) {
            try {
                val resp = api.deleteContract(com.itguy.assetmanager.data.model.IdRequest(id))
                if (resp.isSuccessful) { refreshContractCache(ctx); return SaveResult.Synced(id.toString()) }
                return SaveResult.Error(httpError(resp))
            } catch (e: IOException) { /* queue */ }
            catch (e: Exception) { return SaveResult.Error(e.message ?: "delete failed") }
        }
        optimisticContract(Contract(id = id), delete = true)
        SyncStore.enqueue(SyncStore.PendingOp(
            UUID.randomUUID().toString(), SyncStore.Entity.CONTRACT, SyncStore.Op.DELETE,
            id.toString(), "", System.currentTimeMillis()))
        return SaveResult.Queued
    }

    // ---------------- employees ----------------

    suspend fun saveEmployee(ctx: Context, emp: Employee, existingId: String?): SaveResult {
        val api = ApiClient.api()
        if (NetworkUtils.isOnline(ctx)) {
            try {
                val resp: Response<*> = if (existingId == null)
                    api.createEmployee(emp) else api.updateEmployee(existingId, emp)
                if (resp.isSuccessful) { refreshEmployeeCache(ctx); return SaveResult.Synced(existingId) }
                return SaveResult.Error(httpError(resp))
            } catch (e: IOException) { /* queue */ }
            catch (e: Exception) { return SaveResult.Error(e.message ?: "save failed") }
        }
        val id = existingId ?: "tmp-${UUID.randomUUID().hex()}"
        optimisticEmployee(emp.copy(id = id), delete = false)
        SyncStore.enqueue(SyncStore.PendingOp(
            UUID.randomUUID().toString(), SyncStore.Entity.EMPLOYEE,
            if (existingId == null) SyncStore.Op.CREATE else SyncStore.Op.UPDATE,
            existingId ?: "", gson.toJson(emp), System.currentTimeMillis()))
        return SaveResult.Queued
    }

    suspend fun deleteEmployee(ctx: Context, id: String): SaveResult {
        val api = ApiClient.api()
        if (NetworkUtils.isOnline(ctx)) {
            try {
                val resp = api.deleteEmployee(id)
                if (resp.isSuccessful) { refreshEmployeeCache(ctx); return SaveResult.Synced(id) }
                return SaveResult.Error(httpError(resp))
            } catch (e: IOException) { /* queue */ }
            catch (e: Exception) { return SaveResult.Error(e.message ?: "delete failed") }
        }
        optimisticEmployee(Employee(id = id), delete = true)
        SyncStore.enqueue(SyncStore.PendingOp(
            UUID.randomUUID().toString(), SyncStore.Entity.EMPLOYEE, SyncStore.Op.DELETE,
            id, "", System.currentTimeMillis()))
        return SaveResult.Queued
    }

    // ---------------- cache helpers ----------------

    private suspend fun refreshAssetCache(ctx: Context) {
        try {
            val r = ApiClient.api().listAssets()
            if (r.isSuccessful) OfflineCache.saveAssets(r.body().orEmpty())
        } catch (e: Exception) { /* best-effort */ }
    }

    private suspend fun refreshContractCache(ctx: Context) {
        try {
            val r = ApiClient.api().contracts()
            if (r.isSuccessful) OfflineCache.saveContracts(r.body().orEmpty())
        } catch (e: Exception) { }
    }

    private suspend fun refreshEmployeeCache(ctx: Context) {
        try {
            val r = ApiClient.api().listEmployees()
            if (r.isSuccessful) OfflineCache.saveEmployees(r.body().orEmpty())
        } catch (e: Exception) { }
    }

    private fun optimisticAsset(asset: Asset, delete: Boolean) {
        val list = OfflineCache.loadAssets()?.toMutableList() ?: mutableListOf()
        list.removeAll { it.id == asset.id }
        if (!delete) list.add(0, asset)
        OfflineCache.saveAssets(list)
    }

    private fun optimisticContract(contract: Contract, delete: Boolean) {
        val list = OfflineCache.loadContracts()?.toMutableList() ?: mutableListOf()
        list.removeAll { it.id == contract.id }
        if (!delete) list.add(0, contract)
        OfflineCache.saveContracts(list)
    }

    private fun optimisticEmployee(emp: Employee, delete: Boolean) {
        val list = OfflineCache.loadEmployees()?.toMutableList() ?: mutableListOf()
        list.removeAll { it.id == emp.id }
        if (!delete) list.add(0, emp)
        OfflineCache.saveEmployees(list)
    }

    private fun httpError(resp: Response<*>): String {
        return try {
            val body = resp.errorBody()?.string().orEmpty()
            val msg = Regex("\"error\"\\s*:\\s*\"([^\"]*)\"").find(body)?.groupValues?.get(1)
            msg?.ifBlank { null } ?: "Server returned ${resp.code()}"
        } catch (e: Exception) { "Server returned ${resp.code()}" }
    }

    private fun UUID.hex(): String = toString().replace("-", "")
}
