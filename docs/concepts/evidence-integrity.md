# Evidence integrity

When you are organizing documents for a dispute — whether you are headed
to a regulator, an attorney, a reporter, or small-claims court — the
single most important property of your evidence is that a stranger can
tell it has not been quietly edited since you collected it. This page
explains how the toolkit gives you that property without requiring you
to trust anyone's word, including your own.

## Three layers, one guarantee

The toolkit builds evidence integrity out of three independent checks.
Each one can be verified by someone who has never met you.

### 1. SHA-256 hash manifest

`scripts/evidence_hash.py` walks your evidence tree and writes a plain
text file (`evidence/MANIFEST.sha256` by default) that lists every file
and its SHA-256 digest, sorted by path:

```
a94a8fef8c17a0[…]  letters/2025-09-01_notice-of-claim.pdf
c0535e4be2b79f[…]  photos/IMG_0142.jpg
```

A SHA-256 digest is a 64-character fingerprint. Changing even one byte
of a file changes the fingerprint completely and unpredictably. A third
party can re-run `shasum -a 256` on any file and compare to the manifest
to prove the file has not been altered.

Regenerate the manifest any time you add a new file:

```
python -m scripts.evidence_hash
```

Verify (without rewriting) that every tracked file still matches:

```
python -m scripts.evidence_hash --verify
```

Verify **and** flag any untracked files that appeared under the evidence
root since the last run:

```
python -m scripts.evidence_hash --check
```

The manifest is a regular text file. Attorneys and regulators can open
it in any editor. There is no proprietary format to worry about.

### 2. Pre-commit immutability hook

The manifest only matters if you don't silently rewrite it. The
pre-commit hook (`scripts/hooks/pre_commit.py`) refuses git commits that
would modify or delete any file under a protected path — `evidence/` by
default, anything you configure in `advocacy.toml` otherwise.

New files under the protected path are allowed. Edits and deletions are
refused. If you genuinely need to remove a file (e.g. a redaction with a
public notice), set `ADVOCACY_ALLOW_EVIDENCE_MUTATION=1` for that one
commit. The override is an environment variable, not a command-line
flag, because it's meant to show up in shell history and CI logs so
future-you can explain what happened.

Install the hook into a case workspace:

```
scripts/hooks/install_hooks.sh
```

Or, if the workspace already uses the `pre-commit` framework, the
repo's `.pre-commit-config.yaml` already wires the same Python entry
point as a local hook.

### 3. xattr / provenance snapshots

Some forensic information lives outside the file contents. On macOS,
Safari and Mail record the original source URL and the download
timestamp as extended attributes (xattrs) on every file they write:

- `com.apple.metadata:kMDItemWhereFroms` — the URL the file came from.
- `com.apple.quarantine` — the timestamp of the first launch prompt.

Git does not track xattrs. If you commit a PDF downloaded from your
insurer's web portal, the URL that proves where it came from does not
travel with it. `scripts/provenance_snapshot.py` captures every file's
size, mtime, SHA-256, and xattrs into a timestamped JSON snapshot under
`provenance/snapshots/`. The snapshot directory is intended to be
committed, so the xattr evidence becomes a permanent part of the repo.

Capture a snapshot:

```
python -m scripts.provenance_snapshot
```

On Linux, xattrs will usually be empty; that's fine. The snapshot still
records size and mtime, which remain useful when combined with the hash
manifest and git history.

## What this does not do

- It does not prove a file is authentic — only that it has not changed
  since you added it. If someone hands you a forged PDF and you hash it,
  you have a verifiable record of a forgery.
- It does not defeat a sophisticated local attacker who rewrites history.
  A regulator with subpoena power, however, can verify your git history
  against a hosted remote and your timestamps against the platforms that
  produced the xattr URLs.
- It does not encrypt anything. Evidence-integrity and confidentiality
  are separate problems; see the `pii-and-publication` note for the
  latter.

See also: [chain-of-custody.md](./chain-of-custody.md) for how these
three layers compose into a single forensic record.
