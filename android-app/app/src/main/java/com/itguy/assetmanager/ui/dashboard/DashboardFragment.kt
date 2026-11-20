package com.itguy.assetmanager.ui.dashboard

import android.graphics.Color
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.NetworkUtils
import com.itguy.assetmanager.data.OfflineCache
import com.itguy.assetmanager.databinding.FragmentDashboardBinding
import com.itguy.assetmanager.ui.MainActivity
import com.itguy.assetmanager.ui.Refreshable
import com.itguy.assetmanager.ui.assets.AssetEditFragment
import com.itguy.assetmanager.ui.tickets.TicketDetailFragment
import kotlinx.coroutines.launch

/** Mirrors the web app's Dashboard exactly: KPI row, then the same five
 * widgets in the same order (Asset Status, Top Asset Types, Recent Assets,
 * Open Tickets, Recent Activity), each pulling live from the server. */
class DashboardFragment : Fragment(), Refreshable, com.itguy.assetmanager.ui.Rebranded {

    /** The hero's ink is worked out from the card's own colour, so it has
     *  to be worked out again once that colour is the server's. */
    override fun onPaletteApplied() {
        if (_b != null) styleHero()
    }

    private var _b: FragmentDashboardBinding? = null
    private val b get() = _b!!

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        _b = FragmentDashboardBinding.inflate(inflater, container, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        b.statTotal.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statLabel).text = "TOTAL ASSETS"
        b.statOut.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statLabel).text = "CHECKED OUT"
        b.statMaint.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statLabel).text = "MAINTENANCE"
        b.statDue.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statLabel).text = "DUE SOON"
        b.statWarr.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statLabel).text = "WARRANTY ≤30D"
        // One colour per role, as on the web. Five numbers all painted in the
        // accent read as one number repeated; the colour is what says which
        // of them is the one to worry about.
        listOf(
            b.statTotal to com.itguy.assetmanager.R.color.accent,
            b.statOut to com.itguy.assetmanager.R.color.stat_cyan,
            b.statMaint to com.itguy.assetmanager.R.color.stat_green,
            b.statDue to com.itguy.assetmanager.R.color.stat_amber,
            b.statWarr to com.itguy.assetmanager.R.color.stat_red,
        ).forEach { (card, colour) ->
            // The dot carries the colour now, not the figure. Five numbers in
            // five colours is a chart nobody asked for; five black numbers
            // with a coloured dot beside each is a list you can read.
            val tint = androidx.core.content.ContextCompat.getColor(requireContext(), colour)
            card.root.findViewById<View>(com.itguy.assetmanager.R.id.statDot)
                .backgroundTintList = android.content.res.ColorStateList.valueOf(tint)
        }
        paintGreeting()
        styleHero()
        wireSeeAll()
        refresh()
    }

    /**
     * "See all" goes to the screen that owns the list.
     *
     * The dashboard shows four of each; every one of these lists has a screen
     * of its own, and sending people there beats growing the dashboard until
     * it is a report.
     */
    private fun wireSeeAll() {
        val main = activity as? MainActivity
        // the hero's three buttons: what people open the app to do
        b.dashAddAsset.setOnClickListener {
            main?.showFragment(AssetEditFragment.newInstance(null), "Add Asset", addToBackStack = true)
        }
        b.dashNewTicket.setOnClickListener {
            main?.showFragment(com.itguy.assetmanager.ui.tickets.TicketsListFragment.newInstance(openNew = true),
                               "Tickets", addToBackStack = true)
        }
        b.dashScan.visibility = if (com.itguy.assetmanager.data.Prefs.role.equals("read-only", true)) View.GONE else View.VISIBLE
        b.dashScan.setOnClickListener {
            main?.showFragment(com.itguy.assetmanager.ui.scan.NetworkScanFragment(), "Network Scan", addToBackStack = true)
        }
        b.seeAllAssets.setOnClickListener {
            main?.showFragment(com.itguy.assetmanager.ui.assets.AssetsListFragment(),
                               "Assets", addToBackStack = true)
        }
        b.seeAllTickets.setOnClickListener {
            main?.showFragment(com.itguy.assetmanager.ui.tickets.TicketsListFragment(),
                               "Tickets", addToBackStack = true)
        }
        b.seeAllActivity.setOnClickListener {
            main?.showFragment(
                com.itguy.assetmanager.ui.generic.GenericListFragment.newInstance(
                    com.itguy.assetmanager.ui.generic.ListKind.AUDIT),
                "Audit Log", addToBackStack = true)
        }
        b.seeAllContracts.setOnClickListener {
            main?.showFragment(com.itguy.assetmanager.ui.contracts.ContractsListFragment(),
                               "Contracts", addToBackStack = true)
        }
    }

    /** The date and who is looking, as the reference's header does it. */
    private fun paintGreeting() {
        val now = java.util.Date()
        b.dashDate.text = java.text.SimpleDateFormat("d MMMM, yyyy", java.util.Locale.getDefault())
            .format(now)
        val who = com.itguy.assetmanager.data.Prefs.displayName
            .ifBlank { com.itguy.assetmanager.data.Prefs.username }
            .substringBefore(' ')
            .replaceFirstChar { it.uppercase() }
        val hour = java.util.Calendar.getInstance().get(java.util.Calendar.HOUR_OF_DAY)
        val part = when (hour) {
            in 0..11 -> "Good morning"
            in 12..16 -> "Good afternoon"
            else -> "Good evening"
        }
        b.dashGreeting.text = if (who.isBlank()) "Overview" else "$part, $who!"
    }

    /** The ring sits on the accent card, so its track has to be a washed-out
     *  version of whatever that card is -- not a grey that would look like
     *  dirt on a red or a green. */
    private fun styleHero() = b.heroCard.post {
        val bb = _b ?: return@post
        val ctx = requireContext()
        val accent = com.itguy.assetmanager.data.Palette.serverColours()?.accent
            ?: androidx.core.content.ContextCompat.getColor(ctx, com.itguy.assetmanager.R.color.accent)
        val strong = androidx.core.content.ContextCompat.getColor(ctx, com.itguy.assetmanager.R.color.text_strong)
        val track = androidx.core.content.ContextCompat.getColor(ctx, com.itguy.assetmanager.R.color.divider)
        // the web's band: the card, with the accent glowing in from a corner
        bb.heroInner.background = android.graphics.drawable.GradientDrawable().apply {
            gradientType = android.graphics.drawable.GradientDrawable.RADIAL_GRADIENT
            gradientRadius = bb.heroInner.width.coerceAtLeast(1) * 0.9f
            setGradientCenter(0f, 0f)
            colors = intArrayOf((accent and 0x00FFFFFF) or 0x2E000000, 0x00000000)
        }
        bb.heroRing.setColors(accent, track, strong)
    }

    /** "18  with staff": the number bold, the words quiet. */
    private fun figure(n: Int, words: String): CharSequence {
        val num = n.toString()
        return android.text.SpannableString("$num  $words").apply {
            setSpan(android.text.style.StyleSpan(android.graphics.Typeface.BOLD), 0, num.length, 0)
            setSpan(android.text.style.RelativeSizeSpan(1.3f), 0, num.length, 0)
            setSpan(android.text.style.ForegroundColorSpan(
                resources.getColor(com.itguy.assetmanager.R.color.text_strong, null)), 0, num.length, 0)
        }
    }

    /**
     * The numbers and the bars, from whatever stats we were handed.
     *
     * Split out so the cached copy can be painted the moment the screen
     * opens: this used to run only on the reply from the server, which is
     * why the dashboard sat empty behind a spinner every time, holding
     * numbers it had had all along.
     */
    /** Recent assets and open tickets, from the cached lists. The server
     * orders "recent" itself, which the cache cannot reproduce, so this is
     * the right shape rather than the right order until the fetch lands. */
    private fun prepaintLists() {
        OfflineCache.loadAssets()?.takeIf { it.isNotEmpty() }?.let { cached ->
            b.recentAssets.removeAllViews()
            cached.take(GLANCE).forEach { a ->
                addTwoLineRow(b.recentAssets, a.Name.ifBlank { "(unnamed)" },
                              "${a.Type} · ${a.Serial}",
                              trailing = a.Status.replace("-", " "),
                              trailingColor = statusColor(a.Status), asset = a) {
                    (activity as? MainActivity)?.showFragment(
                        AssetEditFragment.newInstance(a.id), "Edit Asset", addToBackStack = true)
                }
            }
        }
        OfflineCache.loadTickets()?.let { cached ->
            val open = cached.filter { it.status !in listOf("Resolved", "Closed") }.take(GLANCE)
            b.openTickets.removeAllViews()
            if (open.isEmpty()) emptyRow(b.openTickets, "No open tickets")
            else open.forEach { t ->
                addTwoLineRow(b.openTickets, t.subject, t.code ?: "",
                              trailing = t.status,
                              trailingColor = statusColor(t.status)) {
                    (activity as? MainActivity)?.showFragment(
                        TicketDetailFragment.newInstance(t.id), "Ticket ${t.code ?: ""}",
                        addToBackStack = true)
                }
            }
        }
    }

    private fun paintStats(d: com.itguy.assetmanager.data.model.DashboardStats) {
            b.statTotal.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statValue).text = d.total.toString()
            b.statOut.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statValue).text = d.checked_out.toString()
            b.statMaint.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statValue).text = d.maintenance.toString()
            b.statDue.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statValue).text = d.due_soon.toString()
            b.statWarr.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statValue).text = d.warranty_expiring.toString()

            // The hero: how much of the register is out with somebody. A
            // fraction, because a total on its own never tells you anything
            // is wrong.
            val total = d.total
            val out = d.checked_out
            val share = if (total > 0) out.toFloat() / total else 0f
            b.heroRing.progress = share
            b.heroRing.centerText = "${Math.round(share * 100)}%"
            val ready = (d.by_status ?: emptyMap())["Available"] ?: 0
            b.heroOut.text = figure(out, "with staff")
            b.heroReady.text = figure(ready, "ready to issue")
            b.heroTotal.text = figure(total, "in the register")

            // each card says what share of the register it is
            fun share(card: com.itguy.assetmanager.databinding.ItemStatCardBinding, n: Int) {
                val lbl = card.root.findViewById<TextView>(com.itguy.assetmanager.R.id.statLabel)
                val base = lbl.text.toString().substringBefore("  ·")
                lbl.text = if (total > 0 && n > 0) "$base  ·  ${Math.round(n * 100f / total)}%" else base
            }
            share(b.statOut, out); share(b.statMaint, d.maintenance)
            share(b.statDue, d.due_soon); share(b.statWarr, d.warranty_expiring)

            renderDonut(b.statusBars, (d.by_status ?: emptyMap()))
            renderTypeBars(b.typeBars, (d.by_type ?: emptyMap()), 8)
            renderBars(b.contractsBars, (d.contracts_by_type ?: emptyMap())) { resources.getColor(com.itguy.assetmanager.R.color.accent2, null) }
            b.contractsExpiring.removeAllViews()
            val expiring = (d.expiring_contracts ?: emptyList()).take(GLANCE)
            if (expiring.isEmpty()) emptyRow(b.contractsExpiring, "No contracts expiring soon")
            else expiring.forEach { ec ->
                addTwoLineRow(b.contractsExpiring, ec.name,
                              "${ec.vendor ?: "—"} · ends ${ec.end_date ?: "—"}",
                              trailing = "${ec.days_left}d",
                              trailingColor = if (ec.days_left <= 7)
                                  resources.getColor(com.itguy.assetmanager.R.color.stat_red, null)
                              else resources.getColor(com.itguy.assetmanager.R.color.stat_amber, null)) {
                    (activity as? MainActivity)?.showFragment(com.itguy.assetmanager.ui.contracts.ContractEditFragment.newInstance(ec.id), "Edit Contract", addToBackStack = true)
                }
            }
    }

    override fun refresh() {
        val bb = _b ?: return
        // Everything the phone already knows, on screen before a single
        // request goes out. The fetches below overwrite it in place.
        val known = OfflineCache.loadDashboard()
        if (known != null) paintStats(known)
        prepaintLists()
        bb.dashProgress.visibility = if (known == null) View.VISIBLE else View.GONE
        bb.offlineBanner.visibility = View.GONE
        lifecycleScope.launch {
            try {
                var d = if (!NetworkUtils.isOnline(requireContext())) null else try {
                    val resp = ApiClient.api().dashboard()
                    resp.body()?.also { if (resp.isSuccessful) OfflineCache.saveDashboard(it) }
                } catch (e: Exception) { null }
                if (d == null) {
                    d = OfflineCache.loadDashboard()
                    if (d != null && _b != null) {
                        val age = NetworkUtils.timeAgo(OfflineCache.lastUpdated("dashboard"))
                        b.offlineBanner.text = "📡 Offline — showing cached data from $age"
                        b.offlineBanner.visibility = View.VISIBLE
                    }
                }
                if (_b != null && d != null) paintStats(d)
            } catch (e: Exception) {}

            try { com.itguy.assetmanager.data.Looks.refresh() } catch (e: Exception) {}
            try {
                val list = ApiClient.api().listAssets(order = "recent").body().orEmpty().take(GLANCE)
                if (_b != null) {
                    b.recentAssets.removeAllViews()
                    if (list.isEmpty()) emptyRow(b.recentAssets, "No assets")
                    else list.forEach { a ->
                        addTwoLineRow(b.recentAssets, a.Name.ifBlank { "(unnamed)" },
                                      "${a.Type} · ${a.Serial}",
                                      trailing = a.Status.replace("-", " "),
                                      trailingColor = statusColor(a.Status), asset = a) {
                            (activity as? MainActivity)?.showFragment(AssetEditFragment.newInstance(a.id), "Edit Asset", addToBackStack = true)
                        }
                    }
                }
            } catch (e: Exception) {}

            try {
                val open = ApiClient.api().listTickets().body().orEmpty().filter { it.status !in listOf("Resolved", "Closed") }.take(GLANCE)
                if (_b != null) {
                    b.openTickets.removeAllViews()
                    if (open.isEmpty()) emptyRow(b.openTickets, "No open tickets")
                    else open.forEach { t ->
                        addTwoLineRow(b.openTickets, t.subject,
                                      t.code ?: "",
                                      trailing = t.status,
                                      trailingColor = statusColor(t.status)) {
                            (activity as? MainActivity)?.showFragment(TicketDetailFragment.newInstance(t.id), "Ticket ${t.code ?: ""}", addToBackStack = true)
                        }
                    }
                }
            } catch (e: Exception) {}

            try {
                val audit = ApiClient.api().audit().body().orEmpty().take(GLANCE)
                if (_b != null) {
                    b.activityFeed.removeAllViews()
                    if (audit.isEmpty()) emptyRow(b.activityFeed, "No activity")
                    else audit.forEach { a ->
                        val what = a.detail?.takeIf { it.isNotBlank() }
                            ?: a.action.orEmpty()
                        val who = listOfNotNull(
                            a.actor?.takeIf { it.isNotBlank() },
                            a.action?.takeIf { it.isNotBlank() && it != what },
                        ).joinToString(" · ")
                        addTwoLineRow(b.activityFeed, what, who,
                                      trailing = Regex("""(\d{1,2}:\d{2})(?::\d{2})?""").find(a.ts ?: "")?.groupValues?.get(1) ?: "",
                                      onClick = null)
                    }
                }
            } catch (e: Exception) {}

            _b?.dashProgress?.visibility = View.GONE
        }
    }

    private fun statusColor(s: String): Int = com.itguy.assetmanager.ui.StatusTint.of(s)

    private fun statusColorOld(s: String): Int = when (s) {
        "Available" -> Color.parseColor("#2ECC71")
        "Checked-Out" -> Color.parseColor("#3BC9DB")
        "Returned" -> Color.parseColor("#9B7BE0")
        "Under-Maintenance" -> Color.parseColor("#FFB84D")
        "Retired" -> Color.parseColor("#FF3B30")
        else -> Color.parseColor("#8A93A6")
    }

    /** The status donut and its legend, as on the web: tap a status to see those assets. */
    private fun renderDonut(container: LinearLayout, data: Map<String, Int>) {
        container.removeAllViews()
        val entries = data.toList().filter { it.second > 0 }.sortedByDescending { it.second }
        if (entries.isEmpty()) { emptyRow(container, "No data yet"); return }
        val ctx = requireContext(); val d = resources.displayMetrics.density
        val total = entries.sumOf { it.second }
        val row = LinearLayout(ctx).apply { orientation = LinearLayout.HORIZONTAL; gravity = android.view.Gravity.CENTER_VERTICAL }
        val donut = com.itguy.assetmanager.ui.DonutView(ctx).apply {
            setData(entries.map { it.second to statusColor(it.first) },
                    resources.getColor(com.itguy.assetmanager.R.color.divider, null),
                    resources.getColor(com.itguy.assetmanager.R.color.text_strong, null),
                    resources.getColor(com.itguy.assetmanager.R.color.text_soft, null))
        }
        row.addView(donut, LinearLayout.LayoutParams((118 * d).toInt(), (118 * d).toInt()).also { it.rightMargin = (18 * d).toInt() })
        val legend = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL }
        for ((label, count) in entries) {
            val line = LinearLayout(ctx).apply {
                orientation = LinearLayout.HORIZONTAL; gravity = android.view.Gravity.CENTER_VERTICAL
                setPadding(0, (5 * d).toInt(), 0, (5 * d).toInt())
                isClickable = true; isFocusable = true
                setBackgroundResource(com.itguy.assetmanager.R.drawable.nav_item_bg)
                setOnClickListener {
                    (activity as? MainActivity)?.showFragment(
                        com.itguy.assetmanager.ui.assets.AssetsListFragment.newInstance(status = label),
                        "Assets", addToBackStack = true)
                }
            }
            line.addView(View(ctx).apply {
                background = android.graphics.drawable.GradientDrawable().apply { cornerRadius = 3 * d; setColor(statusColor(label)) }
            }, LinearLayout.LayoutParams((10 * d).toInt(), (10 * d).toInt()).also { it.rightMargin = (9 * d).toInt() })
            line.addView(TextView(ctx).apply {
                text = label.replace("-", " "); textSize = 13f; maxLines = 1
                ellipsize = android.text.TextUtils.TruncateAt.END
                setTextColor(resources.getColor(com.itguy.assetmanager.R.color.text_strong, null))
            }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            line.addView(TextView(ctx).apply {
                text = count.toString(); textSize = 13f; setTypeface(typeface, android.graphics.Typeface.BOLD)
                setTextColor(resources.getColor(com.itguy.assetmanager.R.color.text_strong, null))
            })
            line.addView(TextView(ctx).apply {
                text = "${Math.round(count * 100f / total)}%"; textSize = 11.5f; gravity = android.view.Gravity.END
                setTextColor(resources.getColor(com.itguy.assetmanager.R.color.text_soft, null))
            }, LinearLayout.LayoutParams((40 * d).toInt(), ViewGroup.LayoutParams.WRAP_CONTENT))
            legend.addView(line)
        }
        row.addView(legend, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        container.addView(row)
    }

    /** Top asset types with the same icons as the list; the rest summed up in one line. */
    private fun renderTypeBars(container: LinearLayout, data: Map<String, Int>, top: Int) {
        val entries = data.toList().sortedByDescending { it.second }
        val shown = entries.take(top); val rest = entries.drop(top)
        renderBars(container, shown.toMap()) {
            com.itguy.assetmanager.data.Palette.serverColours()?.accent
                ?: resources.getColor(com.itguy.assetmanager.R.color.accent, null)
        }
        // an icon tile in front of each row
        val ctx = requireContext(); val d = resources.displayMetrics.density
        val accent = com.itguy.assetmanager.data.Palette.serverColours()?.accent
            ?: resources.getColor(com.itguy.assetmanager.R.color.accent, null)
        for (i in 0 until container.childCount) {
            val rowView = container.getChildAt(i) as? LinearLayout ?: continue
            val type = shown.getOrNull(i)?.first ?: continue
            container.removeViewAt(i)
            val wrap = LinearLayout(ctx).apply { orientation = LinearLayout.HORIZONTAL; gravity = android.view.Gravity.CENTER_VERTICAL }
            val tile = android.widget.FrameLayout(ctx).apply {
                background = android.graphics.drawable.GradientDrawable().apply { cornerRadius = 9 * d; setColor((accent and 0x00FFFFFF) or 0x24000000) }
            }
            tile.addView(android.widget.ImageView(ctx).apply {
                setImageResource(com.itguy.assetmanager.ui.TypeIcons.forType(type))
                imageTintList = android.content.res.ColorStateList.valueOf(accent)
            }, android.widget.FrameLayout.LayoutParams((16 * d).toInt(), (16 * d).toInt(), android.view.Gravity.CENTER))
            wrap.addView(tile, LinearLayout.LayoutParams((32 * d).toInt(), (32 * d).toInt()).also { it.rightMargin = (12 * d).toInt(); it.bottomMargin = (10 * d).toInt() })
            wrap.addView(rowView, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            container.addView(wrap, i)
        }
        if (rest.isNotEmpty()) container.addView(TextView(ctx).apply {
            text = "+ ${rest.size} more type${if (rest.size > 1) "s" else ""} · ${rest.sumOf { it.second }} assets"
            textSize = 12.5f; setPadding((44 * d).toInt(), (2 * d).toInt(), 0, 0)
            setTextColor(resources.getColor(com.itguy.assetmanager.R.color.text_soft, null))
        })
    }

    /** Reproduces the web app's renderBars(): sorted desc by count, each row a label+count line over a proportional colored bar. */
    private fun renderBars(container: LinearLayout, data: Map<String, Int>, colorFor: (String) -> Int) {
        container.removeAllViews()
        val entries = data.toList().sortedByDescending { it.second }
        if (entries.isEmpty()) { emptyRow(container, "No data yet"); return }
        val max = (entries.maxOfOrNull { it.second } ?: 1).coerceAtLeast(1)
        val density = resources.displayMetrics.density
        for ((label, count) in entries) {
            val row = LinearLayout(requireContext()).apply { orientation = LinearLayout.VERTICAL; setPadding(0, 0, 0, (10 * density).toInt()) }
            val top = LinearLayout(requireContext()).apply { orientation = LinearLayout.HORIZONTAL }
            val labelTv = TextView(requireContext()).apply { text = label; setTextColor(resources.getColor(com.itguy.assetmanager.R.color.text_soft, null)); textSize = 13f
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f) }
            val countTv = TextView(requireContext()).apply { text = count.toString(); setTextColor(resources.getColor(com.itguy.assetmanager.R.color.text, null)); textSize = 13f; setTypeface(typeface, android.graphics.Typeface.BOLD) }
            top.addView(labelTv); top.addView(countTv)
            val track = LinearLayout(requireContext()).apply {
                layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, (7 * density).toInt()).also { it.topMargin = (7 * density).toInt() }
                // rounded, like everything else now, and clipped so the fill
                // inside takes the same corners
                background = android.graphics.drawable.GradientDrawable().apply {
                    cornerRadius = 4 * density
                    setColor(resources.getColor(com.itguy.assetmanager.R.color.divider, null))
                }
                clipToOutline = true
            }
            val fillWidthPct = (count.toFloat() / max.toFloat())
            val fill = View(requireContext())
            fill.background = android.graphics.drawable.GradientDrawable().apply {
                cornerRadius = 4 * density
                setColor(colorFor(label))
            }
            track.addView(fill, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, fillWidthPct))
            track.addView(View(requireContext()), LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f - fillWidthPct))
            row.addView(top); row.addView(track)
            container.addView(row)
        }
    }

    /**
     * One row in a card: a small marker, the thing, and the detail under it.
     *
     * The marker and the hairline are what the reference uses to turn a stack
     * of text into a list you can scan -- without them, six two-line rows in
     * a card read as one paragraph.
     */
    /** How many rows of a list belong on a dashboard. The rest are one tap
     *  away on the screen that owns them. */
    private val GLANCE = 4

    private fun addTwoLineRow(
        container: LinearLayout, title: String, subtitle: String,
        trailing: String? = null, trailingColor: Int? = null,
        asset: com.itguy.assetmanager.data.model.Asset? = null, onClick: (() -> Unit)?,
    ) {
        val d = resources.displayMetrics.density
        fun px(v: Float) = (v * d).toInt()
        val ctx = requireContext()

        // a divider above every row but the first
        if (container.childCount > 0) {
            container.addView(View(ctx).apply {
                layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, px(1f))
                    .also { it.leftMargin = px(34f); it.rightMargin = px(12f) }
                setBackgroundColor(resources.getColor(com.itguy.assetmanager.R.color.divider, null))
            })
        }

        val row = LinearLayout(ctx).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = android.view.Gravity.CENTER_VERTICAL
            setPadding(px(12f), px(12f), px(12f), px(12f))
            if (onClick != null) {
                isClickable = true
                isFocusable = true
                setBackgroundResource(com.itguy.assetmanager.R.drawable.nav_item_bg)
                setOnClickListener { onClick() }
            }
        }

        if (asset != null) {
            // the asset's picture, as in the list: photo, else its type icon
            val accent = com.itguy.assetmanager.data.Palette.serverColours()?.accent
                ?: resources.getColor(com.itguy.assetmanager.R.color.accent, null)
            val tile = android.widget.FrameLayout(ctx)
            fun paint(c: Int) { tile.background = android.graphics.drawable.GradientDrawable().apply { cornerRadius = px(9f).toFloat(); setColor(c) } }
            paint((accent and 0x00FFFFFF) or 0x24000000)
            val icon = android.widget.ImageView(ctx).apply {
                setImageResource(com.itguy.assetmanager.ui.TypeIcons.forType(asset.Type))
                imageTintList = android.content.res.ColorStateList.valueOf(accent)
            }
            val photo = android.widget.ImageView(ctx).apply { scaleType = android.widget.ImageView.ScaleType.FIT_CENTER; setPadding(px(2f), px(2f), px(2f), px(2f)); visibility = View.GONE }
            tile.addView(icon, android.widget.FrameLayout.LayoutParams(px(17f), px(17f), android.view.Gravity.CENTER))
            tile.addView(photo, android.widget.FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
            com.itguy.assetmanager.ui.Images.load(photo, com.itguy.assetmanager.data.Looks.pictureFor(asset), 120) { shown ->
                photo.visibility = if (shown) View.VISIBLE else View.GONE
                icon.visibility = if (shown) View.GONE else View.VISIBLE
                if (shown) paint(android.graphics.Color.WHITE)
            }
            row.addView(tile, LinearLayout.LayoutParams(px(34f), px(34f)).also { it.rightMargin = px(12f) })
        } else row.addView(View(ctx).apply {
            layoutParams = LinearLayout.LayoutParams(px(10f), px(10f))
                .also { it.rightMargin = px(12f) }
            setBackgroundResource(com.itguy.assetmanager.R.drawable.rail_dot)
        })

        val text = LinearLayout(ctx).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        }
        text.addView(TextView(ctx).apply {
            setText(title)
            setTextColor(resources.getColor(com.itguy.assetmanager.R.color.text_strong, null))
            textSize = 14f
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
        })
        // no second line rather than an empty one: a row whose subtitle is
        // blank used to reserve the space anyway, which is how the activity
        // feed ended up with a lone separator under every entry
        if (subtitle.isNotBlank()) text.addView(TextView(ctx).apply {
            setText(subtitle)
            setTextColor(resources.getColor(com.itguy.assetmanager.R.color.text_soft, null))
            textSize = 12f
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
            (layoutParams as? LinearLayout.LayoutParams ?: LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
                .also { it.topMargin = px(2f); layoutParams = it }
        })
        row.addView(text)

        // the time, the status, the days left: the one value that makes the
        // row worth a glance, right-aligned as in the reference
        if (!trailing.isNullOrBlank()) {
            row.addView(TextView(ctx).apply {
                setText(trailing)
                textSize = 11.5f
                setTypeface(typeface, android.graphics.Typeface.BOLD)
                setPadding(px(10f), px(5f), px(10f), px(5f))
                val tint = trailingColor
                    ?: resources.getColor(com.itguy.assetmanager.R.color.text_soft, null)
                setTextColor(tint)
                background = android.graphics.drawable.GradientDrawable().apply {
                    cornerRadius = 100f
                    setColor((tint and 0x00FFFFFF) or 0x14000000)
                }
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT
                ).also { it.leftMargin = px(8f) }
            })
        }
        container.addView(row)
    }

    private fun emptyRow(container: LinearLayout, text: String) {
        val d = resources.displayMetrics.density
        val tv = TextView(requireContext())
        tv.text = text
        tv.setTextColor(resources.getColor(com.itguy.assetmanager.R.color.text_faint, null))
        tv.textSize = 13f
        tv.setPadding((14 * d).toInt(), (14 * d).toInt(), (14 * d).toInt(), (14 * d).toInt())
        container.addView(tv)
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _b = null
    }
}
