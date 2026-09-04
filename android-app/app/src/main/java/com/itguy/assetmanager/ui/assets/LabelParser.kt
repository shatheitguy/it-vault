package com.itguy.assetmanager.ui.assets

/**
 * Pulls Serial / Model / Manufacturer / MAC out of the raw OCR text of a
 * printed asset label.
 *
 * Kept as a pure function (no Android types) so the parsing rules can be
 * reasoned about and tested on their own, separately from the camera and the
 * form that consumes it.
 *
 * The earlier version only matched a label when a ":" or "-" separator
 * followed it, so extremely common real-world stickers were silently missed:
 *
 *     Serial No   ABC123        <- whitespace only, no separator
 *     S/N ABC123
 *     SN: ABC123  MAC: 00:11:22 <- two fields sharing one line
 *
 * so separators are optional here, a value may sit on the next line, and a
 * value stops before the next recognised label on the same line.
 */
object LabelParser {

    data class Result(
        val serial: String? = null,
        val model: String? = null,
        val manufacturer: String? = null,
        val mac: String? = null
    ) {
        val filledNames: List<String>
            get() = listOfNotNull(
                serial?.let { "Serial" }, model?.let { "Model" },
                manufacturer?.let { "Manufacturer" }, mac?.let { "MAC" }
            )
        val isEmpty: Boolean get() = filledNames.isEmpty()
    }

    // Longest-first within each group, so "serial number" wins over "serial"
    // and "model no" over "model" when both could match the same text.
    private val SERIAL_ALIASES = listOf(
        "serial number", "serial no.", "serial no", "serialno", "serial #", "serial#",
        "serial", "s/n no", "s/n", "s.n.", "s.n", "sn no", "sno", "sn"
    )
    private val MODEL_ALIASES = listOf(
        "model number", "model name", "model no.", "model no", "modelno",
        "model #", "model#", "model", "part number", "part no", "p/n", "mod."
    )
    private val MFR_ALIASES = listOf("manufacturer", "manufactured by", "brand", "make", "vendor")
    private val MAC_ALIASES = listOf("mac address", "mac addr", "mac id", "mac")

    private val ALL_ALIASES = (SERIAL_ALIASES + MODEL_ALIASES + MFR_ALIASES + MAC_ALIASES)
        .sortedByDescending { it.length }

    private val MAC_PATTERN = Regex("""([0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}""")

    /** A captured value is rejected if it's really just another label word
     * (e.g. "Model" sitting alone), or has no alphanumeric content at all. */
    private fun plausible(value: String): Boolean {
        val v = value.trim().trim(':', '-', '.', '=', '|', ',').trim()
        if (v.isEmpty()) return false
        if (!v.any { it.isLetterOrDigit() }) return false
        return ALL_ALIASES.none { it.equals(v, ignoreCase = true) }
    }

    private fun clean(value: String): String =
        value.trim().trim(':', '-', '.', '=', '|', ',').trim()

    /** Cuts a same-line value short when the NEXT recognised label starts on
     * that same line, so "SN: ABC123  MAC: .." doesn't swallow the MAC part. */
    private fun cutAtNextLabel(value: String): String {
        var cut = value.length
        for (alias in ALL_ALIASES) {
            val m = Regex("""(?i)\s+${Regex.escape(alias)}\b\.?\s*[:\-=]?""").find(value)
            if (m != null && m.range.first < cut) cut = m.range.first
        }
        return value.substring(0, cut)
    }

    /**
     * @param singleToken true for values that never contain spaces (serial,
     *   MAC) -- takes just the first whitespace-delimited token, which keeps a
     *   trailing "Rev A" or a second field off the end. Model and
     *   manufacturer legitimately contain spaces ("Latitude 5540"), so they
     *   take the rest of the line instead.
     */
    private fun findLabeled(lines: List<String>, aliases: List<String>, singleToken: Boolean): String? {
        val aliasPattern = aliases.joinToString("|") { Regex.escape(it) }
        // label, optional ".", optional separator, then the value -- the
        // separator being optional is the important part vs. the old version
        val sameLine = Regex("""(?i)(?:^|\s)($aliasPattern)\.?\s*[:\-=]?\s+(\S.*)$""")
        // ...and the no-space form, e.g. "SN:ABC123" or "S/N=ABC123"
        val glued = Regex("""(?i)(?:^|\s)($aliasPattern)\.?\s*[:\-=]\s*(\S.*)$""")

        for (line in lines) {
            // A line that IS just a label header ("Serial Number") must fall
            // through to the next-line lookup below. Without this the regex
            // backtracks to a shorter alias ("serial") and captures the rest
            // of the header itself as the value -- i.e. "Number".
            val bare = line.trim().trimEnd(':', '-', '=').trim()
            if (ALL_ALIASES.any { it.equals(bare, ignoreCase = true) }) continue
            for (re in listOf(sameLine, glued)) {
                val m = re.find(line) ?: continue
                var v = m.groupValues[2]
                v = if (singleToken) v.trim().split(Regex("\\s+")).first() else cutAtNextLabel(v)
                v = clean(v)
                if (plausible(v)) return v
            }
        }
        // label alone on its line, value on the line below
        for (i in lines.indices) {
            val norm = lines[i].trim().trimEnd(':', '-', '=').trim()
            if (aliases.any { it.equals(norm, ignoreCase = true) } && i + 1 < lines.size) {
                var v = lines[i + 1]
                v = if (singleToken) v.trim().split(Regex("\\s+")).first() else cutAtNextLabel(v)
                v = clean(v)
                if (plausible(v)) return v
            }
        }
        return null
    }

    fun parse(text: String): Result {
        val lines = text.lines().map { it.trim() }.filter { it.isNotBlank() }
        val serial = findLabeled(lines, SERIAL_ALIASES, singleToken = true)
        val model = findLabeled(lines, MODEL_ALIASES, singleToken = false)
        val mfr = findLabeled(lines, MFR_ALIASES, singleToken = false)
        // a bare MAC anywhere in the text is unambiguous enough to take even
        // when nothing labelled it
        val mac = findLabeled(lines, MAC_ALIASES, singleToken = true)
            ?: MAC_PATTERN.find(text)?.value
        return Result(serial = serial, model = model, manufacturer = mfr, mac = mac)
    }
}
