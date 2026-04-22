# Playbook: insurance dispute (worked: Maryland)

> **This is reference material, not legal advice.** It describes
> mechanics and points at authorities. It does not tell you what to
> argue in your specific case. Verify every deadline and every
> citation with counsel licensed in your state.

This is the *worked* playbook: Maryland is populated with real
authorities and real deadline hooks. The synthetic
[`Mustang-in-Maryland`](../../examples/mustang-in-maryland/) case
exercises every mechanic described below.

For other states: the mechanics transfer, but the authority names,
URLs, and deadline numbers must be confirmed in your state's
Department of Insurance and unfair-claims-practice statutes. Look up
the state's entry in [`data/authorities.yaml`](../../data/authorities.yaml);
if it's a stub, see the *populate-this* list at the bottom.

---

## What "insurance dispute" means here

First-party or third-party claims where the insurer's conduct — not
just the claim outcome — is the grievance. Typical shapes:

- **Auto total-loss** where the valuation is challenged.
- **Auto agreed-value / classic-vehicle** where the insurer tries to
  re-value at loss.
- **Property** (homeowners / renters) where coverage is disputed.
- **Health claim denial** where an out-of-network / medical-necessity
  denial is challenged.
- **Surprise moves** by the insurer during active negotiation:
  salvage transfer, claim closure without notice, lapse-of-coverage
  backdating.

The core mechanic is almost always the same: *the insurer's conduct is
inconsistent with the policy's own terms*. The packet argues the
counterparty's stated position against their own written agreement
first, statute second.

---

## The standard mechanics

### 1. Get the full policy form set

Insurer portals typically give you only the **declarations page**.
That is not the policy. The policy is the declarations + the master
form + every endorsement listed on the dec page.

For the synthetic Mustang case that's:

- `CIM-CLS-0000-0000` (declarations)
- `CIM-VEH-2023` (master classic-vehicle form)
- `CIM-AV-ENDT-2023` (agreed-value endorsement)
- `CIM-SALV-2023` (salvage / total-loss provisions)

**Where to get them:** your producer (agent). Email the agent requesting
the full current-form set with all endorsements. They are required to
provide it. Track the request in the correspondence manifest.

### 2. Build the three-layer correspondence set

Everything the insurer said in writing is exhibit material. Run each
`.eml` through:

```
python -m scripts.ingest.email_eml_to_json <input>  --out-dir evidence/emails/structured
python -m scripts.ingest.email_json_to_txt evidence/emails/structured --out-dir evidence/emails/readable
```

`raw/` keeps the RFC-5322 original; `structured/` is canonical JSON
the tools consume; `readable/` is what goes into the packet as an
exhibit.

### 3. Build a correspondence manifest

Narrow your entire inbox to just this dispute:

```
python -m scripts.manifest.correspondence_manifest \
  --config search.yaml --out correspondence-manifest.yaml \
  path/to/inbox.mbox
```

Search config is YAML. See
[`docs/concepts/correspondence-manifest-schema.md`](../concepts/correspondence-manifest-schema.md)
for the full schema.

### 4. Identify the core grievance

Most insurance disputes have more than one complaint but only one
*core grievance* — the one that is clean, well-documented, and hard
to defend. Lead the complaint with that; order the rest as
supporting.

For the synthetic Mustang case the core grievance is the **salvage
transfer during active negotiation** (2025-06-24), not the valuation
dispute. The valuation dispute is a contract-interpretation fight
the insurer can argue; the unauthorized salvage transfer is a
timeline fact that speaks for itself.

### 5. File with the state Department of Insurance

The state DOI is your first forum. Complaints are free, produce a
paper trail, and the insurer is typically required to respond within
a defined window.

