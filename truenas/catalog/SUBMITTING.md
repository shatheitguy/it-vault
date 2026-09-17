# Getting IT-Vault into the TrueNAS catalogue

Two different things, and it is worth not confusing them.

**Installing it today** needs nothing from anybody: TrueNAS Apps (24.10 and
later) runs Docker Compose, so Apps → Discover Apps → **Custom App → Install
via YAML** and `truenas/docker-compose.yaml` is a complete install. That file
is for pasting.

**Appearing in Discover Apps**, so other people find it by searching, means
getting listed in the community train. That is a pull request to
[truenas/apps](https://github.com/truenas/apps), and `it-vault/` next to this
file is that app, ready to go in.

## What is here

```
it-vault/
├── app.yaml                              metadata: title, version, icon, categories
├── ix_values.yaml                        images and constants
├── questions.yaml                        the install form TrueNAS renders
├── README.md                             one paragraph, as they ask for
└── templates/
    ├── docker-compose.yaml               Jinja2, rendered by their ix_lib
    └── test_values/basic-values.yaml     the CI's test scenario
```

Two files are **not** here because their tooling generates them:
`templates/library/` (vendored by `devbox run copy-lib`) and `item.yaml`
(written by their CI). Do not hand-write either.

The app is modelled on their own `bookstack` app, which has the same shape as
this one: a single web container, MariaDB beside it, a permissions container,
one published port and a handful of persistent paths.

## Submitting it

```bash
gh repo fork truenas/apps --clone           # or fork in the UI and clone
cd apps
git checkout -b add-it-vault

cp -r /path/to/it-vault/truenas/catalog/it-vault ix-dev/community/it-vault

# vendors the render library and fills lib_version_hash in app.yaml
devbox run copy-lib

# renders the template against basic-values.yaml and validates the result;
# this runs in a container, so Docker has to be up
./.github/scripts/ci.py --app it-vault --train community --test-file basic-values.yaml

git add ix-dev/community/it-vault
git commit -m "Add IT-Vault to the community train"
git push -u origin add-it-vault
gh pr create --repo truenas/apps --title "Add IT-Vault (community)"
```

Then in the PR body, link the project and say what it is in two sentences.
Their reviewers will ask for the icon and screenshots as URLs; they upload
them to their own CDN and hand you back the final `icon:` and `screenshots:`
values to put in `app.yaml`. The placeholders in there now point at where
those files will live (`media.sys.truenas.net/apps/it-vault/...`) — expect to
change them once, on request.

## What to keep in step afterwards

A catalogue entry is a second copy of your configuration, and copies rot.
`tests/test_nas_templates.py` in this repository holds the parts that matter:

- `app_version` and the pinned image tag both equal `VERSION`
- the image is ours and the tag is not `latest` — a catalogue entry that moves
  under the user is not reproducible
- every environment variable the template sets is one `app.py` actually reads
- all three data paths are mounted
- the app still brings its own MariaDB and still waits for it to be healthy

Their rules on top of that: bump `version` in `app.yaml` on **every** change to
the app directory (it is the packaging version, not the software's), and
`app_version` whenever the image tag moves.

## Why the catalogue copy brings a database and the pasteable one does not

The compose file in `truenas/` and the catalogue app are deliberately
different. The catalogue install has a form, so it can ask for two passwords
and stand MariaDB up for you — nobody should have to build a database before a
one-click install works. The pasteable file is read by whoever pastes it, and
the comments in it can explain the choice.
