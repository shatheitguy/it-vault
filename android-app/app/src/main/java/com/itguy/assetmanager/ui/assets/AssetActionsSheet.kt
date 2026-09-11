package com.itguy.assetmanager.ui.assets

import android.content.Intent
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.google.android.material.bottomsheet.BottomSheetDialogFragment
import com.itguy.assetmanager.R
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.model.Asset
import kotlinx.coroutines.launch

/**
 * The row action menu from the web UI, as a native bottom sheet: Edit, Sign,
 * Print label, QR, Check-in/out, Delete. Reached by long-pressing an asset
 * row (tapping still opens Edit, as before).
 */
class AssetActionsSheet : BottomSheetDialogFragment() {

    companion object {
        private const val ARG_ID = "id"
        private const val ARG_TAG = "tag"
        private const val ARG_NAME = "name"
        private const val ARG_STATUS = "status"

        fun newInstance(a: Asset): AssetActionsSheet = AssetActionsSheet().apply {
            arguments = Bundle().apply {
                putString(ARG_ID, a.id)
                putString(ARG_TAG, a.AssetTag)
                putString(ARG_NAME, a.Name)
                putString(ARG_STATUS, a.Status)
            }
        }
    }

    /** Set by the host fragment so an action can refresh the list / navigate. */
    var onEdit: (() -> Unit)? = null
    var onAssign: (() -> Unit)? = null
    var onChanged: (() -> Unit)? = null

    private val assetId get() = arguments?.getString(ARG_ID).orEmpty()
    private val assetTag get() = arguments?.getString(ARG_TAG).orEmpty()
    private val assetName get() = arguments?.getString(ARG_NAME).orEmpty()
    private val assetStatus get() = arguments?.getString(ARG_STATUS).orEmpty()

    override fun onCreateView(
        inflater: android.view.LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View {
        val ctx = requireContext()
        val pad = (16 * resources.displayMetrics.density).toInt()

        val root = LinearLayout(ctx).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, pad / 2, 0, pad)
        }

        root.addView(TextView(ctx).apply {
            text = listOf(assetTag, assetName).filter { it.isNotBlank() }.joinToString(" · ")
                .ifBlank { "Asset" }
            setPadding(pad, pad / 2, pad, pad / 2)
            textSize = 15f
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setTextColor(ContextCompat.getColor(ctx, R.color.text))
        })

        fun row(label: String, onTap: () -> Unit) {
            root.addView(TextView(ctx).apply {
                text = label
                textSize = 16f
                gravity = Gravity.CENTER_VERTICAL
                setPadding(pad, pad, pad, pad)
                setTextColor(ContextCompat.getColor(ctx, R.color.text))
                isClickable = true
                setBackgroundResource(R.drawable.nav_item_bg)
                setOnClickListener { onTap() }
            })
        }

        row("✏️  Edit asset") { dismiss(); onEdit?.invoke() }
        // Assigning is the thing people do most from a list, and it was only
        // reachable by opening the asset and finding a button inside it.
        if (!assetStatus.equals("Checked-Out", ignoreCase = true)) {
            row("👤  Assign to employee") { dismiss(); onAssign?.invoke() }
        }
        row("✍️  Sign / acknowledge") { shareSignLink() }
        row("🖨️  Print label") { openLabel(printNow = true) }
        row("🔳  QR label") { openLabel(printNow = false) }

        if (assetStatus.equals("Checked-Out", ignoreCase = true)) {
            row("📥  Check in") { checkIn() }
        }
        row("🗑️  Delete asset") { confirmDelete() }

        return root
    }

    /** Fetches the acknowledgement link, then hands it to the Android share
     * sheet so it can go out by WhatsApp/email/copy -- whatever's installed. */
    private fun shareSignLink() {
        val id = assetId
        if (id.isBlank()) { toast("This asset has no id yet"); return }
        lifecycleScope.launch {
            try {
                val resp = ApiClient.api().signLink(id)
                val url = resp.body()?.url
                if (!resp.isSuccessful || url.isNullOrBlank()) {
                    toast(resp.body()?.error ?: "Could not create a sign link (need write access)")
                    return@launch
                }
                val subject = "Acknowledge asset ${assetTag.ifBlank { assetName }}"
                val text = "Please review and sign for ${assetName.ifBlank { assetTag }}:\n$url"
                val send = Intent(Intent.ACTION_SEND).apply {
                    type = "text/plain"
                    putExtra(Intent.EXTRA_SUBJECT, subject)
                    putExtra(Intent.EXTRA_TEXT, text)
                }
                startActivity(Intent.createChooser(send, "Send sign link"))
                dismiss()
            } catch (e: Exception) {
                toast("Could not create a sign link: ${e.message}")
            }
        }
    }

    private fun openLabel(printNow: Boolean) {
        val id = assetId
        if (id.isBlank()) { toast("This asset has no id yet"); return }
        startActivity(LabelViewActivity.intent(requireContext(), id, assetTag, printNow))
        dismiss()
    }

    private fun checkIn() {
        lifecycleScope.launch {
            try {
                val resp = ApiClient.api().checkinAsset(assetId)
                if (resp.isSuccessful) { toast("✓ Checked in"); dismiss(); onChanged?.invoke() }
                else toast(resp.body()?.error ?: "Check-in failed")
            } catch (e: Exception) { toast("Check-in failed: ${e.message}") }
        }
    }

    private fun confirmDelete() {
        androidx.appcompat.app.AlertDialog.Builder(requireContext())
            .setTitle("Delete asset?")
            .setMessage("${assetTag.ifBlank { assetName }} moves to Trash and can be restored from there.")
            .setNegativeButton("Cancel", null)
            .setPositiveButton("Delete") { _, _ ->
                lifecycleScope.launch {
                    try {
                        val resp = ApiClient.api().deleteAsset(assetId)
                        if (resp.isSuccessful) { toast("✓ Moved to Trash"); dismiss(); onChanged?.invoke() }
                        else toast(resp.body()?.error ?: "Delete failed")
                    } catch (e: Exception) { toast("Delete failed: ${e.message}") }
                }
            }
            .show()
    }

    private fun toast(msg: String) {
        if (isAdded) Toast.makeText(requireContext(), msg, Toast.LENGTH_LONG).show()
    }
}

/** Convenience so any fragment can pop the sheet in one line. */
fun Fragment.showAssetActions(
    asset: Asset,
    onEdit: () -> Unit,
    onChanged: () -> Unit,
    onAssign: (() -> Unit)? = null,
) {
    val sheet = AssetActionsSheet.newInstance(asset)
    sheet.onEdit = onEdit
    sheet.onChanged = onChanged
    sheet.onAssign = onAssign ?: onEdit
    sheet.show(childFragmentManager, "asset_actions")
}
