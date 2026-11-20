package com.itguy.assetmanager.ui.settings

import android.content.Context
import android.text.InputType
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.LinearLayout
import android.widget.TextView
import com.google.android.material.button.MaterialButton
import com.google.android.material.card.MaterialCardView
import com.google.android.material.materialswitch.MaterialSwitch
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout
import com.google.gson.JsonObject
import com.itguy.assetmanager.R
import com.itguy.assetmanager.data.bool
import com.itguy.assetmanager.data.str
import com.itguy.assetmanager.ui.widget.AppSpinner

/**
 * The settings engine.
 *
 * Every section of the web's Settings is, at heart, a few labelled fields
 * loaded from one endpoint and saved to another, with a test button or two.
 * Describing them as data -- rather than a layout file and a fragment each --
 * is what lets the phone carry all of them, and keeps them looking alike.
 */
sealed class Field {
    abstract val key: String
    /** kind: text | number | password | email | url | multiline | phone */
    data class Text(override val key: String, val label: String, val hint: String = "",
                    val kind: String = "text", val help: String = "") : Field()
    data class Toggle(override val key: String, val label: String, val help: String = "") : Field()
    data class Choice(override val key: String, val label: String,
                      val options: List<Pair<String, String>>, val help: String = "") : Field()
    data class Note(val text: String) : Field() { override val key = "" }
}

/** A button under a group's fields. [run] gets the form; its answer is shown under the card. */
data class Action(val label: String, val primary: Boolean = false, val confirm: String? = null,
                  val run: suspend (Form) -> String?)

/**
 * One card. [load] fills it; [save] (when set) is the main button. A group
 * can instead build its own content with [custom] -- the WhatsApp link, the
 * user list -- and still sit in the same card, with the same message line.
 */
data class Group(
    val title: String,
    val fields: List<Field> = emptyList(),
    val load: (suspend () -> JsonObject)? = null,
    val save: (suspend (Form) -> String?)? = null,
    val saveLabel: String = "Save",
    val actions: List<Action> = emptyList(),
    val custom: ((GroupHost) -> Unit)? = null,
    val subtitle: String = "",
)

data class Section(val id: String, val title: String, val subtitle: String, val icon: Int,
                   val adminOnly: Boolean = false, val groups: List<Group>)

/** What a custom group gets to draw into and talk through. */
interface GroupHost {
    val context: Context
    val body: LinearLayout
    fun say(msg: String?, ok: Boolean = true)
    fun launch(block: suspend () -> Unit)
    fun pickFile(mime: String, onPicked: (android.net.Uri) -> Unit)
    fun reload()
    /** Run [block] now and on every pull-to-refresh. */
    fun onRefresh(block: () -> Unit)
}

/** The live fields of one group: read them, fill them. */
class Form(val ctx: Context) {
    private val texts = linkedMapOf<String, Pair<Field.Text, TextInputEditText>>()
    private val toggles = linkedMapOf<String, MaterialSwitch>()
    private val choices = linkedMapOf<String, Pair<Field.Choice, AppSpinner>>()
    /** password fields that already have a value on the server */
    private val secretSet = mutableSetOf<String>()

    fun text(k: String) = texts[k]?.second?.text?.toString()?.trim().orEmpty()
    fun on(k: String) = toggles[k]?.isChecked ?: false
    fun choice(k: String): String = choices[k]?.let { (f, sp) -> f.options.getOrNull(sp.selectedItemPosition)?.first } ?: ""

    /** Everything as the server wants it. A password left empty is left out,
     *  so saving the other fields never blanks a stored secret. */
    fun values(): JsonObject = JsonObject().apply {
        texts.forEach { (k, p) ->
            val v = p.second.text?.toString()?.trim().orEmpty()
            when {
                p.first.kind == "password" && v.isEmpty() -> {}
                p.first.kind == "number" -> v.toIntOrNull()?.let { addProperty(k, it) } ?: addProperty(k, v)
                else -> addProperty(k, v)
            }
        }
        toggles.forEach { (k, s) -> addProperty(k, s.isChecked) }
        choices.forEach { (k, _) -> addProperty(k, choice(k)) }
    }

    fun fill(o: JsonObject) {
        texts.forEach { (k, p) ->
            if (p.first.kind == "password") {
                val set = o.bool("${k}_set") || o.bool(k.removeSuffix("_pass") + "_pass_set")
                if (set) secretSet.add(k)
                p.second.setText("")
                (p.second.parent?.parent as? TextInputLayout)?.placeholderText =
                    if (set) "Saved. Type a new one to change it" else ""
            } else if (o.has(k)) p.second.setText(o.str(k))
        }
        toggles.forEach { (k, s) -> if (o.has(k)) s.isChecked = o.bool(k) }
        choices.forEach { (k, p) ->
            if (o.has(k)) {
                val i = p.first.options.indexOfFirst { it.first == o.str(k) }
                if (i >= 0) p.second.setSelection(i)
            }
        }
    }

