package com.itguy.assetmanager.data

import android.content.Context
import android.content.SharedPreferences
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import com.itguy.assetmanager.data.model.Asset
import com.itguy.assetmanager.data.model.Contract
import com.itguy.assetmanager.data.model.Employee
import com.itguy.assetmanager.data.model.DashboardStats
import com.itguy.assetmanager.data.model.HbState
import com.itguy.assetmanager.data.model.Ticket

/**
 * Read-only offline cache: the last successful fetch of each main list is
 * kept on disk so the app still shows something useful with no connection.
 * Nothing here supports offline editing -- add/edit/delete still require a
 * live connection, same as before. Data is refreshed and overwritten every
 * time a real fetch succeeds.
 */
object OfflineCache {
    private const val FILE = "itguy_offline_cache"
    private lateinit var prefs: SharedPreferences
    private val gson = Gson()

    fun init(context: Context) {
        if (::prefs.isInitialized) return
        prefs = context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
    }

    fun saveAssets(list: List<Asset>) = save("assets", list)
    fun loadAssets(): List<Asset>? = load("assets", object : TypeToken<List<Asset>>() {}.type)

    fun saveContracts(list: List<Contract>) = save("contracts", list)
    fun loadContracts(): List<Contract>? = load("contracts", object : TypeToken<List<Contract>>() {}.type)

    fun saveEmployees(list: List<Employee>) = save("employees", list)
    fun loadEmployees(): List<Employee>? = load("employees", object : TypeToken<List<Employee>>() {}.type)

    fun saveDashboard(stats: DashboardStats) = save("dashboard", stats)
    fun loadDashboard(): DashboardStats? = load("dashboard", DashboardStats::class.java)

    fun saveTickets(list: List<Ticket>) = save("tickets", list)
    fun loadTickets(): List<Ticket>? = load("tickets", object : TypeToken<List<Ticket>>() {}.type)

    fun saveHeartbeat(state: HbState) = save("heartbeat", state)
    fun loadHeartbeat(): HbState? = load("heartbeat", HbState::class.java)

    /**
     * The reference-style lists (Product Catalog, Trash, Audit Log) share one
     * screen, so they share one cache keyed by which list it is -- and the
     * Catalog's tabs are separate lists in their own right, hence the suffix.
     * Keyed rather than lumped together: a stale Trash must never be shown as
     * the Catalog.
     */
    fun saveRows(kind: String, rows: List<String>) = save("rows_$kind", rows)
    fun loadRows(kind: String): List<String>? =
        load("rows_$kind", object : TypeToken<List<String>>() {}.type)

    fun rowsUpdated(kind: String): Long = lastUpdated("rows_$kind")

    /** Millis since epoch when [key]'s cache was last written, or 0 if never. */
    fun lastUpdated(key: String): Long = prefs.getLong("${key}_ts", 0L)

    private fun save(key: String, data: Any) {
        prefs.edit()
            .putString(key, gson.toJson(data))
            .putLong("${key}_ts", System.currentTimeMillis())
            .apply()
    }

    private fun <T> load(key: String, type: java.lang.reflect.Type): T? {
        val json = prefs.getString(key, null) ?: return null
        return try { gson.fromJson(json, type) } catch (e: Exception) { null }
    }
}
