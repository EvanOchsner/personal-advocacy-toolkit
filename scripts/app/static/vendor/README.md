# Vendored third-party assets

Files in this directory are imported into the case-map viewer
(`scripts/app`) as static assets. They are served from `127.0.0.1`
under the same strict CSP as everything else; the browser does not
fetch anything from outside the server.

The CI airgap grep at `.github/workflows/ci.yml` (and the mirroring
test in `tests/test_case_map_server.py::test_no_external_urls_in_static_tree`)
**excludes this directory**. Minified third-party JS bundles contain
URL string literals (doc links, MathJax CDN references inside code
paths we do not invoke, XML namespace declarations) that are not
network calls. The runtime defenses — CSP `default-src 'self'`,
`connect-src 'self'`, `script-src 'self'`, plus the 127.0.0.1 bind —
are what actually prevent any external fetch.

## Each vendored asset is documented below.

If you add or replace a file in this directory, update this README in
the same change so the audit trail stays current.

---

### `plotly-basic.min.js`

- **Library:** [Plotly.js](https://plotly.com/javascript/) (basic bundle)
- **Version:** 2.35.2
- **Source URL:** https://cdn.plot.ly/plotly-basic-2.35.2.min.js
- **sha256:** `138c2e81014b979dc00867a93da55b7605a17495ee78dd7afb433b7f021dfcfa`
- **License:** MIT (https://github.com/plotly/plotly.js/blob/master/LICENSE)
- **Used by:** `scripts/app/static/js/plotly_timeline.js`

The "basic" partial bundle ships scatter, bar, and pie traces. The
case-map timeline only needs scatter, so this is the minimum viable
build (~1.0 MB).

To re-vendor, fetch the published artifact and verify the sha256:

```sh
VENDOR_DIR="$(git rev-parse --show-toplevel)/scripts/app/static/vendor"
PLOTLY_VERSION=2.35.2
curl -fsSL "https://cdn.plot.ly/plotly-basic-${PLOTLY_VERSION}.min.js" \
  -o "$VENDOR_DIR/plotly-basic.min.js"
shasum -a 256 "$VENDOR_DIR/plotly-basic.min.js"
```

If you need full Plotly (3D, geo, financial traces), swap the URL to
`plotly-${PLOTLY_VERSION}.min.js` (~3.5 MB) and update the sha256 here.