    // ---- building ----
    fun build(parent: LinearLayout, fields: List<Field>) {
        val inf = LayoutInflater.from(ctx)
        for (f in fields) when (f) {
            is Field.Text -> {
                val row = inf.inflate(R.layout.row_text, parent, false)
                row.findViewById<TextView>(R.id.rowLabel).text = f.label
                val input = row.findViewById<TextInputEditText>(R.id.rowInput)
                input.hint = f.hint
                input.inputType = when (f.kind) {
                    "number" -> InputType.TYPE_CLASS_NUMBER
                    "password" -> InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
                    "email" -> InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS
                    "url" -> InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
                    "phone" -> InputType.TYPE_CLASS_PHONE
                    "multiline" -> InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
                    else -> InputType.TYPE_CLASS_TEXT
                }
                if (f.kind == "password") row.findViewById<TextInputLayout>(R.id.rowBox).endIconMode = TextInputLayout.END_ICON_PASSWORD_TOGGLE
                if (f.kind == "multiline") { input.minLines = 3; input.gravity = android.view.Gravity.TOP }
                help(row, f.help)
                if (parent.childCount == 0) row.findViewById<TextView>(R.id.rowLabel).let {
                    (it.layoutParams as? ViewGroup.MarginLayoutParams)?.topMargin = 0
                }
                parent.addView(row); texts[f.key] = f to input
            }
            is Field.Toggle -> {
                val row = inf.inflate(R.layout.row_switch, parent, false)
                val sw = row.findViewById<MaterialSwitch>(R.id.rowSwitch); sw.text = f.label
                help(row, f.help); parent.addView(row); toggles[f.key] = sw
            }
            is Field.Choice -> {
                val row = inf.inflate(R.layout.row_choice, parent, false)
                row.findViewById<TextView>(R.id.rowLabel).text = f.label
                val sp = row.findViewById<AppSpinner>(R.id.rowChoice)
                sp.adapter = ArrayAdapter(ctx, android.R.layout.simple_spinner_dropdown_item, f.options.map { it.second })
                help(row, f.help); parent.addView(row); choices[f.key] = f to sp
            }
            is Field.Note -> parent.addView(TextView(ctx).apply {
                text = f.text; textSize = 13f
                setTextColor(ctx.getColor(R.color.text_soft))
                setPadding(0, dp(ctx, 4f), 0, dp(ctx, 6f))
            })
        }
    }

    private fun help(row: View, text: String) {
        if (text.isBlank()) return
        row.findViewById<TextView>(R.id.rowHelp)?.apply { this.text = text; visibility = View.VISIBLE }
    }
}

// ---- small view helpers shared by the settings screens ----
fun dp(ctx: Context, v: Float) = (v * ctx.resources.displayMetrics.density).toInt()

fun sectionCard(ctx: Context): Pair<MaterialCardView, LinearLayout> {
    val card = MaterialCardView(ctx).apply {
        radius = dp(ctx, 20f).toFloat()
        setCardBackgroundColor(ctx.getColor(R.color.card))
        strokeColor = ctx.getColor(R.color.card_line); strokeWidth = dp(ctx, 1f)
        cardElevation = 0f
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            .also { it.topMargin = dp(ctx, 8f) }
    }
    val inner = LinearLayout(ctx).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(ctx, 18f), dp(ctx, 16f), dp(ctx, 18f), dp(ctx, 18f))
    }
    card.addView(inner)
    return card to inner
}

fun sectionTitle(ctx: Context, text: String, sub: String = ""): View = LinearLayout(ctx).apply {
    orientation = LinearLayout.VERTICAL
    setPadding(dp(ctx, 4f), dp(ctx, 18f), dp(ctx, 4f), 0)
    addView(TextView(ctx).apply {
        this.text = text; textSize = 17f; setTypeface(typeface, android.graphics.Typeface.BOLD)
        setTextColor(ctx.getColor(R.color.text_strong))
    })
    if (sub.isNotBlank()) addView(TextView(ctx).apply {
        this.text = sub; textSize = 12.5f; setTextColor(ctx.getColor(R.color.text_soft))
        setPadding(0, dp(ctx, 2f), 0, 0)
    })
}

/** A button in the app's two pill styles: the main one, or the quiet one. */
fun pillButton(ctx: Context, label: String, primary: Boolean): MaterialButton {
    val style = if (primary) R.style.ButtonPill else R.style.ButtonPillQuiet
    return MaterialButton(android.view.ContextThemeWrapper(ctx, style), null, 0).apply {
        text = label; isAllCaps = false; textSize = 14f
        minHeight = dp(ctx, 44f); minimumHeight = dp(ctx, 44f)
        insetTop = 0; insetBottom = 0
        cornerRadius = dp(ctx, 12f)
        if (!primary) {
            val accent = com.itguy.assetmanager.data.Palette.serverColours()?.accent ?: ctx.getColor(R.color.accent)
            setTextColor(accent)
            backgroundTintList = android.content.res.ColorStateList.valueOf((accent and 0x00FFFFFF) or 0x1F000000)
        } else {
            val accent = com.itguy.assetmanager.data.Palette.serverColours()?.accent ?: ctx.getColor(R.color.accent)
            backgroundTintList = android.content.res.ColorStateList.valueOf(accent)
            setTextColor(if (androidx.core.graphics.ColorUtils.calculateLuminance(accent) > 0.55)
                android.graphics.Color.parseColor("#101828") else android.graphics.Color.WHITE)
        }
    }
}

/** A row of buttons that wraps onto a second line rather than squeezing. */
fun buttonRow(ctx: Context, buttons: List<View>): View {
    val flow = FlowRow(ctx, dp(ctx, 8f)).apply {
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            .also { it.topMargin = dp(ctx, 16f) }
    }
    buttons.forEach { flow.addView(it) }
    return flow
}

fun message(ctx: Context): TextView = TextView(ctx).apply {
    textSize = 13f; visibility = View.GONE
    setPadding(0, dp(ctx, 10f), 0, 0)
}
