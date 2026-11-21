package com.itguy.assetmanager.ui.settings

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.FileProvider
import com.google.gson.JsonObject
import com.itguy.assetmanager.R
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.ApiError
import com.itguy.assetmanager.data.Looks
import com.itguy.assetmanager.data.Net
import com.itguy.assetmanager.data.Prefs
import com.itguy.assetmanager.data.bool
import com.itguy.assetmanager.data.int
import com.itguy.assetmanager.data.str
import com.itguy.assetmanager.ui.BrandDialog
import com.itguy.assetmanager.ui.Images
import com.itguy.assetmanager.ui.TypeIcons
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File

/**
 * The rest of the web app the phone did not have: the Product Catalog with
 * its pictures (brand logos fetched from the brand's site, product photos,
 * category icons), imports and exports, deleted contracts, and Heartbeat's
 * notification channels.
 */
object MoreSections {
    private fun isAdmin() = Prefs.role.equals("admin", true)

    fun all(): List<Section> = listOf(catalog(), data(), channels()).filter { !it.adminOnly || isAdmin() }
    fun byId(id: String) = all().firstOrNull { it.id == id }

    // ============================================================ Product Catalog
    private fun catalog() = Section("catalog", "Product Catalog", "Categories, brands, models and their pictures", R.drawable.ic_catalog, groups = listOf(
        Group("Item categories", subtitle = "Tap a category to choose its icon or give it a photo", custom = { h -> categories(h) }),
        Group("Brands", subtitle = "Give a brand its website and IT-Vault fetches its logo", custom = { h -> brands(h) }),
        Group("Models", subtitle = "A model's photo shows on every asset of that model", custom = { h -> models(h) }),
        Group("Contract types", custom = { h -> simpleList(h, "api/contract-types", "Contract type") }),
    ))

    private fun tile(ctx: Context, sizeDp: Float = 40f): Pair<android.widget.FrameLayout, Pair<ImageView, ImageView>> {
        val accent = com.itguy.assetmanager.data.Palette.serverColours()?.accent ?: ctx.getColor(R.color.accent)
        val fr = android.widget.FrameLayout(ctx)
        fr.background = android.graphics.drawable.GradientDrawable().apply { cornerRadius = dp(ctx, 11f).toFloat(); setColor((accent and 0x00FFFFFF) or 0x24000000) }
        val icon = ImageView(ctx).apply { imageTintList = android.content.res.ColorStateList.valueOf(accent) }
        val photo = ImageView(ctx).apply { scaleType = ImageView.ScaleType.FIT_CENTER; setPadding(dp(ctx, 3f), dp(ctx, 3f), dp(ctx, 3f), dp(ctx, 3f)); visibility = View.GONE }
        fr.addView(icon, android.widget.FrameLayout.LayoutParams(dp(ctx, sizeDp * 0.5f), dp(ctx, sizeDp * 0.5f), android.view.Gravity.CENTER))
        fr.addView(photo, android.widget.FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        fr.layoutParams = LinearLayout.LayoutParams(dp(ctx, sizeDp), dp(ctx, sizeDp)).also { it.rightMargin = dp(ctx, 12f) }
        return fr to (icon to photo)
    }

    private fun showPicture(fr: android.widget.FrameLayout, icon: ImageView, photo: ImageView, url: String?) {
        Images.load(photo, url?.ifBlank { null }, 200) { shown ->
            photo.visibility = if (shown) View.VISIBLE else View.GONE
            icon.visibility = if (shown) View.GONE else View.VISIBLE
            if (shown) (fr.background as? android.graphics.drawable.GradientDrawable)?.setColor(android.graphics.Color.WHITE)
        }
    }

    private fun listRow(ctx: Context, lead: View, title: String, sub: String, onTap: () -> Unit, onDelete: (() -> Unit)?): View {
        val row = LinearLayout(ctx).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = android.view.Gravity.CENTER_VERTICAL
            setPadding(0, dp(ctx, 8f), 0, dp(ctx, 8f))
            isClickable = true; isFocusable = true; setBackgroundResource(R.drawable.nav_item_bg)
            setOnClickListener { onTap() }
        }
        row.addView(lead)
        row.addView(LinearLayout(ctx).apply {
            orientation = LinearLayout.VERTICAL
            addView(TextView(ctx).apply { text = title; textSize = 15f; setTextColor(ctx.getColor(R.color.text_strong)) })
            if (sub.isNotBlank()) addView(TextView(ctx).apply { text = sub; textSize = 12f; setTextColor(ctx.getColor(R.color.text_soft)) })
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        if (onDelete != null) row.addView(TextView(ctx).apply {
            text = "Delete"; textSize = 13f; setTextColor(ctx.getColor(R.color.stat_red))
            setPadding(dp(ctx, 12f), dp(ctx, 10f), dp(ctx, 4f), dp(ctx, 10f))
            setOnClickListener { onDelete() }
        })
        return row
    }

    private fun confirmDelete(h: GroupHost, what: String, go: suspend () -> Unit) {
        BrandDialog(h.context).setTitle("Delete $what?").setMessage("Assets keep the name they already have.")
            .setPositiveButton("Delete") { _, _ -> h.launch { go(); h.say("Deleted"); h.reload() } }
            .setNegativeButton("Cancel", null).show()
    }

    /** Add a name (and, for brands, a website). */
    private fun addDialog(h: GroupHost, title: String, fields: List<Field>, go: suspend (Form) -> Unit) {
        val ctx = h.context
        val box = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(ctx, 22f), dp(ctx, 8f), dp(ctx, 22f), 0) }
        val form = Form(ctx); form.build(box, fields)
        BrandDialog(ctx).setTitle(title).setView(box)
            .setPositiveButton("Add") { _, _ -> h.launch { go(form); h.reload() } }
            .setNegativeButton("Cancel", null).show()
    }

