package com.itguy.assetmanager.ui

import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.ActionBarDrawerToggle
import androidx.appcompat.app.AppCompatActivity
import androidx.fragment.app.Fragment
import com.google.android.material.navigation.NavigationView
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.Prefs
import com.itguy.assetmanager.databinding.ActivityMainBinding
import com.itguy.assetmanager.ui.assets.AssetsListFragment
import com.itguy.assetmanager.ui.dashboard.DashboardFragment
import com.itguy.assetmanager.ui.employees.DirectoryFragment
import com.itguy.assetmanager.ui.generic.GenericListFragment
import com.itguy.assetmanager.ui.generic.ListKind
import com.itguy.assetmanager.ui.login.LoginActivity
import com.itguy.assetmanager.ui.settings.SettingsFragment
import com.itguy.assetmanager.ui.tickets.TicketsListFragment
import com.itguy.assetmanager.ui.unifi.UnifiFragment

class MainActivity : AppCompatActivity(), NavigationView.OnNavigationItemSelectedListener {

    private lateinit var b: ActivityMainBinding
    private lateinit var drawerToggle: ActionBarDrawerToggle

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Prefs.init(applicationContext)
        if (!Prefs.isLoggedIn) {
            startActivity(Intent(this, LoginActivity::class.java)); finish(); return
        }

        b = ActivityMainBinding.inflate(layoutInflater)
        setContentView(b.root)
        setSupportActionBar(b.toolbar)

        drawerToggle = ActionBarDrawerToggle(this, b.drawerLayout, b.toolbar, 0, 0)
        b.drawerLayout.addDrawerListener(drawerToggle)
        drawerToggle.syncState()

        b.navView.setNavigationItemSelectedListener(this)
        val header = b.navView.getHeaderView(0)
        header.findViewById<android.widget.TextView>(com.itguy.assetmanager.R.id.navHeaderUser).text =
            "${Prefs.displayName.ifBlank { Prefs.username }} · ${Prefs.role}"

        b.swipeRefresh.setOnRefreshListener {
            val f = supportFragmentManager.findFragmentById(com.itguy.assetmanager.R.id.fragmentContainer)
            (f as? Refreshable)?.refresh()
            b.swipeRefresh.isRefreshing = false
        }

        supportFragmentManager.addOnBackStackChangedListener { updateDrawerLockState() }

        if (savedInstanceState == null) {
            showFragment(DashboardFragment(), "Dashboard")
            b.navView.setCheckedItem(com.itguy.assetmanager.R.id.nav_dashboard)
        }
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
            com.itguy.assetmanager.R.id.nav_contracts -> showFragment(GenericListFragment.newInstance(ListKind.CONTRACTS), "Contracts")
            com.itguy.assetmanager.R.id.nav_locations -> showFragment(GenericListFragment.newInstance(ListKind.LOCATIONS), "Locations")
            com.itguy.assetmanager.R.id.nav_catalog -> showFragment(GenericListFragment.newInstance(ListKind.CATALOG), "Product Catalog")
            com.itguy.assetmanager.R.id.nav_trash -> showFragment(GenericListFragment.newInstance(ListKind.TRASH), "Trash")
            com.itguy.assetmanager.R.id.nav_audit -> showFragment(GenericListFragment.newInstance(ListKind.AUDIT), "Audit Log")
            com.itguy.assetmanager.R.id.nav_unifi -> showFragment(UnifiFragment(), "UniFi Controller")
            com.itguy.assetmanager.R.id.nav_settings -> showFragment(SettingsFragment(), "Settings")
            com.itguy.assetmanager.R.id.nav_logout -> { logout(); return true }
        }
        item.isChecked = true
        return true
    }

    private fun logout() {
        Prefs.clear()
        ApiClient.reset()
        startActivity(Intent(this, LoginActivity::class.java))
        finish()
    }
}
