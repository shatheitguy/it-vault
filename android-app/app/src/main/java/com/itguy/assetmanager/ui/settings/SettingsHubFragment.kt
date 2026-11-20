package com.itguy.assetmanager.ui.settings

import android.os.Bundle
import android.view.Gravity
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.fragment.app.Fragment
import com.itguy.assetmanager.R
import com.itguy.assetmanager.ui.MainActivity

/**
 * Settings, as the web lays it out: one entry per section. "This phone" (the
 * app's own appearance, sync, updates and server) comes first; everything
 * after it is the server's settings, the same ones the web edits.
 */
class SettingsHubFragment : Fragment() {

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, s: Bundle?): View {
        val ctx = requireContext()
        val body = LinearLayout(ctx).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(ctx, 16f), dp(ctx, 6f), dp(ctx, 16f), dp(ctx, 96f))
        }
        val main = activity as? MainActivity
        body.addView(sectionTitle(ctx, "On this device"))
        body.addView(entry("This phone", "Appearance, offline sync, app updates, server", R.drawable.ic_settings) {
            main?.showFragment(SettingsFragment(), "This phone", addToBackStack = true)
        })
        body.addView(sectionTitle(ctx, "Server settings", "The same settings as the web app"))
        val (card, inner) = sectionCard(ctx)
        inner.setPadding(dp(ctx, 6f), dp(ctx, 6f), dp(ctx, 6f), dp(ctx, 6f))
        SettingsSections.all(ctx).forEachIndexed { i, sec ->
            if (i > 0) inner.addView(View(ctx).apply {
                setBackgroundColor(ctx.getColor(R.color.divider))
                layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(ctx, 1f)).also { it.leftMargin = dp(ctx, 64f) }
            })
            inner.addView(row(sec.title, sec.subtitle, sec.icon, sec.id == "danger") {
                main?.showFragment(SectionFragment.newInstance(sec.id), sec.title, addToBackStack = true)
            })
        }
        body.addView(card)
        body.addView(sectionTitle(ctx, "Data & alerts"))
        val (card2, inner2) = sectionCard(ctx)
        inner2.setPadding(dp(ctx, 6f), dp(ctx, 6f), dp(ctx, 6f), dp(ctx, 6f))
        MoreSections.all().filter { it.id != "catalog" }.forEachIndexed { i, sec ->
            if (i > 0) inner2.addView(View(ctx).apply {
                setBackgroundColor(ctx.getColor(R.color.divider))
                layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(ctx, 1f)).also { it.leftMargin = dp(ctx, 64f) }
            })
            inner2.addView(row(sec.title, sec.subtitle, sec.icon, false) {
                main?.showFragment(SectionFragment.newInstance(sec.id), sec.title, addToBackStack = true)
            })
        }
        body.addView(card2)
        return ScrollView(ctx).apply {
            setBackgroundColor(ctx.getColor(R.color.page)); clipToPadding = false
            addView(body)
        }
    }

    private fun entry(title: String, sub: String, icon: Int, go: () -> Unit): View {
        val ctx = requireContext()
        val (card, inner) = sectionCard(ctx)
        inner.setPadding(dp(ctx, 6f), dp(ctx, 6f), dp(ctx, 6f), dp(ctx, 6f))
        inner.addView(row(title, sub, icon, false, go))
        return card
    }

    private fun row(title: String, sub: String, icon: Int, danger: Boolean, go: () -> Unit): View {
        val ctx = requireContext()
        val accent = if (danger) ctx.getColor(R.color.stat_red)
            else com.itguy.assetmanager.data.Palette.serverColours()?.accent ?: ctx.getColor(R.color.accent)
        return LinearLayout(ctx).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(ctx, 12f), dp(ctx, 12f), dp(ctx, 12f), dp(ctx, 12f))
            isClickable = true; isFocusable = true
            setBackgroundResource(R.drawable.nav_item_bg)
            setOnClickListener { go() }
            val tile = android.widget.FrameLayout(ctx).apply {
                background = android.graphics.drawable.GradientDrawable().apply { cornerRadius = dp(ctx, 11f).toFloat(); setColor((accent and 0x00FFFFFF) or 0x24000000) }
                addView(ImageView(ctx).apply {
                    setImageResource(icon); imageTintList = android.content.res.ColorStateList.valueOf(accent)
                }, android.widget.FrameLayout.LayoutParams(dp(ctx, 20f), dp(ctx, 20f), Gravity.CENTER))
            }
            addView(tile, LinearLayout.LayoutParams(dp(ctx, 40f), dp(ctx, 40f)).also { it.rightMargin = dp(ctx, 14f) })
            addView(LinearLayout(ctx).apply {
                orientation = LinearLayout.VERTICAL
                addView(TextView(ctx).apply { text = title; textSize = 15.5f; setTypeface(typeface, android.graphics.Typeface.BOLD)
                    setTextColor(if (danger) accent else ctx.getColor(R.color.text_strong)) })
                addView(TextView(ctx).apply { text = sub; textSize = 12.5f; setTextColor(ctx.getColor(R.color.text_soft)) })
            }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(TextView(ctx).apply { text = "›"; textSize = 22f; setTextColor(ctx.getColor(R.color.text_soft)) })
        }
    }
}
