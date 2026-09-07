# Releasing the IT-Vault Android app (self-hosted auto-update)

The app updates itself with **no Play Store** involved. It reads a small manifest
from the project's GitHub Pages site and, when a newer `versionCode` is published,
offers a one-tap **Update now** that downloads the signed APK from GitHub Releases
and launches the installer.

```
app  ──daily/on-demand──►  https://shatheitguy.github.io/it-vault/app/latest.json
                                        │  (versionCode newer?)
                                        ▼
app  ──Update now──────►  https://github.com/shatheitguy/it-vault/releases/latest/download/IT-Vault.apk
```

## Signing key — already set up, do NOT regenerate

This project already has its release key:

- `android-app/keystore/itguy-assets-release.keystore`
- `android-app/keystore.properties` (points the build at it)

Both are git-ignored, so the key never leaves your machine. **Never generate a new
keystore** — every update must be signed with this same key or Android refuses the
in-place upgrade, and everyone who installed a previous build would have to
uninstall/reinstall (losing local data).

> **Back these up somewhere safe** (password manager / offline drive). If the
> keystore or its passwords are lost, the auto-update path is permanently broken
> for existing installs.

## Cutting a release

1. **Bump the version** in `android-app/app/build.gradle.kts`:
   - `versionCode` — **must increase every release** (this is what the updater compares).
   - `versionName` — the human string (e.g. `1.8.0`).

2. **Build the signed APK:**

   PowerShell (note: `;` not `&&`):

   ```powershell
   $env:JAVA_HOME = "C:\Program Files\Microsoft\jdk-17.0.20.101-hotspot"
   cd C:\Users\Sha\asset-manager\android-app
   .\gradlew.bat assembleRelease
   Copy-Item app\build\outputs\apk\release\app-release.apk IT-Vault.apk
   ```

3. **Publish a GitHub Release** and attach the APK **named exactly `IT-Vault.apk`**
   (the manifest's `apkUrl` points at `releases/latest/download/IT-Vault.apk`):

   ```bash
   gh release create v1.8.0 IT-Vault.apk --generate-notes
   ```

4. **Bump the manifest** `docs/app/latest.json` and commit/push it so GitHub Pages
   serves it:

   ```json
   {
     "versionCode": 11,
     "versionName": "1.8.0",
     "apkUrl": "https://github.com/shatheitguy/it-vault/releases/latest/download/IT-Vault.apk",
     "notes": "What changed in this release."
   }
   ```

That's it — existing installs see the new `versionCode` within a day (or immediately
via **Settings → Check for updates**) and can update in one tap.

## Optional: automate it with GitHub Actions

`.github/workflows/android-release.yml` builds + signs the APK and creates the release
whenever you push a `v*` tag. It needs these repo **secrets**
(Settings → Secrets and variables → Actions):

| Secret | Value |
| --- | --- |
| `KEYSTORE_BASE64` | `base64 -w0 keystore/itguy-assets-release.keystore` (the **existing** key) |
| `KEYSTORE_PASSWORD` | store password from `keystore.properties` |
| `KEY_ALIAS` | key alias from `keystore.properties` |
| `KEY_PASSWORD` | key password from `keystore.properties` |

Then: `git tag v1.8.0 && git push origin v1.8.0`. You still bump `docs/app/latest.json`
(step 4) so the app knows an update exists.

## Other distribution options (no account needed)

- **Obtainium** — users install [Obtainium](https://github.com/ImranR98/Obtainium),
  point it at this repo's releases, and get auto-updates for free. Works out of the box
  once you publish releases.
- **Amazon Appstore / Samsung Galaxy Store** — real public stores with free developer
  accounts if you later want a store listing.
