package com.itguy.assetmanager.ui

import android.content.Context
import android.view.ViewTreeObserver
import androidx.appcompat.app.AlertDialog
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.itguy.assetmanager.data.Palette

/**
 * A dialog that wears the install's own colours.
 *
 * The palette repaints a view tree, and it is hooked to fragments: every
 * screen is themed the moment its view exists. A dialog is not a fragment and
 * its buttons live in a window of their own, so nothing ever reached them --
 * which is why "Pause", "Check now", "Cancel" and "Save" were still the
 * bundled red on an install whose accent is yellow, sitting directly under a
 * heading that was not.
 *
 * Wrapping the builder is the one place that fixes all of them at once.
 * `show()` on the base builder calls `create()`, so overriding this covers
 * callers that build and show in one go and callers that keep the dialog to
 * show later. The decor view exists by then but its buttons are inflated as
 * the window lays out, so the repaint waits for the first layout pass -- and
 * uses a layout listener rather than `setOnShowListener`, because a caller
 * gets only one of those and some of them need it.
 */
class BrandDialog(context: Context) : MaterialAlertDialogBuilder(context) {

    override fun create(): AlertDialog {
        val dialog = super.create()
        val decor = dialog.window?.decorView ?: return dialog
        // Over the first few layout passes, not just one. A dialog that is a
        // list builds its rows lazily, from an adapter, after the window has
        // already laid itself out once -- so a single pass repaints the title
        // and the buttons and leaves every row it has not made yet, which is
        // how a "pick one" dialog kept its radio marks in the bundled red.
        // Bounded, because repainting is not free and a dialog that is still
        // laying out after three passes is not going to settle.
        decor.viewTreeObserver.addOnGlobalLayoutListener(
            object : ViewTreeObserver.OnGlobalLayoutListener {
                private var passes = 0
                override fun onGlobalLayout() {
                    Palette.apply(decor)
                    if (++passes >= 3 && decor.viewTreeObserver.isAlive) {
                        decor.viewTreeObserver.removeOnGlobalLayoutListener(this)
                    }
                }
            }
        )
        return dialog
    }
}
