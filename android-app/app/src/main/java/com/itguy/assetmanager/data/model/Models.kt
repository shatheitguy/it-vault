package com.itguy.assetmanager.data.model

import com.google.gson.annotations.SerializedName

data class LoginRequest(val username: String, val password: String)
data class LoginResponse(val ok: Boolean, val role: String?, val error: String?, val need_2fa: Boolean = false, val methods: List<String>? = null)
data class Verify2faRequest(val method: String, val code: String)

data class ApiKeyResponse(@SerializedName("api_key") val apiKey: String)

data class MeResponse(
    val user: String?,
    val role: String?,
    val display: String?,
    val email: String?,
    @SerializedName("api_key") val apiKey: String?,
    @SerializedName("app_name") val appName: String?
)

data class Asset(
    @SerializedName("_id") val id: String? = null,
    var AssetTag: String = "",
    var Name: String = "",
    var Type: String = "",
    var Serial: String = "",
    var MacAddress: String = "",
    var Location: String = "",
    var Status: String = "Available",
    var Manufacturer: String = "",
    var Model: String = "",
    var ReceivedBy: String = "",
    var NotesReceived: String = "",
    var Note: String = "",
    var PurchaseDate: String = "",
    var WarrantyMonths: Int = 12,
    var Price: String = "0",
    var EmployeeID: String = "",
    val InvoiceFile: String? = null
)

data class CreateAssetResponse(val ok: Boolean?, @SerializedName("_id") val id: String?, val error: String?)
data class NextTagResponse(val tag: String?)
data class CheckoutRequest(val username: String, val signed_date: String, val expected: String, val note: String)

data class Employee(
    @SerializedName("_id") val id: String? = null,
    var EmployeeID: String = "",
    var EmpCode: String = "",
    var EmployeeName: String = "",
    var Designation: String = "",
    var Department: String = "",
    var Email: String = "",
    val source: String? = null
)

data class Ticket(
    val id: Int = 0,
    val code: String? = null,
    var subject: String = "",
    var description: String = "",
    var priority: String = "Normal",
    var status: String = "Open",
    var requester: String = "",
    var requester_email: String = "",
    var assignee: String? = null,
    var asset_id: String? = null,
    var due_date: String? = null,
    var sla_hours: Int = 24,
    var category: String = "",
    val source: String? = null,
    val created_at: String? = null,
    val updated_at: String? = null,
    val reply_count: Int = 0
)

data class TicketDetail(val ticket: Ticket, val replies: List<TicketReply>)
data class CreateTicketResponse(val ok: Boolean?, val id: Int?, val code: String?, val error: String?)
data class TicketReply(val id: Int, val ticket_id: Int, val author: String, val author_role: String, val body: String, val created_at: String)
data class ReplyRequest(val body: String)

data class NamedItem(val id: Int, val name: String)
data class NameOnly(val name: String)
data class LocationItem(val id: Int, val name: String, val parent_id: Int = 0)
data class ModelItem(val id: Int, val name: String, val manufacturer_id: Int?, val manufacturer: String?)

data class Contract(
    val id: Int = 0,
    var name: String = "",
    var vendor: String = "",
    var type: String = "",
    var start_date: String = "",
    var end_date: String = "",
    var cost: Double = 0.0,
    var asset_id: String? = null,
    var employee_id: String = "",
    var location: String = "",
    var department: String = "",
    var license_key: String = "",
    var note: String = ""
)

data class AuditEntry(val id: Int, val ts: String, val actor: String?, val action: String?, val asset_id: String?, val detail: String?)

data class DashboardStats(
    val total: Int = 0,
    val checked_out: Int = 0,
    val maintenance: Int = 0,
    val due_soon: Int = 0,
    val warranty_expiring: Int = 0,
    val by_status: Map<String, Int>? = null,
    val by_type: Map<String, Int>? = null,
    val contracts_total: Int = 0,
    val contracts_by_type: Map<String, Int>? = null,
    val contracts_expiring_soon: Int = 0,
    val expiring_contracts: List<ExpiringContract>? = null
)

data class ExpiringContract(val id: Int, val name: String, val vendor: String?, val type: String?, val end_date: String?, val days_left: Int)

