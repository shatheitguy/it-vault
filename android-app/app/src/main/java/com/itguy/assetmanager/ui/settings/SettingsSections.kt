package com.itguy.assetmanager.ui.settings

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import com.google.gson.JsonObject
import com.itguy.assetmanager.R
import com.itguy.assetmanager.data.ApiError
import com.itguy.assetmanager.data.Net
import com.itguy.assetmanager.data.Prefs
import com.itguy.assetmanager.data.bool
import com.itguy.assetmanager.data.int
import com.itguy.assetmanager.data.str
import com.itguy.assetmanager.ui.BrandDialog
import com.itguy.assetmanager.ui.Images

/**
 * Every Settings section of the web app, for the phone. The order and the
 * names follow the web's Settings menu, so the two can be used side by side.
 */
object SettingsSections {

    private suspend fun settings(): JsonObject = Net.get("api/settings")
    /** Saves just these keys; the server leaves every other setting alone. */
    private suspend fun saveKeys(f: Form, vararg keys: String): String? {
        val all = f.values(); val o = JsonObject()
        keys.forEach { k -> all.get(k)?.let { o.add(k, it) } }
        Net.put("api/settings", o); return "Saved"
    }
    private val MODES = listOf("system" to "System (follows the device)", "light" to "Always light", "dark" to "Always dark")
    private fun isAdmin() = Prefs.role.equals("admin", true)

    fun all(ctx: Context): List<Section> = listOf(
        general(), account(), users(), notifications(), sla(), database(), ldap(), unifi(),
        branding(), customization(), label(), danger()
    ).filter { !it.adminOnly || isAdmin() }

    fun byId(ctx: Context, id: String) = all(ctx).firstOrNull { it.id == id }

    // ------------------------------------------------------------ General
    private fun general() = Section("general", "General", "Organisation, public address, version", R.drawable.ic_settings, groups = listOf(
        Group("Organisation", listOf(
            Field.Text("app_name", "Organisation name", "e.g. Al Wasl Group"),
            Field.Text("company_phone", "Company phone", kind = "phone"),
            Field.Text("company_address", "Company address", kind = "multiline"),
            Field.Text("currency", "Currency", "AED"),
            Field.Text("region", "Region", "UAE"),
        ), load = { settings() }, save = { saveKeys(it, "app_name", "company_phone", "company_address", "currency", "region") }),
        Group("Public address", listOf(
            Field.Text("public_url", "Address people open links on", "http://192.168.0.206:5000", kind = "url",
                help = "Every link sent by email and WhatsApp starts with this. Leave empty to use the address this server is reached on."),
        ), load = { Net.get("api/settings/public-url") },
           save = { f -> val o = JsonObject(); o.addProperty("public_url", f.text("public_url"))
                    val r = Net.post("api/settings/public-url", o)
                    if (r.bool("local_only")) "Saved. Note: that address only works on this server itself" else "Saved" }),
        Group("Server", custom = { h ->
            val t = infoText(h.context); h.body.addView(t)
            h.onRefresh { h.launch { val v = Net.get("api/version")
                t.text = "IT-Vault ${v.str("version")} · " + (if (v.bool("is_docker")) "running in Docker" else "installed from source") +
                    "\nUpdate the server from the web app: Settings › General › Check for updates." } }
        }),
    ))

    // ------------------------------------------------------------ My account
    private fun account() = Section("account", "My account", "Photo, name, mobile, password, 2FA", R.drawable.ic_people, groups = listOf(
        Group("Profile photo", custom = { h -> avatarBox(h) }),
        Group("Details", listOf(
            Field.Text("display", "Display name"),
            Field.Text("email", "Email", kind = "email"),
            Field.Text("phone", "Mobile (for WhatsApp sign-in codes)", "050 123 4567", kind = "phone"),
            Field.Text("password", "Current password", kind = "password",
                help = "Only needed when you change your email or mobile."),
        ), load = { Net.get("api/profile") },
           save = { f -> val o = JsonObject()
                    listOf("display", "email", "phone").forEach { o.addProperty(it, f.text(it)) }
                    if (f.text("password").isNotBlank()) o.addProperty("password", f.text("password"))
                    Net.put("api/profile", o); "Saved" }),
        Group("Password", listOf(
            Field.Text("old", "Current password", kind = "password"),
            Field.Text("new", "New password", kind = "password", help = "At least 8 characters."),
        ), save = { f -> val o = JsonObject(); o.addProperty("old", f.text("old")); o.addProperty("new", f.text("new"))
                    Net.post("api/profile", o); "Password changed" }, saveLabel = "Change password"),
        Group("Two-factor sign-in", custom = { h -> twoFactor(h) }),
    ))

