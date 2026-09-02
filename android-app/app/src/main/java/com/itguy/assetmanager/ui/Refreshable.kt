package com.itguy.assetmanager.ui

/** Implemented by top-level list fragments so pull-to-refresh in MainActivity can reach them. */
interface Refreshable {
    fun refresh()
}
