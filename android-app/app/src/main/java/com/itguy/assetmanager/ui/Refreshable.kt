package com.itguy.assetmanager.ui

/** Implemented by top-level list fragments so pull-to-refresh in MainActivity can reach them. */
interface Refreshable {
    fun refresh()
}

/**
 * A screen that has to be told when the install's colours have landed.
 *
 * Most screens need nothing: the palette walks their views and repaints them
 * wherever it finds a colour it knows. A screen only implements this when it
 * has worked something *out* from those colours -- the dashboard picks the
 * ink for its hero card by measuring how light the card is -- because that
 * sum was done against whatever the card was at the time.
 *
 * On a second launch the branding is already cached and the order is kind.
 * On the very first login it is not: the dashboard is built, the sum is done
 * against the bundled colour, and the server's answer arrives a moment later.
 * That is how a yellow card ended up with white text on it.
 */
interface Rebranded {
    fun onPaletteApplied()
}
