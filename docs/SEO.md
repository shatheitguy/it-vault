# Why the project site was not in Google, and what to do about it

The site at <https://shatheitguy.github.io/it-vault/> is live, returns 200,
carries a title, description, canonical URL, Open Graph tags and a sitemap,
and is not blocked by anything. Nothing on the page was stopping it. The
problem is that Google had no way to *find* it, and no way to find the
sitemap that would have told it the page exists.

## The two reasons

**1. Nothing links to it that a crawler will follow.**

A search engine discovers a URL by following a link to it. Every link that
currently points at this page is one Google is told to ignore:

| Where | Why it does not count |
| --- | --- |
| The repository's "About" website field | GitHub marks it `rel="nofollow"` |
| The `Site` badge in `README.md` | GitHub marks links in rendered markdown `rel="nofollow"` |
| `shatheitguy.in` | mentions `shatheitguy.github.io/it-vault` as plain text, not as a link |

So the repository is indexed -- the repo page and every release are in the
index -- and the project site, which is one hop away through nofollowed links
only, is not.

**2. `robots.txt` is at the wrong level, and it cannot be moved.**

A crawler reads `robots.txt` from the root of a host and nowhere else. This
site's file is served at `/it-vault/robots.txt`, so for
`shatheitguy.github.io` the file Google reads is `/robots.txt`, which answers
404. A 404 means "no restrictions", so nothing is being *blocked* -- but the
`Sitemap:` line, which is the one passive way a sitemap gets discovered, is
never seen.

This cannot be fixed from inside this repository. A project site does not own
its host root.

## What has been fixed here

- `robots.txt` now explains the above, so the next person does not assume it
  is doing work it cannot do.
- `sitemap.xml` carries a current `lastmod`.
- The page declares `robots: index, follow, max-image-preview:large,
  max-snippet:-1`. The first two are the defaults; the other two are not, and
  without them a result gets a thumbnail and a clipped snippet, which for a
  screenshot-led page is most of what it has to show.
- The page carries `SoftwareApplication` structured data: that it is
  software, that it is free, its licence, what it runs on, its version, its
  screenshot, its author. All of it was previously left for a crawler to
  infer from prose. `softwareVersion` is checked against `VERSION` by
  `tests/test_versions_agree.py`, so it cannot rot.

None of that makes Google *discover* the page. It makes the page worth
indexing once it does.

## What only you can do

**Do this first -- it takes two minutes and it is the whole fix.**

1. Open [Search Console](https://search.google.com/search-console) and add
   `https://shatheitguy.github.io/it-vault/` as a **URL prefix** property.
   Verify it with the HTML-tag method: Google gives you a
   `<meta name="google-site-verification" content="...">` tag. Paste it into
   `docs/index.html` next to the other meta tags and push. (No placeholder is
   committed here -- a wrong token fails verification and looks like a
   different problem.)
2. In Search Console, use **URL inspection** on that address and press
   **Request indexing**. This is the one action that does not depend on a
   crawler finding a link.
3. Submit `https://shatheitguy.github.io/it-vault/sitemap.xml` under
   **Sitemaps**. With no host-root `robots.txt`, this is the only way it gets
   read.

**Then give it one real inbound link.** On `shatheitguy.in`, where IT-Vault
is described, make `shatheitguy.github.io/it-vault` an actual `<a href>`
rather than plain text. That site is indexed, so the link is a discovery path
Google will follow, and it is worth more than every nofollowed GitHub link
combined.

**Optional, and the permanent fix for `robots.txt`:** put the site on a
subdomain you control -- `vault.shatheitguy.in`, say. Add a `CNAME` file to
`docs/` containing the hostname, point a DNS CNAME record at
`shatheitguy.github.io`, and set the custom domain in the repository's Pages
settings. The site then owns its host root, so `robots.txt` and `sitemap.xml`
sit where a crawler looks for them, and it inherits the trust of a domain
that is already indexed. Remember to update the canonical URL, the Open Graph
URL, the sitemap and the JSON-LD if you do this.

## Realistic expectations

Getting listed at all takes days to a couple of weeks after indexing is
requested. Ranking for anything competitive ("IT asset management") takes
inbound links, not tags: a listing on
[awesome-selfhosted](https://github.com/awesome-selfhosted/awesome-selfhosted),
an r/selfhosted post, or a mention in someone's newsletter will each do more
than any change to this page can.