**Maryland:** [Maryland Insurance Administration (MIA)](https://insurance.maryland.gov/Consumer/Pages/FileAComplaint.aspx).
MIA requires a signed consumer-complaint form plus supporting
exhibits as a single PDF (or per-exhibit uploads).

Run the packet build:

```
python -m scripts.packet.build complaint_packet/packet-manifest.yaml
```

Outputs a merged PDF plus per-exhibit standalone PDFs.

### 6. File parallel with CFPB / state AG (when applicable)

- **CFPB** — primarily for financial-products insurance (lender-placed
  insurance, credit insurance). Not all P&C disputes fit. Verify.
- **State AG consumer-protection** — fits when the insurer's conduct
  is deceptive-practice-shaped, not just contractual.

Run:

```
python -m scripts.intake.authorities_lookup --situation insurance_dispute --jurisdiction MD
```

to see the current shortlist for your state.

### 7. Compute deadlines

```
python -m scripts.intake.deadline_calc \
  --situation insurance_dispute --jurisdiction MD \
  --loss-date 2025-03-15
```

Returns the applicable SOL windows and notice deadlines, each tagged
`[VERIFY WITH COUNSEL]`. Do not file on the machine's math.

### 8. Hire counsel when the dispute crosses the contract

Signals that it's time:

- Regulator closes the complaint without relief.
- Disputed amount exceeds small-claims threshold in your state.
- Insurer invokes the appraisal clause and you need an umpire.
- Bad-faith / unfair-claims-practice statutory damages are plausibly
  in play.
- SOL / notice-of-loss windows are inside ~90 days.

The toolkit is designed to make you a **better client**, not your own
attorney. The forensic audit trail, organized exhibits, and
provenance report shorten the intake call dramatically.

---

## Worked Maryland specifics

Populated in `data/authorities.yaml` and `data/deadlines.yaml` as of
writing. Re-run the lookup tools for current values.

**Lead authority:** Maryland Insurance Administration (MIA),
`https://insurance.maryland.gov/`.

**Secondary authorities:**
- CFPB (financial products).
- Maryland Attorney General — Consumer Protection Division.
- FTC ReportFraud (when deceptive practices accompany the dispute).

**Relevant Maryland statutory framework** (confirm with counsel):
- Md. Insurance Code — unfair-claims settlement practices (Title 27).
- Md. Insurance Code — cancellation / nonrenewal notice requirements.
- Common-law bad-faith in auto first-party contexts.

**MIA complaint form mechanics:**
- Consumer Complaint Form + supporting documents.
- Insurer has a statutory response window to MIA's inquiry.
- MIA does not adjudicate contract disputes but can find unfair-claims
  practice violations.

---

## Worked California specifics

Populated in `data/authorities.yaml` and `data/deadlines.yaml` as of
writing. Re-run the lookup tools for current values — the data files
are the source of truth; this section describes the shape so a reader
knows what to expect.

**Lead authority:** California Department of Insurance (CDI),
`https://www.insurance.ca.gov/`. Consumer Hotline: 1-800-927-4357.
CDI enforces the California Fair Claims Settlement Practices
Regulations (CCR Title 10, Chapter 5, Subchapter 7.5, §§ 2695.1 et
seq.), which govern insurer conduct — acknowledgment windows, claim
decision windows, and unfair-practice definitions.

**Secondary authorities:**
- CFPB (financial-products insurance).
- California Attorney General — Consumer Protection Section (overlaps
  via the Unfair Competition Law, Cal. Bus. & Prof. Code § 17200).
- State Bar of California — Lawyer Referral Service.
- FTC ReportFraud (when deceptive practices accompany the dispute).

Run the lookup tool to see the current shortlist:

```
python -m scripts.intake.authorities_lookup --situation insurance_dispute --jurisdiction CA
```

**Relevant California statutory framework** (confirm with counsel):
- Cal. Code Civ. Proc. § 337 — 4-year SOL on written contracts
  (first-party insurance claims are contract-based).
- Cal. Ins. Code § 790.03(h) — Unfair Claims Settlement Practices
  (statutory anchor for the CCR regulations below).
- Cal. Code Regs. tit. 10, § 2695.5 — claim acknowledgment window
  (15 calendar days).
- Cal. Code Regs. tit. 10, § 2695.7 — claim acceptance/denial window
  (40 calendar days after proof of claim).
- Cal. Ins. Code § 2071 — statutory fire-policy form; 60-day proof of
  loss floor.
- Common-law bad-faith in first-party contexts
  (*Gruenberg v. Aetna*, *Egan v. Mutual of Omaha*).

**Policy suit-limitation caveat:** California policies often contain
contractual suit-limitation clauses (one year from inception of loss
is common for fire-line products under § 2071). The statutory 4-year
SOL does not override a shorter policy clause that is enforceable on
its face. Confirm the policy's own clause before relying on the § 337
window.

Compute the concrete windows for a given loss date:

```
python -m scripts.intake.deadline_calc \
  --situation insurance_dispute --jurisdiction CA \
  --loss-date 2025-03-15
```

Output tags every date `[VERIFY WITH COUNSEL]`. Do not file on the
machine's math.

---

## Populate-this list for other states

To convert your state from stub to populated:

- [ ] State Department of Insurance: name, short code, complaint
      intake URL, mailing address.
- [ ] State AG consumer-protection division: name, URL, filing
      process.
- [ ] State unfair-claims-practice statute citation (confirm with
      counsel).
- [ ] SOL for first-party contract action against insurer.
- [ ] SOL for bad-faith tort (if recognized in your state).
- [ ] Notice-of-loss deadline from the policy.
- [ ] Appraisal-clause mechanics under state case law.
- [ ] Any state-specific consumer-side nonprofits
      (United Policyholders state chapter, etc.).

Contributions welcome via PR against `data/authorities.yaml`,
`data/deadlines.yaml`, and this playbook. See
[CONTRIBUTING.md](../../CONTRIBUTING.md).

---

## See also

- Worked example:
  [`examples/mustang-in-maryland/WALKTHROUGH.md`](../../examples/mustang-in-maryland/WALKTHROUGH.md)
- Tutorial:
  [`docs/tutorials/03-understanding-the-situation.md`](../tutorials/03-understanding-the-situation.md)
- Authorities concept:
  [`docs/concepts/authorities-and-regulators.md`](../concepts/authorities-and-regulators.md)