    // ------------------------------------------------------------ Users
    private fun users() = Section("users", "Users & roles", "Who can sign in, and what they can do", R.drawable.ic_people, adminOnly = true, groups = listOf(
        Group("Users", custom = { h -> userList(h) }),
    ))

    // ------------------------------------------------------------ Notifications
    private fun notifications() = Section("notify", "Notifications", "Email, WhatsApp, what to send", R.drawable.ic_bell, groups = listOf(
        Group("Email (SMTP)", listOf(
            Field.Text("smtp_host", "SMTP server", "smtp.office365.com"),
            Field.Text("smtp_port", "Port", "587", kind = "number"),
            Field.Text("smtp_user", "Username"),
            Field.Text("smtp_pass", "Password / app password", kind = "password"),
            Field.Text("smtp_from", "From address", kind = "email"),
        ), load = { settings() }, save = { saveKeys(it, "smtp_host", "smtp_port", "smtp_user", "smtp_pass", "smtp_from") },
           actions = listOf(Action("Send test email") { f -> Net.post("api/settings/smtp-test", f.values()).str("message", "Test email sent") })),
        Group("WhatsApp", subtitle = "Send sign links and signed copies from the company's WhatsApp", custom = { h -> whatsApp(h) }),
        Group("Notify me about", custom = { h -> notifyTypes(h) }),
    ))

    // ------------------------------------------------------------ SLA & automation
    private fun sla() = Section("sla", "SLA & automation", "Ticket deadlines, assignment, portal", R.drawable.ic_heartbeat, groups = listOf(
        Group("Hours to resolve, by priority", listOf(
            Field.Text("sla_urgent", "Urgent", kind = "number"), Field.Text("sla_high", "High", kind = "number"),
            Field.Text("sla_normal", "Normal", kind = "number"), Field.Text("sla_low", "Low", kind = "number"),
            Field.Toggle("sla_breach_notify", "Tell IT when a ticket misses its deadline"),
            Field.Toggle("auto_assign_roundrobin", "Share new tickets out in turn between IT staff"),
        ), load = { settings() }, save = { saveKeys(it, "sla_urgent", "sla_high", "sla_normal", "sla_low", "sla_breach_notify", "auto_assign_roundrobin") }),
        Group("Ticket portal", listOf(
            Field.Text("portal_token", "Portal access code",
                help = "Optional. When set, the portal link only works with this code, so only your staff can raise tickets."),
        ), load = { settings() }, save = { saveKeys(it, "portal_token") },
           actions = listOf(Action("Copy portal link") { f ->
               val url = Net.get("api/portal/link").str("url")
               (f.ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("Portal", url))
               "Copied: $url" })),
    ))

    // ------------------------------------------------------------ Database / LDAP / UniFi
    private fun database() = Section("database", "Database", "Where IT-Vault keeps its data", R.drawable.ic_backup, adminOnly = true, groups = listOf(
        Group("MariaDB / MySQL", listOf(
            Field.Note("Changing these moves IT-Vault to another database. Test first."),
            Field.Text("db_host", "Host"), Field.Text("db_port", "Port", kind = "number"),
            Field.Text("db_name", "Database"), Field.Text("db_user", "User"), Field.Text("db_pass", "Password", kind = "password"),
        ), load = { settings() }, save = { saveKeys(it, "db_host", "db_port", "db_name", "db_user", "db_pass") },
           actions = listOf(Action("Test connection") { f -> Net.post("api/test-db", f.values()).str("message", "Connected") })),
    ))

