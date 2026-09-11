# Releasing IT-Vault

One version number, stated in four places, published by one git tag.

## The four places

| File | What reads it |
|---|---|
| `VERSION` | the web app (`APP_VERSION`), shown in Settings and compared against GitHub Releases on an update check |
| `android-app/app/build.gradle.kts` → `versionName` | the version shown in the Android app |
| `android-app/app/build.gradle.kts` → `versionCode` | **the only thing the in-app updater compares.** Must increase every release, and never go backwards |
| `docs/app/latest.json` | what installed phones poll to learn a new build exists |

`tests/test_versions_agree.py` fails if any of them disagree, and it runs in CI
before the image is built. These drifted three ways once — `VERSION` said
1.8.0, the Android build said 1.9.0, and the manifest said 1.6.2, so the
updater offered phones a "new" version whose name read as a downgrade.

## Cutting a release

```bash
# 1. bump all four, keeping versionCode strictly increasing
#    VERSION, build.gradle.kts (versionName + versionCode), docs/app/latest.json

# 2. prove they agree before you tag
python tests/test_versions_agree.py

# 3. commit and tag -- the tag is what publishes
git commit -am "IT-Vault 1.9.0"
git tag v1.9.0
git push origin HEAD --tags
```

Pushing the tag fires both workflows:

- **`docker-publish.yml`** builds linux/amd64 + linux/arm64 and pushes
  `ghcr.io/shatheitguy/it-vault` tagged `1.9.0`, `1.9`, the commit sha, and
  `latest` (the last only from the default branch).
- **`android-release.yml`** builds and signs the APK and creates the GitHub
  Release.

## Docker image tags, and which to use

| Tag | Moves? | Use it for |
|---|---|---|
| `latest` | yes, every default-branch push | the install one-liner; what most people run |
| `1.9.0` | never | pinning a known-good build in production |
| `1.9` | yes, within the minor series | patches without re-pinning |
| `<sha>` | never | bisecting a regression to one commit |

Pin with `ITVAULT_TAG=1.9.0` in `.env`, or `--tag 1.9.0` on the installer.

## Two things that will bite you

**The APK asset must be named exactly `IT-Vault.apk`.** The README badge, the
download button on `docs/index.html` and the app's own updater all resolve
`https://github.com/shatheitguy/it-vault/releases/latest/download/IT-Vault.apk`,
which matches by *filename* inside whatever release is latest. Attaching
`IT-Vault-v1.9.0.apk` 404s all three at once. If you upload by hand:

```bash
gh release upload v1.9.0 android-app/IT-Vault.apk --clobber
curl -sIL https://github.com/shatheitguy/it-vault/releases/latest/download/IT-Vault.apk | tail -1
```

**`android-release.yml` needs signing secrets.** It reads `KEYSTORE_BASE64`,
`KEYSTORE_PASSWORD`, `KEY_ALIAS` and `KEY_PASSWORD` from repo secrets. With
none set the job fails and no APK is attached — the Docker image still
publishes. Either add them under Settings ▸ Secrets and variables ▸ Actions, or
build locally and upload with the command above.

Never regenerate the signing key: a new one breaks in-place updates for every
existing install.

## After publishing

```bash
# the image tags actually exist
docker manifest inspect ghcr.io/shatheitguy/it-vault:1.9.0 > /dev/null && echo ok
# and the app reports the new version
docker run --rm ghcr.io/shatheitguy/it-vault:1.9.0 cat VERSION
```
