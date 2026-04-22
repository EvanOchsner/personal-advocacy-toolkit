"""Publication safety tools: PII scrubbing, PDF redaction, metadata stripping.

Every tool in this package has a mandatory post-check. The post-check is the
core defense: a detector can miss a case, but the post-check reads the final
artifact and fails loudly if a banned term survived. Treat the post-check as
the primary contract; the scrubber is the convenience.
"""