    /** The picture dialog for a brand or model: upload, link, (brand) website. */
    private fun pictureDialog(h: GroupHost, kind: String, ref: String, title: String, current: String, website: String) {
        val ctx = h.context
        val box = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(ctx, 22f), dp(ctx, 8f), dp(ctx, 22f), 0) }
        val prev = ImageView(ctx).apply { scaleType = ImageView.ScaleType.FIT_CENTER
            background = android.graphics.drawable.GradientDrawable().apply { cornerRadius = dp(ctx, 16f).toFloat(); setColor(android.graphics.Color.WHITE) }
            layoutParams = LinearLayout.LayoutParams(dp(ctx, 96f), dp(ctx, 96f)).also { it.bottomMargin = dp(ctx, 8f) } }
        if (current.isNotBlank()) { box.addView(prev); Images.load(prev, current, 300) }
        val form = Form(ctx)
        val fields = mutableListOf<Field>()
        if (kind == "brand") fields += Field.Text("website", "Brand website", "dell.com", kind = "url", help = "IT-Vault finds the logo on the site.")
        fields += Field.Text("url", "Or a link to a picture", "https://…/picture.png", kind = "url")
        form.build(box, fields)
        if (kind == "brand") form.fill(JsonObject().apply { addProperty("website", website.removePrefix("https://").removePrefix("http://")) })
        val d = BrandDialog(ctx).setTitle(title).setView(box)
            .setPositiveButton(if (kind == "brand") "Get logo" else "Use link") { _, _ -> h.launch {
                val o = JsonObject()
                if (kind == "brand" && form.text("website").isNotBlank() && form.text("url").isBlank()) o.addProperty("website", form.text("website"))
                else o.addProperty("url", form.text("url"))
                h.say(if (o.has("website")) "Looking for the logo…" else "Fetching the picture…")
                Net.post("api/img/$kind/$ref", o); Looks.refresh(); h.say("Picture saved"); h.reload() } }
            .setNeutralButton("Upload") { _, _ -> h.pickFile("image/*") { uri -> h.launch {
                Net.postParts("api/img/$kind/$ref", listOf(Net.filePart(ctx, uri, "photo"))); Looks.refresh(); h.say("Picture saved"); h.reload() } } }
        if (current.isNotBlank()) d.setNegativeButton("Remove") { _, _ -> h.launch {
            Net.delete("api/img/$kind/$ref"); Looks.refresh(); h.say("Picture removed"); h.reload() } }
        else d.setNegativeButton("Cancel", null)
        d.show()
    }

    private fun categories(h: GroupHost) {
        val ctx = h.context
        val list = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL }
        val add = pillButton(ctx, "Add category", true)
        h.body.addView(list); h.body.addView(buttonRow(ctx, listOf(add)))
        add.setOnClickListener { addDialog(h, "New category", listOf(Field.Text("name", "Name", "e.g. Laptop"))) { f ->
            val o = JsonObject(); o.addProperty("name", f.text("name")); Net.post("api/categories", o); h.say("Added") } }
        h.onRefresh { h.launch {
            val cats = Net.getArray("api/categories")
            list.removeAllViews()
            cats.forEach { e -> val c = e.asJsonObject
                val (fr, iv) = tile(ctx); iv.first.setImageResource(TypeIcons.forType(c.str("name")))
                showPicture(fr, iv.first, iv.second, c.str("photo"))
                list.addView(listRow(ctx, fr, c.str("name"), if (c.str("photo").isNotBlank()) "Photo" else if (c.str("icon").isNotBlank()) "Icon: ${c.str("icon")}" else "Icon chosen from the name",
                    onTap = { categoryLook(h, c) },
                    onDelete = { confirmDelete(h, c.str("name")) { Net.deleteWithId("api/categories", c.int("id")) } }))
            }
        } }
    }

    private val ICONS = listOf("" to "Automatic, from the name", "laptop" to "Laptop", "desktop" to "Desktop", "monitor" to "Monitor",
        "smartphone" to "Phone", "tablet" to "Tablet", "router" to "Router", "switch" to "Switch", "wifi" to "Access point",
        "shield" to "Firewall", "server" to "Server", "drive" to "Storage", "camera" to "Camera", "printer" to "Printer",
        "headphones" to "Headset", "battery" to "UPS / battery", "keyboard" to "Keyboard", "projector" to "Projector", "box" to "Other")

    private fun categoryLook(h: GroupHost, c: JsonObject) {
        val ctx = h.context
        val box = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(ctx, 22f), dp(ctx, 8f), dp(ctx, 22f), 0) }
        val form = Form(ctx); form.build(box, listOf(Field.Choice("icon", "Icon", ICONS)))
        form.fill(JsonObject().apply { addProperty("icon", c.str("icon")) })
        val id = c.int("id")
        val d = BrandDialog(ctx).setTitle(c.str("name")).setView(box)
            .setPositiveButton("Save icon") { _, _ -> h.launch {
                val o = JsonObject(); o.addProperty("icon", form.choice("icon")); Net.post("api/categories/$id/look", o); h.say("Saved"); h.reload() } }
            .setNeutralButton(if (c.str("photo").isBlank()) "Upload photo" else "Replace photo") { _, _ -> h.pickFile("image/*") { uri -> h.launch {
                Net.postParts("api/categories/$id/look", listOf(Net.filePart(ctx, uri, "photo"))); h.say("Photo saved"); h.reload() } } }
        if (c.str("photo").isNotBlank()) d.setNegativeButton("Remove photo") { _, _ -> h.launch { Net.delete("api/categories/$id/look"); h.say("Photo removed"); h.reload() } }
        else d.setNegativeButton("Cancel", null)
        d.show()
    }

    private fun brands(h: GroupHost) {
        val ctx = h.context
        val list = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL }
        val add = pillButton(ctx, "Add brand", true)
        h.body.addView(list); h.body.addView(buttonRow(ctx, listOf(add)))
        add.setOnClickListener { addDialog(h, "New brand", listOf(Field.Text("name", "Name", "e.g. Dell"),
            Field.Text("website", "Website (optional, for the logo)", "dell.com", kind = "url"))) { f ->
            val o = JsonObject(); o.addProperty("name", f.text("name")); o.addProperty("website", f.text("website"))
            if (f.text("website").isNotBlank()) h.say("Adding, and fetching the logo…")
            val r = Net.post("api/manufacturers", o); Looks.refresh()
            h.say(if (r.str("logo_error").isNotBlank()) "Added. No logo: ${r.str("logo_error")}" else if (r.str("logo").isNotBlank()) "Added with its logo" else "Added") } }
        h.onRefresh { h.launch {
            val ms = Net.getArray("api/manufacturers")
            list.removeAllViews()
            ms.forEach { e -> val m = e.asJsonObject
                val (fr, iv) = tile(ctx); iv.first.setImageResource(R.drawable.ic_tag)
                showPicture(fr, iv.first, iv.second, m.str("logo"))
                list.addView(listRow(ctx, fr, m.str("name"), m.str("website").removePrefix("https://").removePrefix("http://"),
                    onTap = { pictureDialog(h, "brand", m.str("id"), "${m.str("name")} logo", m.str("logo"), m.str("website")) },
                    onDelete = { confirmDelete(h, m.str("name")) { Net.deleteWithId("api/manufacturers", m.int("id")) } }))
            }
        } }
    }

    private fun models(h: GroupHost) {
        val ctx = h.context
        val list = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL }
        val add = pillButton(ctx, "Add model", true)
        h.body.addView(list); h.body.addView(buttonRow(ctx, listOf(add)))
        var brandOpts = listOf<Pair<String, String>>()
        add.setOnClickListener { addDialog(h, "New model", listOf(Field.Choice("manufacturer_id", "Brand", brandOpts), Field.Text("name", "Model", "e.g. Latitude 5440"))) { f ->
            val o = JsonObject(); o.addProperty("name", f.text("name")); o.addProperty("manufacturer_id", f.choice("manufacturer_id").toIntOrNull())
            Net.post("api/models", o); h.say("Added") } }
        h.onRefresh { h.launch {
            brandOpts = Net.getArray("api/manufacturers").map { it.asJsonObject.let { m -> m.str("id") to m.str("name") } }
            val ms = Net.getArray("api/models")
            list.removeAllViews()
            ms.forEach { e -> val m = e.asJsonObject
                val (fr, iv) = tile(ctx); iv.first.setImageResource(R.drawable.ic_t_image)
                showPicture(fr, iv.first, iv.second, m.str("photo"))
                list.addView(listRow(ctx, fr, m.str("name"), m.str("manufacturer"),
                    onTap = { pictureDialog(h, "model", m.str("id"), "${m.str("manufacturer")} ${m.str("name")}".trim(), m.str("photo"), "") },
                    onDelete = { confirmDelete(h, m.str("name")) { Net.deleteWithId("api/models", m.int("id")) } }))
            }
        } }
    }

    private fun simpleList(h: GroupHost, path: String, noun: String) {
        val ctx = h.context
        val list = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL }
        val add = pillButton(ctx, "Add ${noun.lowercase()}", true)
        h.body.addView(list); h.body.addView(buttonRow(ctx, listOf(add)))
        add.setOnClickListener { addDialog(h, "New ${noun.lowercase()}", listOf(Field.Text("name", "Name"))) { f ->
            val o = JsonObject(); o.addProperty("name", f.text("name")); Net.post(path, o); h.say("Added") } }
        h.onRefresh { h.launch {
            val xs = Net.getArray(path); list.removeAllViews()
            xs.forEach { e -> val x = e.asJsonObject
                val (fr, iv) = tile(ctx); iv.first.setImageResource(R.drawable.ic_doc)
                list.addView(listRow(ctx, fr, x.str("name"), "", onTap = {}, onDelete = { confirmDelete(h, x.str("name")) { Net.deleteWithId(path, x.int("id")) } }))
            }
        } }
    }

    // ============================================================ Import, export & trash
    private fun data() = Section("data", "Import, export & trash", "Excel in and out, deleted contracts", R.drawable.ic_backup, groups = listOf(
        Group("Assets", subtitle = "Excel (.xlsx) or CSV with the same columns as the export", custom = { h ->
            ioButtons(h, "api/export", "assets.xlsx", "api/import", byDepartment = true) }),
        Group("Contracts", custom = { h -> ioButtons(h, "api/contracts/export", "contracts.xlsx", "api/contracts/import") }),
        Group("Directory", subtitle = "Import staff from a sheet", custom = { h -> ioButtons(h, null, "", "api/directory/import") }),
        Group("Product Catalog", subtitle = "Columns: Category, Manufacturer, Model", custom = { h -> ioButtons(h, null, "", "api/catalog/import") }),
        Group("Deleted contracts", custom = { h -> contractTrash(h) }),
    ))

    private suspend fun download(ctx: Context, path: String, name: String): File = withContext(Dispatchers.IO) {
        val client = OkHttpClient.Builder().addInterceptor { c ->
            val r = c.request().newBuilder(); if (Prefs.apiKey.isNotBlank()) r.header("X-Api-Key", Prefs.apiKey); c.proceed(r.build()) }.build()
        client.newCall(Request.Builder().url(ApiClient.absolute(path)).build()).execute().use { resp ->
            if (!resp.isSuccessful) throw ApiError("The server said ${resp.code}.")
            val dir = File(ctx.cacheDir, "downloads").apply { mkdirs() }
            File(dir, name).also { f -> f.outputStream().use { o -> resp.body?.byteStream()?.copyTo(o) } }
        }
    }

    // Which department an asset export or import is for: every one (export
    // only), or one. With a single department there is nothing to ask.
    private fun pickDepartment(h: GroupHost, forImport: Boolean, onPicked: (Int?) -> Unit) = h.launch {
        val all = Net.getArray("api/spaces").map { it.asJsonObject }
        val choices = if (forImport) all.filter { !it.has("can_edit") || it.bool("can_edit") } else all
        if (all.size < 2 || choices.isEmpty()) { onPicked(null); return@launch }
        val labels = (if (forImport) emptyList() else listOf("All departments")) + choices.map { "${it.str("name")}  (${it.str("prefix")}-…)" }
        BrandDialog(h.context).setTitle(if (forImport) "Import into which department?" else "Export which department?")
            .setItems(labels.toTypedArray()) { _, which ->
                if (!forImport && which == 0) onPicked(null) else onPicked(choices[which - (if (forImport) 0 else 1)].int("id"))
            }.setNegativeButton("Cancel", null).show()
    }

    private fun ioButtons(h: GroupHost, exportPath: String?, exportName: String, importPath: String, byDepartment: Boolean = false) {
        val ctx = h.context
        val btns = mutableListOf<View>()
        if (exportPath != null) btns += pillButton(ctx, "Export", false).apply { setOnClickListener {
            if (byDepartment) pickDepartment(h, false) { sid -> exportNow(h, exportPath + (sid?.let { "?space=$it" } ?: ""), exportName) }
            else exportNow(h, exportPath, exportName) } }
        btns += pillButton(ctx, "Import from a file", true).apply { setOnClickListener {
            if (byDepartment) pickDepartment(h, true) { sid -> importNow(h, importPath, sid) } else importNow(h, importPath, null) } }
        h.body.addView(buttonRow(ctx, btns))
    }

    private fun exportNow(h: GroupHost, exportPath: String, exportName: String) {
        val ctx = h.context
        h.launch {
            val f = download(ctx, exportPath, exportName)
            val uri = FileProvider.getUriForFile(ctx, ctx.packageName + ".fileprovider", f)
            ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply {
                type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                putExtra(Intent.EXTRA_STREAM, uri); addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }, "Save or send $exportName").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            h.say("Exported $exportName") }
    }

    private fun importNow(h: GroupHost, importPath: String, space: Int?) {
        val ctx = h.context
        h.pickFile("*/*") { uri -> h.launch {
            h.say("Importing…")
            val parts = listOf(Net.filePart(ctx, uri, "file")) + (space?.let { listOf(Net.textPart("space", it.toString())) } ?: emptyList())
            val r = Net.postParts(importPath, parts)
            h.say(r.str("message").ifBlank {
                listOf("added" to r.int("added", -1), "updated" to r.int("updated", -1), "imported" to r.int("imported", -1), "skipped" to r.int("skipped", -1),
                       "need a required field" to r.int("incomplete", -1))
                    .filter { it.second > 0 || (it.second == 0 && it.first == "added") }.joinToString(", ") { "${it.second} ${it.first}" }.ifBlank { "Imported" } }) } }
    }

    private fun contractTrash(h: GroupHost) {
        val ctx = h.context
        val list = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL }
        val empty = pillButton(ctx, "Empty trash", false)
        h.body.addView(list); h.body.addView(buttonRow(ctx, listOf(empty)))
        empty.setOnClickListener { BrandDialog(ctx).setTitle("Empty contract trash?").setMessage("Deleted contracts are removed for good.")
            .setPositiveButton("Empty") { _, _ -> h.launch { Net.post("api/contracts/trash/empty"); h.say("Emptied"); h.reload() } }
            .setNegativeButton("Cancel", null).show() }
        h.onRefresh { h.launch {
            val xs = Net.getArray("api/contracts/trash"); list.removeAllViews()
            if (xs.size() == 0) list.addView(TextView(ctx).apply { text = "Nothing deleted."; textSize = 13.5f; setTextColor(ctx.getColor(R.color.text_soft)) })
            empty.visibility = if (xs.size() == 0) View.GONE else View.VISIBLE
            xs.forEach { e -> val c = e.asJsonObject
                val (fr, iv) = tile(ctx); iv.first.setImageResource(R.drawable.ic_doc)
                list.addView(listRow(ctx, fr, c.str("name"), listOf(c.str("contract_tag"), c.str("vendor")).filter { it.isNotBlank() }.joinToString(" · "),
                    onTap = { BrandDialog(ctx).setTitle(c.str("name")).setMessage("Restore this contract?")
                        .setPositiveButton("Restore") { _, _ -> h.launch { Net.post("api/contracts/${c.int("id")}/restore"); h.say("Restored"); h.reload() } }
                        .setNegativeButton("Cancel", null).show() },
                    onDelete = { BrandDialog(ctx).setTitle("Delete ${c.str("name")} for good?").setMessage("This cannot be undone.")
                        .setPositiveButton("Delete") { _, _ -> h.launch { Net.delete("api/contracts/${c.int("id")}/permanent"); h.say("Deleted"); h.reload() } }
                        .setNegativeButton("Cancel", null).show() }))
            }
        } }
    }

    // ============================================================ Heartbeat channels
    private val KINDS = listOf("email" to "Email (uses your SMTP settings)", "webhook" to "Webhook (JSON POST)",
                               "slack" to "Slack incoming webhook", "telegram" to "Telegram bot")

    private fun channels() = Section("channels", "Notification channels", "Where alerts are delivered", R.drawable.ic_bell, adminOnly = true, groups = listOf(
        Group("Channels", subtitle = "Asset events, tickets, SLA breaches, backups and Heartbeat outages go to every active channel", custom = { h -> channelList(h) }),
    ))

    private fun channelEditor(h: GroupHost, ch: JsonObject?) {
        val ctx = h.context
        val box = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(ctx, 22f), dp(ctx, 8f), dp(ctx, 22f), 0) }
        val form = Form(ctx)
        form.build(box, listOf(
            Field.Text("name", "Name", "e.g. IT team email"), Field.Choice("kind", "Type", KINDS),
            Field.Text("to", "Send to (email)", "it@company.com, oncall@company.com"),
            Field.Text("url", "Webhook / Slack URL", "https://…", kind = "url"),
            Field.Text("token", "Telegram bot token"), Field.Text("chat_id", "Telegram chat id"),
            Field.Toggle("enabled", "Active")))
        val cfg = ch?.getAsJsonObject("config") ?: JsonObject()
        form.fill(JsonObject().apply {
            addProperty("name", ch?.str("name") ?: ""); addProperty("kind", ch?.str("kind") ?: "email")
            addProperty("to", cfg.str("to")); addProperty("url", cfg.str("url")); addProperty("token", cfg.str("token"))
            addProperty("chat_id", cfg.str("chat_id")); addProperty("enabled", ch?.bool("enabled") ?: true) })
        BrandDialog(ctx).setTitle(if (ch == null) "Add a channel" else "Edit ${ch.str("name")}").setView(android.widget.ScrollView(ctx).apply { addView(box) })
            .setPositiveButton("Save") { _, _ -> h.launch {
                val kind = form.choice("kind")
                val c = JsonObject()
                when (kind) {
                    "email" -> c.addProperty("to", form.text("to"))
                    "webhook", "slack" -> c.addProperty("url", form.text("url"))
                    "telegram" -> { c.addProperty("token", form.text("token")); c.addProperty("chat_id", form.text("chat_id")) }
                }
                val o = JsonObject(); o.addProperty("name", form.text("name")); o.addProperty("kind", kind)
                o.add("config", c); o.addProperty("enabled", form.on("enabled"))
                if (ch == null) Net.post("api/heartbeat/channels", o) else Net.put("api/heartbeat/channels/${ch.int("id")}", o)
                h.say("Saved"); h.reload() } }
            .setNegativeButton("Cancel", null).show()
    }

    private fun channelList(h: GroupHost) {
        val ctx = h.context
        val list = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL }
        val add = pillButton(ctx, "Add a channel", true)
        h.body.addView(list); h.body.addView(buttonRow(ctx, listOf(add)))
        add.setOnClickListener { channelEditor(h, null) }
        h.onRefresh { h.launch {
            val xs = Net.getArray("api/heartbeat/channels"); list.removeAllViews()
            if (xs.size() == 0) list.addView(TextView(ctx).apply { text = "No channels yet: notifications go to users who have an email on their profile."
                textSize = 13.5f; setTextColor(ctx.getColor(R.color.text_soft)) })
            xs.forEach { e -> val c = e.asJsonObject
                val (fr, iv) = tile(ctx); iv.first.setImageResource(R.drawable.ic_bell)
                val where = c.getAsJsonObject("config")?.let { it.str("to").ifBlank { it.str("url") }.ifBlank { it.str("chat_id") } } ?: ""
                val row = listRow(ctx, fr, c.str("name"), "${c.str("kind")} · ${if (c.bool("enabled")) "active" else "paused"}${if (where.isNotBlank()) " · $where" else ""}",
                    onTap = { BrandDialog(ctx).setTitle(c.str("name")).setItems(arrayOf("Send a test", "Edit", "Delete")) { _, which ->
                        when (which) {
                            0 -> h.launch { val r = Net.post("api/heartbeat/channels/${c.int("id")}/test"); h.say(r.str("message", "Test sent")) }
                            1 -> channelEditor(h, c)
                            2 -> h.launch { Net.delete("api/heartbeat/channels/${c.int("id")}"); h.say("Deleted"); h.reload() }
                        } }.show() },
                    onDelete = null)
                list.addView(row)
            }
        } }
    }
}
