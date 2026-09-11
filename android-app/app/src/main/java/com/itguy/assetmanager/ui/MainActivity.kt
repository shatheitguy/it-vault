package com.itguy.assetmanager.ui

import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.ActionBarDrawerToggle
import androidx.appcompat.app.AppCompatActivity
import androidx.fragment.app.Fragment
import com.google.android.material.navigation.NavigationView
import androidx.lifecycle.lifecycleScope
import com.itguy.assetmanager.data.OfflineCache
import com.itguy.assetmanager.data.Prefs
import com.itguy.assetmanager.data.SyncManager
import com.itguy.assetmanager.data.SyncStore
import kotlinx.coroutines.launch
import com.itguy.assetmanager.databinding.ActivityMainBinding
import com.itguy.assetmanager.ui.assets.AssetsListFragment
import com.itguy.assetmanager.ui.backup.BackupRestoreFragment
import com.itguy.assetmanager.ui.contracts.ContractsListFragment
import com.itguy.assetmanager.ui.dashboard.DashboardFragment
import com.itguy.assetmanager.ui.employees.DirectoryFragment
import com.itguy.assetmanager.ui.generic.GenericListFragment
import com.itguy.assetmanager.ui.generic.ListKind
import com.itguy.assetmanager.ui.heartbeat.HeartbeatFragment
import com.itguy.assetmanager.ui.login.LoginActivity
import com.itguy.assetmanager.ui.scan.NetworkScanFragment
import com.itguy.assetmanager.ui.settings.SettingsFragment
import com.itguy.assetmanager.ui.tickets.TicketsListFragment

class MainActivity : AppCompatActivity(), NavigationView.OnNavigationItemSelectedListener {

    private lateinit var b: ActivityMainBinding
    private lateinit var drawerToggle: ActionBarDrawerToggle

    /** Guards against the bottom bar re-firing while we mirror the drawer's selection into it. */
    private var syncingNav = false

    /** Paints the server's cached name + logo into the drawer header and toolbar. */
    private fun applyBranding() {
        if (!::b.isInitialized) return
        val header = b.navView.getHeaderView(0) ?: return
        com.itguy.assetmanager.data.Branding.apply(
            this,
            header.findViewById(com.itguy.assetmanager.R.id.navHeaderBrand),
            header.findViewById(com.itguy.assetmanager.R.id.navHeaderLogo)
        )
        // The colours as well as the name. Applied to the whole window, so the
        // toolbar, drawer and bottom bar follow the deployment's accent instead
        // of the bundled red.
        com.itguy.assetmanager.data.Palette.apply(b.root)
        com.itguy.assetmanager.data.Palette.apply(header)
        com.itguy.assetmanager.data.Palette.apply(
            supportFragmentManager
                .findFragmentById(com.itguy.assetmanager.R.id.fragmentContainer)?.view
        )
    }

    /**
     * Themes every screen from one place.
     *
     * A hook per fragment would mean editing all fourteen of them and
     * remembering to edit the fifteenth. Registering recursively means a
     * screen written later is themed without being told theming exists, and
     * dialogs and bottom sheets are fragments too, so they are covered.
     */
    private fun themeEveryScreen() {
        supportFragmentManager.registerFragmentLifecycleCallbacks(
            object : androidx.fragment.app.FragmentManager.FragmentLifecycleCallbacks() {
                override fun onFragmentViewCreated(
                    fm: androidx.fragment.app.FragmentManager,
                    f: androidx.fragment.app.Fragment,
                    v: android.view.View,
                    savedInstanceState: android.os.Bundle?
                ) {
                    com.itguy.assetmanager.data.Palette.apply(v)
                }
            },
            true
        )
    }

    /** Mirrors the current destination into the bottom bar when it has a matching item. */
    private fun syncBottomNav(itemId: Int) {
        b.bottomNav.menu.findItem(itemId) ?: return
        if (b.bottomNav.selectedItemId == itemId) return
        syncingNav = true
        b.bottomNav.selectedItemId = itemId
        syncingNav = false
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        Prefs.init(applicationContext)
        Prefs.applyThemeMode()
        super.onCreate(savedInstanceState)
        OfflineCache.init(applicationContext)
        SyncStore.init(applicationContext)
        if (!Prefs.isLoggedIn) {
            startActivity(Intent(this, LoginActivity::class.java)); finish(); return
        }
        // Replay anything queued offline as soon as we're up, and keep watching
        // for the network returning so later edits sync on their own.
        SyncManager.startAutoSync(applicationContext)
        lifecycleScope.launch { runCatching { SyncManager.syncNow(applicationContext) } }

        b = ActivityMainBinding.inflate(layoutInflater)
        setContentView(b.root)
        setSupportActionBar(b.toolbar)

        drawerToggle = ActionBarDrawerToggle(this, b.drawerLayout, b.toolbar, 0, 0)
        b.drawerLayout.addDrawerListener(drawerToggle)
        drawerToggle.syncState()

        b.navView.setNavigationItemSelectedListener(this)

        // Bottom bar handles the top-level destinations; it shares the drawer's
        // item ids so both route through onNavigationItemSelected().
        b.bottomNav.setOnItemSelectedListener { item ->
            if (!syncingNav) onNavigationItemSelected(item)
            true
        }
        val header = b.navView.getHeaderView(0)
        header.findViewById<android.widget.TextView>(com.itguy.assetmanager.R.id.navHeaderUser).text =
            "${Prefs.displayName.ifBlank { Prefs.username }} · ${Prefs.role}"

        // Wear the server's own branding rather than the bundled defaults: paint
        // whatever is cached right away, then refresh from the server in the background.
        themeEveryScreen()
        applyBranding()
        lifecycleScope.launch {
            runCatching { com.itguy.assetmanager.data.Branding.refresh(applicationContext) }
            applyBranding()
        }

        b.swipeRefresh.setOnRefreshListener {
            val f = supportFragmentManager.findFragmentById(com.itguy.assetmanager.R.id.fragmentContainer)
            (f as? Refreshable)?.refresh()
            b.swipeRefresh.isRefreshing = false
        }
        // Without this, SwipeRefreshLayout only knows how to check its direct child
        // (a plain FrameLayout, which is never "scrolled"), so it treats every
        // downward drag anywhere on screen as a pull-to-refresh -- including normal
        // scrolling inside a fragment's own list/ScrollView. This makes it check the
        // fragment's *actual* scrollable content instead.
        b.swipeRefresh.setOnChildScrollUpCallback { _, _ -> canCurrentFragmentScrollUp() }

        supportFragmentManager.addOnBackStackChangedListener { updateDrawerLockState() }

        if (savedInstanceState == null) {
            showFragment(DashboardFragment(), "Dashboard")
            b.navView.setCheckedItem(com.itguy.assetmanager.R.id.nav_dashboard)
        }

        // Self-hosted update check (throttled to once a day; prompts only if newer).
        com.itguy.assetmanager.ui.update.AppUpdater.checkOnLaunch(this)
    }

