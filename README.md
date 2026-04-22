# personal-advocacy-toolkit

> **Status:** scaffolding only. Phase 0 of the plan at
> `.claude/plans/advocacy-toolkit/` is complete; Phases 1–5 (tool porting,
> synthetic case, new tools, skills, documentation) are not yet written.
> Nothing in this repo is functional or reviewed yet.

## What this is

You have a situation — a bad-faith insurance claim, a surprise medical bill,
a harassment campaign, a landlord trying to retaliate, a debt collector who
won't follow the rules, a scam that took your money. There are people and
offices whose job it is to help: regulators, consumer-protection advocates,
attorneys, journalists. They can only help you if you hand them something
they can act on.

This toolkit helps you organize digital evidence with forensic integrity,
understand what's happening in your situation, and package the result in
the form the right helper needs.

## What this isn't

- **Not legal advice.** Nothing here tells you what to argue or predicts an
  outcome in your specific case.
- **Not a substitute for counsel.** When you need a lawyer, hire one.
- **Not a litigation automation platform.** There are other projects for that
  (Document Assembly Line, Docassemble); this one handles the *pre-filing*
  evidence-organization step those projects generally assume has already
  happened.

The thesis: **do the legwork so whoever helps you can actually help you.**

## Situations it fits

- Insurance bad-faith / claim handling
- Medical balance-billing and surprise bills
- Consumer scams (romance, crypto, impersonation, fake invoices)
- Harassment and cyberbullying
- Landlord retaliation / habitability disputes
- Debt-collector abuse (FDCPA)
- Employment retaliation

The framework generalizes further; these are just the situations the
initial playbooks cover.

## 60-second demo

*(Not yet functional — coming in Phase 5.)*

```sh
git clone <this-repo> advocacy-toolkit
cd advocacy-toolkit/examples/mustang-in-maryland
# ... walkthrough steps ...
```

See `examples/mustang-in-maryland/WALKTHROUGH.md` once it exists.

## For tech-minded evaluators

If you're from Suffolk LIT Lab, United Policyholders, LSC TIG, or a
civic-legal-tech group: the interop story is in
`docs/concepts/evidence-integrity.md` and the packet pipeline in
`scripts/packet/`. The packet assembler is a plausible upstream feed into
Document Assembly Line / Docassemble.

## License

MIT — see [LICENSE](LICENSE).