    private fun ldap() = Section("ldap", "LDAP / Active Directory", "Import staff from the directory", R.drawable.ic_people, groups = listOf(
        Group("Directory server", listOf(
            Field.Text("ldap_server", "Server", "ldap://dc01.company.local"), Field.Text("ldap_domain", "Domain", "company.local"),
            Field.Text("ldap_bind_user", "Bind user"), Field.Text("ldap_bind_pass", "Bind password", kind = "password"),
            Field.Text("ldap_base_dn", "Base DN", "DC=company,DC=local"),
        ), load = { settings() }, save = { saveKeys(it, "ldap_server", "ldap_domain", "ldap_bind_user", "ldap_bind_pass", "ldap_base_dn") },
           actions = listOf(
               Action("Test") { f -> Net.post("api/test-ldap", f.values()).str("message", "Connected") },
               Action("Sync directory now", confirm = "Import and update staff from the directory now?") {
                   val r = Net.post("api/employees/ldap-sync"); r.str("message").ifBlank { "Synced: ${r.int("added")} added, ${r.int("updated")} updated" } })),
    ))

    private fun unifi() = Section("unifi", "UniFi controller", "Network devices and clients", R.drawable.ic_wifi, groups = listOf(
        Group("Controller", listOf(
            Field.Toggle("unifi_enabled", "Use UniFi"),
            Field.Text("unifi_host", "Host"), Field.Text("unifi_port", "Port", kind = "number"),
            Field.Text("unifi_site", "Site", "default"), Field.Text("unifi_user", "User"),
            Field.Text("unifi_pass", "Password", kind = "password"),
            Field.Toggle("unifi_is_os", "UniFi OS (Cloud Key Gen2, UDM)"),
            Field.Toggle("unifi_verify_ssl", "Check the controller's certificate"),
        ), load = { settings() }, save = { saveKeys(it, "unifi_enabled", "unifi_host", "unifi_port", "unifi_site", "unifi_user", "unifi_pass", "unifi_is_os", "unifi_verify_ssl") },
           actions = listOf(Action("Test") { f -> Net.post("api/test-unifi", f.values()).str("message", "Connected") })),
    ))

    // ------------------------------------------------------------ Branding
    private fun branding() = Section("branding", "Branding", "Logo, letterhead, Returned watermark", R.drawable.ic_tag, groups = listOf(
        Group("Name & logo", listOf(
            Field.Text("app_name", "Organisation name"), Field.Text("logo_text", "Logo text (sidebar)"),
        ), load = { settings() }, save = { saveKeys(it, "app_name", "logo_text") }, custom = { h -> logoBox(h) }),
        Group("Letterhead", subtitle = "Printed sheets and PDFs use it as their header", custom = { h -> letterheadBox(h) }),
        Group("Returned assets", listOf(
            Field.Text("text", "Watermark text", "RETURNED"),
            Field.Text("color", "Colour", "#d32f2f"),
            Field.Text("opacity", "Opacity (5 to 100)", kind = "number"),
            Field.Toggle("send", "Send the returned copy to the employee and IT"),
            Field.Text("auto_days", "Make Available again after (days, 0 = never)", kind = "number"),
        ), load = { Net.get("api/settings/return-watermark") },
           save = { f -> Net.post("api/settings/return-watermark", f.values()); "Saved" }),
    ))

    // ------------------------------------------------------------ Customization
    private fun customization() = Section("custom", "Customization", "Light & dark, colours", R.drawable.ic_settings, groups = listOf(
        Group("Light & dark", listOf(
            Field.Choice("ui_mode", "The app", MODES),
            Field.Choice("sign_mode", "Acknowledgement pages", MODES),
            Field.Choice("portal_mode", "Ticket portal", MODES),
        ), load = { Net.get("api/settings/modes") },
           save = { f -> Net.post("api/settings/modes", f.values()); "Saved. The phone follows it under This phone › Appearance › Same as web" }),
        Group("Colours", listOf(
            Field.Text("accent", "Accent colour", "#f1ff2e"), Field.Text("accent2", "Second colour", "#bdbf2b"),
            Field.Text("radius", "Corner roundness (px)", kind = "number"),
        ), load = { settings() }, save = { saveKeys(it, "accent", "accent2", "radius") }),
    ))