    /** Finds the actual scrollable view inside whichever fragment is showing
     * (a RecyclerView or a Scroll/NestedScrollView) and asks IT whether it's
     * scrolled away from the top, instead of asking the FrameLayout wrapper. */
    private fun canCurrentFragmentScrollUp(): Boolean {
        val scrollable = findScrollable(b.fragmentContainer) ?: return false
        return scrollable.canScrollVertically(-1)
    }

    private fun findScrollable(view: android.view.View): android.view.View? {
        if (view is androidx.recyclerview.widget.RecyclerView) return view
        if (view is android.widget.ScrollView) return view
        if (view is androidx.core.widget.NestedScrollView) return view
        if (view is android.view.ViewGroup) {
            for (i in 0 until view.childCount) {
                findScrollable(view.getChildAt(i))?.let { return it }
            }
        }
        return null
    }

    private fun updateDrawerLockState() {
        val onRoot = supportFragmentManager.backStackEntryCount == 0
        supportActionBar?.setDisplayHomeAsUpEnabled(!onRoot)
        drawerToggle.isDrawerIndicatorEnabled = onRoot
        drawerToggle.syncState()
    }

    fun showFragment(fragment: Fragment, title: String, addToBackStack: Boolean = false) {
        supportActionBar?.title = title
        val tx = supportFragmentManager.beginTransaction()
            .setCustomAnimations(
                com.itguy.assetmanager.R.anim.frag_enter,
                com.itguy.assetmanager.R.anim.frag_exit,
                com.itguy.assetmanager.R.anim.frag_pop_enter,
                com.itguy.assetmanager.R.anim.frag_pop_exit
            )
            .replace(com.itguy.assetmanager.R.id.fragmentContainer, fragment)
        if (addToBackStack) tx.addToBackStack(null)
        else supportFragmentManager.popBackStack(null, androidx.fragment.app.FragmentManager.POP_BACK_STACK_INCLUSIVE)
        tx.commit()
    }

    override fun onSupportNavigateUp(): Boolean {
        if (supportFragmentManager.backStackEntryCount > 0) { supportFragmentManager.popBackStack(); return true }
        return super.onSupportNavigateUp()
    }

    override fun onBackPressed() {
        if (b.drawerLayout.isDrawerOpen(androidx.core.view.GravityCompat.START)) {
            b.drawerLayout.closeDrawers()
        } else if (supportFragmentManager.backStackEntryCount > 0) {
            supportFragmentManager.popBackStack()
        } else {
            super.onBackPressed()
        }
    }

    override fun onNavigationItemSelected(item: android.view.MenuItem): Boolean {
        b.drawerLayout.closeDrawers()
        when (item.itemId) {
            com.itguy.assetmanager.R.id.nav_dashboard -> showFragment(DashboardFragment(), "Dashboard")
            com.itguy.assetmanager.R.id.nav_assets -> showFragment(AssetsListFragment(), "Assets")
            com.itguy.assetmanager.R.id.nav_directory -> showFragment(DirectoryFragment(), "Directory")
            com.itguy.assetmanager.R.id.nav_tickets -> showFragment(TicketsListFragment(), "Tickets")
            com.itguy.assetmanager.R.id.nav_contracts -> showFragment(ContractsListFragment(), "Contracts")
            com.itguy.assetmanager.R.id.nav_catalog -> showFragment(GenericListFragment.newInstance(ListKind.CATALOG), "Product Catalog")
            com.itguy.assetmanager.R.id.nav_trash -> showFragment(GenericListFragment.newInstance(ListKind.TRASH), "Trash")
            com.itguy.assetmanager.R.id.nav_audit -> showFragment(GenericListFragment.newInstance(ListKind.AUDIT), "Audit Log")
            com.itguy.assetmanager.R.id.nav_scan -> showFragment(NetworkScanFragment(), "Network Scan")
            com.itguy.assetmanager.R.id.nav_heartbeat -> showFragment(HeartbeatFragment(), "Heartbeat")
            com.itguy.assetmanager.R.id.nav_backup -> showFragment(BackupRestoreFragment(), "Backup / Restore")
            com.itguy.assetmanager.R.id.nav_settings -> showFragment(SettingsFragment(), "Settings")
        }
        item.isChecked = true
        syncBottomNav(item.itemId)
        return true
    }
}
