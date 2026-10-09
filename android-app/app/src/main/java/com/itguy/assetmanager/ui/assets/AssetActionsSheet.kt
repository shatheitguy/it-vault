package com.itguy.assetmanager.ui.assets

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.google.android.material.bottomsheet.BottomSheetDialogFragment
import com.itguy.assetmanager.R
import com.itguy.assetmanager.data.ApiClient
import com.itguy.assetmanager.data.model.Asset
import com.itguy.assetmanager.ui.ActionSheet
import kotlinx.coroutines.launch

/**
 * The row action menu from the web UI, as a native bottom sheet: Edit, Sign,
 * Print record, Print label, QR, Check-in/out, Delete. Reached by long-pressing an asset
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
        val root = LinearLayout(ctx).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, 0, 0, (10 * resources.displayMetrics.density).toInt())
        }

        root.addView(ActionSheet.header(
            ctx,
            assetName.ifBlank { assetTag }.ifBlank { "Asset" },
            assetTag.takeIf { it.isNotBlank() && assetName.isNotBlank() },
        ))
        root.addView(ActionSheet.divider(ctx))

        val rows = mutableListOf(
            ActionSheet.Row("Edit asset", R.drawable.ic_edit) { dismiss(); onEdit?.invoke() },
        )
        // Assigning is the thing people do most from a list, and it was only
        // reachable by opening the asset and finding a button inside it.
        if (!assetStatus.equals("Checked-Out", ignoreCase = true)) {
            rows += ActionSheet.Row("Assign to employee", R.drawable.ic_person) {
                dismiss(); onAssign?.invoke()
            }
        } else {
            rows += ActionSheet.Row("Check in", R.drawable.ic_checkin) { checkIn() }
        }
        rows += ActionSheet.Row("Sign / acknowledge", R.drawable.ic_sign) { shareSignLink() }
        // Two different printouts, and only the label was reachable from
        // here: the tag you stick on the thing, and the A4 record of what the
        // thing is and who has it. The web list prints both.
        rows += ActionSheet.Row("Print asset record", R.drawable.ic_doc) { openRecord() }
        rows += ActionSheet.Row("Print QR label", R.drawable.ic_tag) { openLabel(printNow = true) }
        rows += ActionSheet.Row("View QR label", R.drawable.ic_qr) { openLabel(printNow = false) }
        rows.forEach { root.addView(ActionSheet.row(ctx, it)) }

        root.addView(ActionSheet.divider(ctx))
        root.addView(ActionSheet.row(ctx, ActionSheet.Row(
            "Delete asset", R.drawable.ic_trash, destructive = true) { confirmDelete() }))

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

    /** The A4 record sheet. Built on the phone from the asset it already
     * has, so it prints in a store room with no signal too. */
    private fun openRecord() {
        val id = assetId
        if (id.isBlank()) { toast("This asset has no id yet"); return }
        startActivity(RecordViewActivity.intent(requireContext(), id, assetTag, true))
        dismiss()
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
        com.itguy.assetmanager.ui.BrandDialog(requireContext())
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