    // ------------------------------------------------------------ Asset label
    private fun label() = Section("label", "Asset label", "What the printed QR tag shows", R.drawable.ic_tag, groups = listOf(
        Group("Label", listOf(
            Field.Choice("label_size", "Label size", listOf("50.8x50.8" to "Square 5.08 × 5.08 cm", "50.8x25.4" to "Rectangle 5.08 × 2.54 cm")),
            Field.Text("label_caption", "Caption", "Asset No."),
            Field.Text("label_color", "Text colour", "#000000"),
            Field.Toggle("label_logo", "Show the logo"),
            Field.Choice("label_logo_size", "Logo size", listOf("sm" to "Small", "md" to "Default", "lg" to "Large", "xl" to "Extra large")),
            Field.Toggle("label_show_name", "Show the asset name"),
            Field.Toggle("label_show_asset", "Show the asset ID"),
            Field.Toggle("label_show_contact", "Show the company phone"),
            Field.Text("qr_size", "QR size (px)", kind = "number"),
            Field.Text("qr_fields", "QR card fields", "Name,AssetID,Type,Serial,Status,Location"),
        ), load = { settings() }, save = { saveKeys(it, "label_size", "label_caption", "label_color", "label_logo", "label_logo_size",
                                                     "label_show_name", "label_show_asset", "label_show_contact", "qr_size", "qr_fields") }),
    ))

    // ------------------------------------------------------------ Danger zone
    private fun danger() = Section("danger", "Danger zone", "Wipe everything", R.drawable.ic_trash, adminOnly = true, groups = listOf(
        Group("Wipe everything", listOf(
            Field.Note("Deletes every asset, ticket, contract, employee and user, and starts IT-Vault from the setup wizard. A full backup is taken first."),
            Field.Text("password", "Your password", kind = "password"),
            Field.Text("confirm", "Type WIPE EVERYTHING", "WIPE EVERYTHING"),
        ), actions = listOf(Action("Wipe everything", confirm = "This deletes all data on the server. Continue?") { f ->
            val o = JsonObject(); o.addProperty("password", f.text("password")); o.addProperty("confirm", f.text("confirm"))
            val r = Net.post("api/admin/wipe", o); "Wiped. Backup: ${r.str("backup_file")}" })),
    ))

    // ================================================================ custom groups

    private fun infoText(ctx: Context) = TextView(ctx).apply {
        textSize = 13.5f; setTextColor(ctx.getColor(R.color.text_soft)); setLineSpacing(0f, 1.15f)
    }

    private fun picture(ctx: Context, sizeDp: Float): ImageView = ImageView(ctx).apply {
        scaleType = ImageView.ScaleType.FIT_CENTER
        background = android.graphics.drawable.GradientDrawable().apply { cornerRadius = dp(ctx, 14f).toFloat(); setColor(ctx.getColor(R.color.divider)) }
        clipToOutline = true
        layoutParams = LinearLayout.LayoutParams(dp(ctx, sizeDp), dp(ctx, sizeDp)).also { it.rightMargin = dp(ctx, 14f) }
    }

    private fun row(ctx: Context, vararg v: View) = LinearLayout(ctx).apply {
        orientation = LinearLayout.HORIZONTAL; gravity = android.view.Gravity.CENTER_VERTICAL
        v.forEach { addView(it) }
    }

