package com.itguy.assetmanager.data

import com.itguy.assetmanager.data.model.*
import retrofit2.Response
import retrofit2.http.*

interface ApiService {

    @POST("api/login")
    suspend fun login(@Body body: LoginRequest): Response<LoginResponse>

    @POST("api/2fa/verify-login")
    suspend fun verifyLogin2fa(@Body body: Verify2faRequest): Response<LoginResponse>

    @POST("api/2fa/resend-email-code")
    suspend fun resendLoginEmailCode(): Response<OkResponse>

    @GET("api/me")
    suspend fun me(): Response<MeResponse>

    @POST("api/profile/apikey")
    suspend fun generateApiKey(): Response<ApiKeyResponse>

    @GET("api/dashboard")
    suspend fun dashboard(): Response<DashboardStats>

    // ---- assets ----
    @GET("api/assets")
    suspend fun listAssets(@Query("q") q: String? = null, @Query("order") order: String? = null): Response<List<Asset>>

    @GET("api/assets/next-tag")
    suspend fun nextAssetTag(): Response<NextTagResponse>

    @GET("api/assets/{id}")
    suspend fun getAsset(@Path("id") id: String): Response<Asset>

    @POST("api/assets")
    suspend fun createAsset(@Body body: Asset): Response<CreateAssetResponse>

    @PUT("api/assets/{id}")
    suspend fun updateAsset(@Path("id") id: String, @Body body: Asset): Response<OkResponse>

    @DELETE("api/assets/{id}")
    suspend fun deleteAsset(@Path("id") id: String): Response<OkResponse>

    @GET("api/assets/trash")
    suspend fun trash(): Response<List<Asset>>

    @POST("api/assets/{id}/restore")
    suspend fun restoreAsset(@Path("id") id: String): Response<OkResponse>

    @DELETE("api/assets/{id}/permanent")
    suspend fun permanentDeleteAsset(@Path("id") id: String): Response<OkResponse>

    // ---- employees ----
    @GET("api/employees")
    suspend fun listEmployees(): Response<List<Employee>>

    @POST("api/employees")
    suspend fun createEmployee(@Body body: Employee): Response<Employee>

    @PUT("api/employees/{id}")
    suspend fun updateEmployee(@Path("id") id: String, @Body body: Employee): Response<OkResponse>

    @DELETE("api/employees/{id}")
    suspend fun deleteEmployee(@Path("id") id: String): Response<OkResponse>

    // ---- tickets ----
    @GET("api/tickets")
    suspend fun listTickets(@Query("status") status: String? = null, @Query("q") q: String? = null): Response<List<Ticket>>

    @GET("api/tickets/{id}")
    suspend fun getTicket(@Path("id") id: Int): Response<TicketDetail>

    @POST("api/tickets")
    suspend fun createTicket(@Body body: Ticket): Response<CreateTicketResponse>

    @PUT("api/tickets/{id}")
    suspend fun updateTicket(@Path("id") id: Int, @Body body: Map<String, @JvmSuppressWildcards Any?>): Response<OkResponse>

    @POST("api/tickets/{id}/reply")
    suspend fun replyTicket(@Path("id") id: Int, @Body body: ReplyRequest): Response<OkResponse>

    // ---- reference lists ----
    @GET("api/categories")
    suspend fun categories(): Response<List<NamedItem>>
    @POST("api/categories")
    suspend fun addCategory(@Body body: NameOnly): Response<OkResponse>
    @HTTP(method = "DELETE", path = "api/categories", hasBody = true)
    suspend fun deleteCategory(@Body body: IdRequest): Response<OkResponse>

    @GET("api/manufacturers")
    suspend fun manufacturers(): Response<List<NamedItem>>
    @POST("api/manufacturers")
    suspend fun addManufacturer(@Body body: NameOnly): Response<OkResponse>
    @HTTP(method = "DELETE", path = "api/manufacturers", hasBody = true)
    suspend fun deleteManufacturer(@Body body: IdRequest): Response<OkResponse>

    @GET("api/models")
    suspend fun models(): Response<List<ModelItem>>
    @POST("api/models")
    suspend fun addModel(@Body body: Map<String, @JvmSuppressWildcards Any?>): Response<OkResponse>
    @HTTP(method = "DELETE", path = "api/models", hasBody = true)
    suspend fun deleteModel(@Body body: IdRequest): Response<OkResponse>

    @GET("api/departments")
    suspend fun departments(): Response<List<NamedItem>>
    @POST("api/departments")
    suspend fun addDepartment(@Body body: NameOnly): Response<OkResponse>
    @HTTP(method = "DELETE", path = "api/departments", hasBody = true)
    suspend fun deleteDepartment(@Body body: IdRequest): Response<OkResponse>

    @GET("api/designations")
    suspend fun designations(): Response<List<NamedItem>>
    @POST("api/designations")
    suspend fun addDesignation(@Body body: NameOnly): Response<OkResponse>
    @HTTP(method = "DELETE", path = "api/designations", hasBody = true)
    suspend fun deleteDesignation(@Body body: IdRequest): Response<OkResponse>

    @GET("api/locations")
    suspend fun locations(): Response<List<LocationItem>>
    @POST("api/locations")
    suspend fun addLocation(@Body body: NameOnly): Response<OkResponse>
    @HTTP(method = "DELETE", path = "api/locations", hasBody = true)
    suspend fun deleteLocation(@Body body: IdRequest): Response<OkResponse>

    @GET("api/contract-types")
    suspend fun contractTypes(): Response<List<NamedItem>>
    @POST("api/contract-types")
    suspend fun addContractType(@Body body: NameOnly): Response<OkResponse>
    @HTTP(method = "DELETE", path = "api/contract-types", hasBody = true)
    suspend fun deleteContractType(@Body body: IdRequest): Response<OkResponse>

    // ---- contracts / AMC / licenses / subscriptions ----
    @GET("api/contracts")
    suspend fun contracts(): Response<List<Contract>>
    @POST("api/contracts")
    suspend fun addContract(@Body body: Contract): Response<OkResponse>
    @PUT("api/contracts")
    suspend fun updateContract(@Body body: Contract): Response<OkResponse>
    @HTTP(method = "DELETE", path = "api/contracts", hasBody = true)
    suspend fun deleteContract(@Body body: IdRequest): Response<OkResponse>

    // ---- audit ----
    @GET("api/audit")
    suspend fun audit(): Response<List<AuditEntry>>

    // ---- UniFi ----
    @GET("api/unifi/devices")
    suspend fun unifiDevices(): Response<UnifiDevicesResponse>
    @GET("api/unifi/clients")
    suspend fun unifiClients(): Response<UnifiClientsResponse>

    // ---- profile / settings ----
    @GET("api/profile")
    suspend fun profile(): Response<Map<String, @JvmSuppressWildcards Any?>>
    @PUT("api/profile")
    suspend fun updateProfile(@Body body: Map<String, @JvmSuppressWildcards Any?>): Response<OkResponse>

    // ---- network scan ----
    @GET("api/scan")
    suspend fun scan(@Query("prefix") prefix: String? = null, @Query("deep") deep: String? = null): Response<List<ScanDevice>>

    // ---- backup / restore ----
    @GET("api/backups")
    suspend fun listBackups(): Response<List<BackupItem>>
    @DELETE("api/backups/{fname}")
    suspend fun deleteBackup(@Path("fname") fname: String): Response<OkResponse>
    @Multipart
    @POST("api/restore")
    suspend fun restore(@Part file: okhttp3.MultipartBody.Part): Response<RestoreResponse>
}
