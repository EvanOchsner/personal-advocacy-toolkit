# Chain of custody

"Chain of custody" means: for every piece of evidence, you can show
where it came from, when it entered your possession, and that nothing
has happened to it since that you haven't recorded. A regulator or
attorney needs to see that chain before they will rely on your
documents.

This toolkit builds the chain out of four sources that a third party can
independently verify. `scripts/provenance.py` joins all four into a
single JSON report that a non-technical reader can skim.

## The four sources

### 1. The SHA-256 manifest

Proves the contents of each file have not changed. See
[evidence-integrity.md](./evidence-integrity.md).

### 2. Provenance snapshots (xattrs + mtimes)

Proves where a file came from, when applicable. On macOS these snapshots
preserve the `kMDItemWhereFroms` URL that Safari or Mail wrote when you
downloaded the file, along with quarantine timestamps. On any platform
they preserve file size and modification time. See the
`provenance_snapshot.py` entry in
[evidence-integrity.md](./evidence-integrity.md).

### 3. Git history

Proves when a file entered your possession and who added it. `git log
--follow -- <file>` gives a signed (if you sign commits) timeline. If
the repo is pushed to a remote, the remote's logs give an independently
verifiable timestamp that you cannot backdate.

### 4. Pipeline metadata sidecars

When the toolkit transforms a file (e.g. an `.eml` email is converted to
a normalized JSON and then to a plain-text `.txt`), each transformation
leaves a `<file>.meta.json` sidecar recording: the input's hash, the
tool version, the timestamp, and any parameters used. A reader can
reconstruct the pipeline without trusting the author.

## Two views: per-file and bundle

### Per-file deep dive

```
python -m scripts.provenance PATH
```

Surfaces six sections for one file: Identity, Git trail, Hash manifest,
Download provenance, Pipeline provenance, Verdict. This is the "what do
we know about this specific exhibit?" tool. Add `--forensic` for a
structured YAML version suitable for a regulator or attorney handoff —
the YAML emitter is stdlib-only, so the recipient doesn't need to
install PyYAML to read it.

The Pipeline section is config-driven
(`data/pipeline_dispatch.yaml`): for an email, it walks to the sibling
JSON and surfaces Message-ID + headers + extraction metadata; for a
policy-catalog PDF it surfaces the README mentions; for a legal-
research artifact it surfaces the YAML frontmatter from the sibling
`.md`. Add a handler there to cover a new content type.

### Whole-packet attestation

```
python -m scripts.provenance_bundle --manifest M --out report.yaml
```

Runs the per-file tool over every entry in a SHA-256 manifest and
concatenates the results into one YAML attestation document. This is
the single document you hand to an attorney or regulator alongside the
evidence tree. Everything in it is independently verifiable: they can
re-hash the file, re-read xattrs from a copy of the repo, pull the
commit from a git remote, and inspect the sidecar.

## What a reviewer looks for

When a regulator, attorney, or journalist skims the report they are
asking three questions, in order:

1. **Does the file match the manifest?** If not, stop — the author
   changed something without a record.
2. **Does the first commit date line up with the claim?** If the author
   is telling you they received the denial letter on September 1 but the
   PDF was first committed on September 15, that is a question worth
   asking (the gap may have a legitimate explanation, or may not).
3. **Does the source URL in xattrs match the author's story?** A PDF
   that the author claims came from the state insurance department but
   whose `kMDItemWhereFroms` points at a personal Dropbox is a flag.

The toolkit's job is to make those three questions answerable from the
report alone, without the reviewer having to take anyone's word.
