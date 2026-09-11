package com.itguy.assetmanager.data

/**
 * Serialises everything currently held on the device -- the cached assets,
 * contracts and directory, plus any edits still waiting to sync -- into a
 * single portable XML document. This is what the "Export data as XML" button
 * hands to the Android file picker, so a snapshot can be saved to Downloads,
 * Drive, or shared off the phone even with no server in reach.
 *
 * Read-only: exporting never touches the server or the outbox.
 */
object XmlExport {

    fun build(): String {
        val assets = OfflineCache.loadAssets().orEmpty()
        val contracts = OfflineCache.loadContracts().orEmpty()
        val employees = OfflineCache.loadEmployees().orEmpty()
        val pending = SyncStore.all()

        val sb = StringBuilder()
        sb.append("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
        sb.append("<itvault exported=\"").append(esc(nowIso())).append("\" ")
            .append("pendingChanges=\"").append(pending.size).append("\">\n")

        sb.append("  <assets count=\"").append(assets.size).append("\">\n")
        for (a in assets) {
            sb.append("    <asset id=\"").append(esc(a.id ?: "")).append("\" updatedAt=\"").append(esc(a.updatedAt)).append("\">\n")
            tag(sb, "assetTag", a.AssetTag); tag(sb, "name", a.Name); tag(sb, "type", a.Type)
            tag(sb, "serial", a.Serial); tag(sb, "mac", a.MacAddress); tag(sb, "location", a.Location)
            tag(sb, "status", a.Status); tag(sb, "manufacturer", a.Manufacturer); tag(sb, "model", a.Model)
            tag(sb, "assignedTo", a.EmployeeID); tag(sb, "purchaseDate", a.PurchaseDate)
            tag(sb, "warrantyMonths", a.WarrantyMonths.toString()); tag(sb, "price", a.Price)
            tag(sb, "note", a.Note)
            sb.append("    </asset>\n")
        }
        sb.append("  </assets>\n")

        sb.append("  <contracts count=\"").append(contracts.size).append("\">\n")
        for (c in contracts) {
            sb.append("    <contract id=\"").append(c.id).append("\" updatedAt=\"").append(esc(c.updatedAt)).append("\">\n")
            tag(sb, "name", c.name); tag(sb, "vendor", c.vendor); tag(sb, "type", c.type)
            tag(sb, "startDate", c.start_date); tag(sb, "endDate", c.end_date)
            tag(sb, "cost", c.cost.toString()); tag(sb, "assignedTo", c.employee_id)
            tag(sb, "location", c.location); tag(sb, "department", c.department)
            tag(sb, "licenseKey", c.license_key); tag(sb, "note", c.note)
            sb.append("    </contract>\n")
        }
        sb.append("  </contracts>\n")

        sb.append("  <employees count=\"").append(employees.size).append("\">\n")
        for (e in employees) {
            sb.append("    <employee id=\"").append(esc(e.id ?: "")).append("\" updatedAt=\"").append(esc(e.updatedAt)).append("\">\n")
            tag(sb, "empCode", e.EmpCode); tag(sb, "employeeId", e.EmployeeID)
            tag(sb, "name", e.EmployeeName); tag(sb, "designation", e.Designation)
            tag(sb, "department", e.Department); tag(sb, "email", e.Email)
            sb.append("    </employee>\n")
        }
        sb.append("  </employees>\n")

        if (pending.isNotEmpty()) {
            sb.append("  <pendingChanges count=\"").append(pending.size).append("\">\n")
            for (op in pending) {
                sb.append("    <change entity=\"").append(esc(op.entity))
                    .append("\" op=\"").append(esc(op.op))
                    .append("\" serverId=\"").append(esc(op.serverId))
                    .append("\" editedAt=\"").append(op.editedAt).append("\"/>\n")
            }
            sb.append("  </pendingChanges>\n")
        }

        sb.append("</itvault>\n")
        return sb.toString()
    }

    fun suggestedFileName(): String {
        val ts = java.text.SimpleDateFormat("yyyyMMdd_HHmmss", java.util.Locale.US)
            .format(java.util.Date())
        return "itvault_export_$ts.xml"
    }

    private fun tag(sb: StringBuilder, name: String, value: String) {
        if (value.isBlank()) return
        sb.append("      <").append(name).append(">").append(esc(value))
            .append("</").append(name).append(">\n")
    }

    private fun nowIso(): String =
        java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", java.util.Locale.US)
            .format(java.util.Date())

    private fun esc(s: String): String = s
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace("\"", "&quot;")
}
