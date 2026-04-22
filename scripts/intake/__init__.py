"""Intake tools: situation classification, authorities lookup, deadline math.

All tools in this package are *reference material, not legal advice*. CLI
output from these modules always carries an explicit disclaimer. See each
submodule for details:

- situation_classify: questionnaire -> case-intake.yaml + situation slug.
- authorities_lookup: (situation, jurisdiction) -> shortlist of regulators.
- deadline_calc: (situation, jurisdiction, loss_date) -> SOL / notice dates.
"""
