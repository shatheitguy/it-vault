package com.itguy.assetmanager.data

import com.itguy.assetmanager.data.model.Asset
import com.itguy.assetmanager.data.model.CatalogLooks

/**
 * What picture each asset shows, by the same rule as the web:
 *
 *   its own photo  >  its model's photo (Product Catalog)  >  the type icon
 *
 * and its brand's logo as a small badge on the corner.
 *
 * The map of URLs comes from /api/catalog/looks in one small request and is
 * kept in the offline cache, so the list keeps its pictures with no signal
 * (the images themselves are cached by [com.itguy.assetmanager.ui.Images]).
 */
object Looks {
    @Volatile private var current: CatalogLooks? = null

    private fun now(): CatalogLooks = current ?: (OfflineCache.loadLooks() ?: CatalogLooks()).also { current = it }

    /** Asks the server for the latest map. True when anything changed. */
    suspend fun refresh(): Boolean = try {
        val r = ApiClient.api().catalogLooks()
        val body = r.body()
        if (r.isSuccessful && body != null) {
            val changed = body != current
            current = body
            OfflineCache.saveLooks(body)
            changed
        } else false
    } catch (e: Exception) { false }

    /** The asset's photo, or its model's: a server path, or null for "use the icon". */
    fun pictureFor(a: Asset): String? {
        val l = now()
        a.id?.let { id -> l.assets?.get(id)?.let { return it } }
        if (a.Model.isNotBlank()) {
            val models = l.models ?: return null
            val key = (a.Manufacturer + "|" + a.Model).lowercase()
            return models[key] ?: models[("|" + a.Model).lowercase()]
        }
        return null
    }

    /** Where the picture comes from, for the asset form's note. */
    fun sourceOf(a: Asset): String? = when {
        a.id != null && now().assets?.containsKey(a.id) == true -> "asset"
        pictureFor(a) != null -> "model"
        else -> null
    }

    fun brandLogo(a: Asset): String? =
        a.Manufacturer.takeIf { it.isNotBlank() }?.let { now().brands?.get(it) }

    /** After an upload/removal, before the next refresh lands. */
    fun setAssetPhoto(id: String, url: String?) {
        val l = now()
        val m = (l.assets ?: emptyMap()).toMutableMap()
        if (url == null) m.remove(id) else m[id] = url
        current = l.copy(assets = m)
        OfflineCache.saveLooks(current!!)
    }
}
