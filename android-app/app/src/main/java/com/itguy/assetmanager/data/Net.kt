package com.itguy.assetmanager.data

import android.content.Context
import android.net.Uri
import com.google.gson.JsonArray
import com.google.gson.JsonElement
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import retrofit2.Response

/** A refusal from the server, carrying the sentence it gave (or a plain one). */
class ApiError(message: String, val code: Int = 0) : Exception(message)

/**
 * The settings screens talk to the same endpoints the web does, one for one.
 * This keeps each of those calls to a line: JSON in, JSON out, and the
 * server's own "error" sentence thrown as an [ApiError] when it says no.
 */
object Net {
    private fun api() = ApiClient.api()

    private fun <T : JsonElement> unwrap(r: Response<JsonElement>): JsonElement {
        if (r.isSuccessful) return r.body() ?: JsonObject()
        val raw = try { r.errorBody()?.string().orEmpty() } catch (e: Exception) { "" }
        val msg = try { JsonParser.parseString(raw).asJsonObject.get("error")?.asString } catch (e: Exception) { null }
        throw ApiError(msg ?: when (r.code()) {
            401 -> "Signed out. Sign in again."
            403 -> "Your account is not allowed to do that."
            404 -> "Not found on this server (is it up to date?)."
            else -> "The server said ${r.code()}."
        }, r.code())
    }

    suspend fun get(path: String): JsonObject = unwrap<JsonObject>(api().getJson(path)).let {
        if (it.isJsonObject) it.asJsonObject else JsonObject().apply { add("items", it) }
    }
    suspend fun getArray(path: String): JsonArray = unwrap<JsonArray>(api().getJson(path)).let {
        if (it.isJsonArray) it.asJsonArray else JsonArray()
    }
    suspend fun post(path: String, body: JsonObject = JsonObject()): JsonObject =
        unwrap<JsonObject>(api().postJson(path, body)).let { if (it.isJsonObject) it.asJsonObject else JsonObject() }
    suspend fun put(path: String, body: JsonObject): JsonObject =
        unwrap<JsonObject>(api().putJson(path, body)).let { if (it.isJsonObject) it.asJsonObject else JsonObject() }
    suspend fun delete(path: String): JsonObject =
        unwrap<JsonObject>(api().deleteJson(path)).let { if (it.isJsonObject) it.asJsonObject else JsonObject() }

    suspend fun deleteWithId(path: String, id: Int): JsonObject =
        unwrap<JsonObject>(api().deleteJsonBody(path, JsonObject().apply { addProperty("id", id) }))
            .let { if (it.isJsonObject) it.asJsonObject else JsonObject() }

    /** A picked file as one multipart part named [field]. */
    fun filePart(ctx: Context, uri: Uri, field: String): MultipartBody.Part {
        val cr = ctx.contentResolver
        val bytes = cr.openInputStream(uri)?.use { it.readBytes() } ?: throw ApiError("Could not read that file.")
        val mime = cr.getType(uri) ?: "application/octet-stream"
        val ext = android.webkit.MimeTypeMap.getSingleton().getExtensionFromMimeType(mime) ?: "bin"
        return MultipartBody.Part.createFormData(field, "upload.$ext", bytes.toRequestBody(mime.toMediaTypeOrNull()))
    }
    fun textPart(name: String, value: String): MultipartBody.Part = MultipartBody.Part.createFormData(name, value)

    suspend fun postParts(path: String, parts: List<MultipartBody.Part>): JsonObject =
        unwrap<JsonObject>(api().postParts(path, parts)).let { if (it.isJsonObject) it.asJsonObject else JsonObject() }
    suspend fun putParts(path: String, parts: List<MultipartBody.Part>): JsonObject =
        unwrap<JsonObject>(api().putParts(path, parts)).let { if (it.isJsonObject) it.asJsonObject else JsonObject() }
}

/** Small readers so the screens can say o.str("x") rather than null-checking Gson. */
fun JsonObject.str(k: String, def: String = ""): String =
    get(k)?.takeIf { !it.isJsonNull }?.let { if (it.isJsonPrimitive) it.asString else it.toString() } ?: def
fun JsonObject.bool(k: String): Boolean =
    get(k)?.takeIf { !it.isJsonNull && it.isJsonPrimitive }?.let {
        val p = it.asJsonPrimitive
        when { p.isBoolean -> p.asBoolean; p.isNumber -> p.asInt != 0; else -> p.asString in listOf("1", "true", "on", "yes") }
    } ?: false
fun JsonObject.int(k: String, def: Int = 0): Int =
    get(k)?.takeIf { !it.isJsonNull && it.isJsonPrimitive }?.let { try { it.asInt } catch (e: Exception) { it.asString.toIntOrNull() } } ?: def