    private fun avatarBox(h: GroupHost) {
        val ctx = h.context
        val img = picture(ctx, 76f)
        val note = infoText(ctx)
        val up = pillButton(ctx, "Upload photo", false)
        val col = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL; addView(note); addView(up) }
        h.body.addView(row(ctx, img, col))
        h.onRefresh { h.launch {
            val p = Net.get("api/me")
            val url = p.str("avatar")
            note.text = if (url.isBlank()) "No photo yet." else "Shown beside your name."
            Images.load(img, url.ifBlank { null }, 256)
        } }
        up.setOnClickListener { h.pickFile("image/*") { uri -> h.launch {
            Net.postParts("api/profile/avatar", listOf(Net.filePart(ctx, uri, "avatar"))); h.say("Photo saved"); h.reload()
        } } }
    }

    private fun twoFactor(h: GroupHost) {
        val ctx = h.context
        val status = infoText(ctx)
        h.body.addView(status)
        val totpOn = pillButton(ctx, "Set up authenticator app", false)
        val totpOff = pillButton(ctx, "Turn off authenticator", false)
        val codesOn = pillButton(ctx, "Turn on sign-in codes", false)
        val codesOff = pillButton(ctx, "Turn off sign-in codes", false)
        h.body.addView(buttonRow(ctx, listOf(totpOn, totpOff, codesOn, codesOff)))
        h.onRefresh { h.launch {
            val s = Net.get("api/2fa/status")
            val totp = s.bool("totp_enabled"); val codes = s.bool("email_otp_enabled")
            val targets = s.getAsJsonArray("code_targets")?.joinToString(" and ") { it.asString } ?: ""
            status.text = "Authenticator app: " + (if (totp) "on" else "off") +
                "\nSign-in codes: " + (if (codes) "on" + (if (targets.isNotBlank()) ", sent to $targets" else "") else "off") +
                "\nCodes go to your email and, when WhatsApp is linked, your mobile."
            totpOn.visibility = if (totp) View.GONE else View.VISIBLE; totpOff.visibility = if (totp) View.VISIBLE else View.GONE
            codesOn.visibility = if (codes) View.GONE else View.VISIBLE; codesOff.visibility = if (codes) View.VISIBLE else View.GONE
        } }
        totpOn.setOnClickListener { h.launch {
            val r = Net.post("api/2fa/totp/setup")
            val box = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(ctx, 22f), dp(ctx, 8f), dp(ctx, 22f), 0) }
            QrSvg.render(r.str("qr_svg"), dp(ctx, 220f))?.let { bmp ->
                box.addView(ImageView(ctx).apply { setImageBitmap(bmp); layoutParams = LinearLayout.LayoutParams(dp(ctx, 220f), dp(ctx, 220f)).also { it.gravity = android.view.Gravity.CENTER_HORIZONTAL } })
            }
            box.addView(infoText(ctx).apply { text = "Scan it in your authenticator app, or tap \"Open in app\" on this phone. Key: ${r.str("secret")}"; setTextIsSelectable(true) })
            val form = Form(ctx); form.build(box, listOf(Field.Text("code", "6-digit code from the app", kind = "number")))
            BrandDialog(ctx).setTitle("Authenticator app").setView(box)
                .setNeutralButton("Open in app") { _, _ ->
                    try { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(r.str("otpauth_url")))) } catch (e: Exception) { h.say("No authenticator app on this phone", false) }
                }
                .setPositiveButton("Turn on") { _, _ -> h.launch {
                    val o = JsonObject(); o.addProperty("code", form.text("code")); Net.post("api/2fa/totp/confirm", o)
                    h.say("Authenticator app is on"); h.reload() } }
                .setNegativeButton("Cancel", null).show()
        } }
        totpOff.setOnClickListener { h.launch { Net.post("api/2fa/totp/disable"); h.say("Authenticator app turned off"); h.reload() } }
        codesOn.setOnClickListener { h.launch {
            val r = Net.post("api/2fa/email-otp/enable")
            val box = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(ctx, 22f), dp(ctx, 8f), dp(ctx, 22f), 0) }
            box.addView(infoText(ctx).apply { text = "A code was sent to ${r.str("sent_to", "you")}. Type it here to turn sign-in codes on." })
            val form = Form(ctx); form.build(box, listOf(Field.Text("code", "Code", kind = "number")))
            BrandDialog(ctx).setTitle("Sign-in codes").setView(box)
                .setPositiveButton("Turn on") { _, _ -> h.launch {
                    val o = JsonObject(); o.addProperty("code", form.text("code")); Net.post("api/2fa/email-otp/confirm", o)
                    h.say("Sign-in codes are on"); h.reload() } }
                .setNegativeButton("Cancel", null).show()
        } }
        codesOff.setOnClickListener { h.launch { Net.post("api/2fa/email-otp/disable"); h.say("Sign-in codes turned off"); h.reload() } }
    }

    private fun userList(h: GroupHost) {
        val ctx = h.context
        val list = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL }
        val add = pillButton(ctx, "Add user", true)
        h.body.addView(list); h.body.addView(buttonRow(ctx, listOf(add)))
        var roles = listOf("admin" to "Admin", "read-write" to "Read & write", "read-only" to "Read only")
        fun editor(u: JsonObject?) {
            val box = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(ctx, 22f), dp(ctx, 8f), dp(ctx, 22f), 0) }
            val form = Form(ctx)
            val fields = mutableListOf<Field>()
            if (u == null) fields += Field.Text("username", "Username")
            fields += listOf(Field.Text("display", "Display name"), Field.Text("email", "Email", kind = "email"),
                             Field.Choice("role", "Role", roles),
                             Field.Text("password", if (u == null) "Password" else "New password (leave empty to keep)", kind = "password"))
            form.build(box, fields); u?.let { form.fill(it) }
            BrandDialog(ctx).setTitle(if (u == null) "Add user" else "Edit ${u.str("username")}").setView(android.widget.ScrollView(ctx).apply { addView(box) })
                .setPositiveButton("Save") { _, _ -> h.launch {
                    val o = form.values()
                    if (u == null) Net.post("api/users", o) else Net.put("api/users/${Uri.encode(u.str("username"))}", o)
                    h.say("Saved"); h.reload() } }
                .setNegativeButton("Cancel", null).show()
        }
        add.setOnClickListener { editor(null) }
        h.onRefresh { h.launch {
            val rs = try { Net.getArray("api/roles") } catch (e: Exception) { null }
            if (rs != null) roles = listOf("admin" to "Admin", "read-write" to "Read & write", "read-only" to "Read only") +
                rs.mapNotNull { it.asJsonObject?.str("name")?.takeIf { n -> n.isNotBlank() }?.let { n -> n to n } }
            val users = Net.getArray("api/users")
            list.removeAllViews()
            users.forEach { e ->
                val u = e.asJsonObject
                val t = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL; layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f) }
                t.addView(TextView(ctx).apply { text = u.str("display").ifBlank { u.str("username") }; textSize = 15f
                    setTextColor(ctx.getColor(R.color.text_strong)); setTypeface(typeface, android.graphics.Typeface.BOLD) })
                t.addView(TextView(ctx).apply { textSize = 12.5f; setTextColor(ctx.getColor(R.color.text_soft))
                    text = listOf(u.str("username"), u.str("role"), u.str("email")).filter { it.isNotBlank() }.joinToString(" · ") +
                        (if (u.bool("totp_enabled") || u.bool("email_otp_enabled")) " · 2FA" else "") })
                val edit = pillButton(ctx, "Edit", false).apply { setOnClickListener { editor(u) } }
                val del = pillButton(ctx, "Delete", false).apply {
                    setOnClickListener {
                        BrandDialog(ctx).setTitle("Delete ${u.str("username")}?").setMessage("They can no longer sign in.")
                            .setPositiveButton("Delete") { _, _ -> h.launch { Net.delete("api/users/${Uri.encode(u.str("username"))}"); h.say("Deleted"); h.reload() } }
                            .setNegativeButton("Cancel", null).show()
                    }
                    (layoutParams as? ViewGroup.MarginLayoutParams)
                }
                val r = row(ctx, t, edit, del).apply { setPadding(0, dp(ctx, 10f), 0, dp(ctx, 10f)) }
                (del.layoutParams as? LinearLayout.LayoutParams)?.leftMargin = dp(ctx, 6f)
                list.addView(r)
            }
        } }
    }

    private fun whatsApp(h: GroupHost) {
        val ctx = h.context
        val status = infoText(ctx)
        val qr = ImageView(ctx).apply { visibility = View.GONE
            layoutParams = LinearLayout.LayoutParams(dp(ctx, 220f), dp(ctx, 220f)).also { it.gravity = android.view.Gravity.CENTER_HORIZONTAL; it.topMargin = dp(ctx, 10f) } }
        val link = pillButton(ctx, "Link WhatsApp", true); val unlink = pillButton(ctx, "Unlink", false)
        h.body.addView(status); h.body.addView(qr); h.body.addView(buttonRow(ctx, listOf(link, unlink)))
        val form = Form(ctx)
        val fieldsBox = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL; setPadding(0, dp(ctx, 8f), 0, 0) }
        form.build(fieldsBox, listOf(
            Field.Text("country_code", "Default country code", "971", kind = "number"),
            Field.Toggle("send_link", "Send the acknowledgement link on WhatsApp"),
            Field.Toggle("send_pdf", "Send the signed PDF copy on WhatsApp"),
            Field.Text("sender_name", "Sender name", help = "Every message starts with this name."),
            Field.Text("number", "Send a test message to", "050 123 4567", kind = "phone"),
        ))
        h.body.addView(fieldsBox)
        val banner = picture(ctx, 120f).apply { layoutParams = LinearLayout.LayoutParams(dp(ctx, 160f), dp(ctx, 80f)).also { it.topMargin = dp(ctx, 12f) } }
        val save = pillButton(ctx, "Save WhatsApp", true); val test = pillButton(ctx, "Send test", false)
        val bUp = pillButton(ctx, "Upload banner", false); val bRm = pillButton(ctx, "Remove banner", false)
        h.body.addView(banner); h.body.addView(buttonRow(ctx, listOf(save, test, bUp, bRm)))
        var poll = false
        fun paint(s: JsonObject) {
            val st = s.str("status")
            status.text = when (st) {
                "on", "open", "connected" -> "Linked as +${s.str("me")}"
                "qr" -> "Scan this code with WhatsApp on the company phone: Settings › Linked devices › Link a device."
                "starting", "connecting" -> "Starting…"
                "unavailable" -> "Not available on this server: ${s.str("error")}"
                else -> "Not linked."
            }
            val svg = s.str("qr_svg")
            if (st == "qr" && svg.isNotBlank()) QrSvg.render(svg, dp(ctx, 220f))?.let { qr.setImageBitmap(it); qr.visibility = View.VISIBLE } else qr.visibility = View.GONE
            link.visibility = if (st in listOf("on", "open", "connected")) View.GONE else View.VISIBLE
            unlink.visibility = if (st in listOf("on", "open", "connected")) View.VISIBLE else View.GONE
            val hasBanner = s.str("banner").isNotBlank()
            banner.visibility = if (hasBanner) View.VISIBLE else View.GONE
            Images.load(banner, s.str("banner").ifBlank { null }, 400)
            bRm.visibility = if (hasBanner) View.VISIBLE else View.GONE
            bUp.text = if (hasBanner) "Replace banner" else "Add banner picture"
        }
        h.onRefresh { h.launch { val s = Net.get("api/whatsapp/status"); paint(s); form.fill(s) } }
        link.setOnClickListener { h.launch {
            paint(Net.post("api/whatsapp/link")); poll = true
            // the code refreshes every ~20 s and the link happens on the other phone: follow it for two minutes
            repeat(40) { if (!poll) return@repeat; kotlinx.coroutines.delay(3000)
                val s = Net.get("api/whatsapp/status"); paint(s); if (s.str("status") !in listOf("qr", "starting", "connecting")) poll = false }
        } }
        unlink.setOnClickListener { h.launch { Net.post("api/whatsapp/unlink"); h.say("Unlinked"); h.reload() } }
        save.setOnClickListener { h.launch { Net.post("api/whatsapp/settings", form.values()); h.say("Saved") } }
        test.setOnClickListener { h.launch { val o = JsonObject(); o.addProperty("number", form.text("number"))
            Net.post("api/whatsapp/test", o); h.say("Test message sent") } }
        bUp.setOnClickListener { h.pickFile("image/*") { uri -> h.launch {
            Net.postParts("api/whatsapp/banner", listOf(Net.filePart(ctx, uri, "banner"))); h.say("Banner saved"); h.reload() } } }
        bRm.setOnClickListener { h.launch { Net.delete("api/whatsapp/banner"); h.say("Banner removed"); h.reload() } }
    }

    private fun notifyTypes(h: GroupHost) {
        val ctx = h.context
        val box = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL }
        val save = pillButton(ctx, "Save", true)
        h.body.addView(box); h.body.addView(buttonRow(ctx, listOf(save)))
        val switches = linkedMapOf<String, com.google.android.material.materialswitch.MaterialSwitch>()
        h.onRefresh { h.launch {
            val s = Net.get("api/settings")
            val on = s.getAsJsonObject("notify_types") ?: JsonObject()
            box.removeAllViews(); switches.clear()
            s.getAsJsonArray("notify_catalog")?.forEach { e ->
                val o = e.asJsonObject; val key = o.str("key")
                val row = android.view.LayoutInflater.from(ctx).inflate(R.layout.row_switch, box, false)
                val sw = row.findViewById<com.google.android.material.materialswitch.MaterialSwitch>(R.id.rowSwitch)
                sw.text = o.str("label"); sw.isChecked = on.bool(key)
                box.addView(row); switches[key] = sw
            }
        } }
        save.setOnClickListener { h.launch {
            val types = JsonObject(); switches.forEach { (k, sw) -> types.addProperty(k, sw.isChecked) }
            val o = JsonObject(); o.add("notify_types", types); Net.put("api/settings", o); h.say("Saved") } }
    }

    private fun logoBox(h: GroupHost) {
        val ctx = h.context
        val img = picture(ctx, 76f)
        val up = pillButton(ctx, "Upload logo", false); val rm = pillButton(ctx, "Remove logo", false)
        h.body.addView(row(ctx, img, LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL; addView(up); addView(rm) }))
        h.onRefresh { Images.load(img, "/logo.png?t=${System.currentTimeMillis() / 60000}", 256) }
        up.setOnClickListener { h.pickFile("image/*") { uri -> h.launch {
            Net.putParts("api/settings", listOf(Net.filePart(ctx, uri, "logo"))); h.say("Logo saved"); h.reload() } } }
        rm.setOnClickListener { h.launch { Net.putParts("api/settings", listOf(Net.textPart("remove_logo", "1"))); h.say("Logo removed"); h.reload() } }
    }

    private fun letterheadBox(h: GroupHost) {
        val ctx = h.context
        val note = infoText(ctx)
        val up = pillButton(ctx, "Upload letterhead", true); val rm = pillButton(ctx, "Remove", false)
        h.body.addView(note); h.body.addView(buttonRow(ctx, listOf(up, rm)))
        h.onRefresh { h.launch { val s = Net.get("api/settings")
            val has = s.bool("has_letterhead")
            note.text = if (has) "A letterhead is set." else "No letterhead: printouts use the plain logo bar."
            rm.visibility = if (has) View.VISIBLE else View.GONE } }
        up.setOnClickListener { h.pickFile("*/*") { uri -> h.launch {
            Net.putParts("api/settings", listOf(Net.filePart(ctx, uri, "letterhead"))); h.say("Letterhead saved"); h.reload() } } }
        rm.setOnClickListener { h.launch { Net.putParts("api/settings", listOf(Net.textPart("remove_letterhead", "1"))); h.say("Letterhead removed"); h.reload() } }
    }
}