data class UnifiDevice(val name: String?, val model: String?, val type: String?, val ip: String?, val mac: String?, val online: Boolean, val version: String?, val uptime: Long, val num_sta: Int)
data class UnifiDevicesResponse(val devices: List<UnifiDevice>?, val error: String?)
data class UnifiClient(val hostname: String?, val ip: String?, val mac: String?, val is_wired: Boolean, val essid: String?, val network: String?, val uptime: Long, val signal: Int?)
data class UnifiClientsResponse(val clients: List<UnifiClient>?, val error: String?)

data class OkResponse(val ok: Boolean?, val error: String?)
data class SignLinkResponse(val ok: Boolean?, val token: String?, val url: String?, val error: String?)
data class IdRequest(val id: Int)

data class ScanDevice(val ip: String, val mac: String?, val type: String?, val host: String?, val vendor: String?)
data class BackupItem(val file: String, val scope: String, val created: String, val size: Long)
data class RestoreResponse(val ok: Boolean?, val statements: Int?, val error: String?)

// ---- Heartbeat: uptime monitoring ----
// `bars` is the status of each recent check, oldest first, and `series` the
// response times of the ones that answered. EcgView draws the trace from
// exactly these two, the same way the web page does.
data class HbMonitor(
    val id: Int,
    val name: String?,
    val kind: String?,
    val target: String?,
    val port: Int?,
    val keyword: String?,
    val tag: String?,
    val note: String?,
    val status: String?,
    val enabled: Int?,
    val notify: Int?,
    val upside_down: Int?,
    val fails: Int?,
    val fail_threshold: Int?,
    val interval_s: Int?,
    val timeout_s: Int?,
    val retry_interval_s: Int?,
    val resend_every: Int?,
    val last_ms: Int?,
    val last_error: String?,
    val last_check: String?,
    val last_change: String?,
    val cert_days: Int?,
    val uptime: Double?,
    val avg_ms: Int?,
    val samples: Int?,
    val accepted_codes: String?,
    val http_method: String?,
    val ignore_tls: Int?,
    val keyword_invert: Int?,
    val channels: String?,
    val asset_id: String?,
    val next_check: String?,
    val bars: List<String>?,
    val series: List<Int>?
) {
    /** Paused is not a server status: it is what enabled=0 means to a reader. */
    val uiStatus: String get() = if ((enabled ?: 1) == 0) "paused" else (status ?: "pending")
    val label: String get() = name?.takeIf { it.isNotBlank() } ?: target.orEmpty()
    val where: String get() = (target.orEmpty()) + (port?.let { ":$it" } ?: "")
}

data class HbCounts(val up: Int?, val down: Int?, val pending: Int?, val disabled: Int?)
data class HbChannelLite(val id: Int, val name: String?, val kind: String?, val enabled: Int?)
data class HbState(
    val monitors: List<HbMonitor>?,
    val counts: HbCounts?,
    val channels: List<HbChannelLite>?,
    val window_hours: Int?,
    val retain_days: Int?
)
data class HbWindow(val uptime: Double?, val checks: Int?, val avg_ms: Int?)
data class HbPoint(val t: String?, val status: String?, val ms: Int?)
data class HbEvent(val t: String?, val kind: String?, val message: String?)
data class HbDetail(
    val monitor: HbMonitor?,
    val windows: Map<String, HbWindow>?,
    val series: List<HbPoint>?,
    val events: List<HbEvent>?,
    val window_hours: Int?
)
data class HbCheckResponse(val ok: Boolean?, val checked: Int?)
data class HbCreateResponse(val ok: Boolean?, val id: Int?, val error: String?)

/** Only the fields the phone form actually sets -- nulls are left to the
 *  server's own defaults, and on an edit to the monitor's stored values. */
data class HbMonitorRequest(
    val name: String?,
    val kind: String?,
    val target: String?,
    val port: Int?,
    val keyword: String?,
    val tag: String?,
    val note: String?,
    val interval_s: Int?,
    val fail_threshold: Int?,
    val timeout_s: Int?,
    val notify: Boolean?,
    val enabled: Boolean?
)
