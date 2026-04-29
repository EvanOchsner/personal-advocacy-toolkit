# Tone modes

Two registers: **lawyer mode** and **casual mode**. Knowing when to use
which is more important than the writing quality of either one on its
own.

This page exists because the single most common way a lay
complainant's packet gets dismissed is not for weak facts — it's for a
tone mismatch that makes the reviewer quietly discount the whole
document.

## Lawyer mode

Careful, precise, on-record. What goes in:

- Written artifacts anyone outside your household will read: complaint
  narratives, position letters, demand letters, FOIA requests,
  preservation-of-evidence letters, correspondence with the
  counterparty.
- Anything that may be attached as an exhibit.
- Anything that may be quoted back to you under oath.

Style rules:

- **Against the counterparty's own words, not against statute
  directly.** If your insurer says "non-customary charges," your
  complaint says "the insurer's asserted 'non-customary charges'
  characterization is inconsistent with the agreed-value endorsement at
  policy inception" — not "they are breaking the law."
- **Cite the contract clause, then the statute, then the case law,** in
  that order. Most disputes resolve on the contract; statutes matter
  when the contract is ambiguous.
- **Never speculate about motive on the record.** "Inconsistent with
  the endorsement" does the work of "acted in bad faith" without
  locking you into a litigation theory you aren't ready to prove.
- **Every factual claim is sourced back to an exhibit.** If you can't
  point to the email, letter, or photo that proves it, it doesn't go
  in lawyer-mode writing.
- **Dates are ISO-8601.** "2025-03-15," not "March 15" — unambiguous,
  sortable, machine-readable by a reviewer's import tool.

## Casual mode

Normal-person-to-normal-person. What goes in:

- Verbal conversations: agent calls, shop calls, escalation requests.
- Internal reasoning: working notes, draft-zero outlines, your own
  private summary before you start writing for the record.
- Claude Code sessions when you are figuring out what you actually
  think, before you write it up formally.

Style rules:

- **Say what you actually mean.** Lawyer mode may phrase something as
  "the insurer's conduct is inconsistent with the agreed-value
  endorsement." Casual mode, internally, can say "they're trying to
  re-underwrite the policy after the loss." Both are useful; only the
  first belongs on the record.
- **Casual mode is where the narrative gets built.** You almost
  always write casual-mode first, then rephrase into lawyer mode for
  filing. Skipping the casual-mode step is how packets end up wooden
  and hard to read.

## The read-aloud test

Before any lawyer-mode document leaves your drafts directory:

1. Read it aloud to yourself, or ideally to a friend who is not
   involved.
2. At every sentence, ask: would I say this with a court reporter
   typing?
3. At every claim, ask: can I point to the exhibit that proves this?

If any sentence fails (1), rephrase. If any claim fails (2), remove it
or add a source-cite.

## Scripts are scaffolds, not recitation

The letter templates under `templates/letter-templates/` and the Jinja
rendering in `scripts/letters/draft.py` produce a starting draft, not
a final document. Lawyer mode means **you** own the words that go out
under your name. Treat rendered templates as scaffolding: fill in the
facts, then rewrite the sentences in your own voice before sending.

A template that someone else wrote is a tell. A reviewer who reads 200
complaint narratives per year can spot one two paragraphs in. Use the
template to remember everything you need to cover; don't use it as the
document.

## Tone and the dashboard

The `case_dashboard.py` tool prints a `[lawyer | casual]` tag next to
every draft, based on the `tone.default_written` / `tone.default_verbal`
fields in `case-intake.yaml`. This is not enforced — it's a reminder.
A packet with a casual-mode demand letter slipped into it is worse
than one with no letter at all.

## See also

- [`.claude/skills/tone-modes/SKILL.md`](../../.claude/skills/tone-modes/SKILL.md) —
  invokable from a Claude Code session for live tone coaching.
- [`templates/letter-templates/`](../../templates/letter-templates/) —
  the Jinja templates, readable in plain text.
