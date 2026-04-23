---
name: Bug report
about: Something is broken or behaves differently than documented
title: "[bug] <short description>"
labels: bug
assignees: ''
---

**Thanks for reporting.** Before you open this, please confirm:

- [ ] The bug is reproducible on a fresh clone with `uv sync`.
- [ ] You are running Python 3.11 or 3.12.
- [ ] You have read the tool's docstring (`uv run python -m scripts.X --help`
      or the script header) and confirmed the behavior is not
      as-designed.

**Please do not include real case material.** Reproduce the bug
against `examples/mustang-in-maryland/` or a minimal synthetic
fixture. If the bug only reproduces with your private data, describe
the shape of the data, not its content.

## What happened

A clear description of what went wrong. Copy any error output
verbatim. If the tool wrote a partial output, include the stdout/
stderr and the filename.

## What you expected

What you thought the tool would do (cite the docstring or tutorial
line if the docs implied different behavior).

## Reproduction

```sh
# Exact commands, run against examples/mustang-in-maryland/ or a
# minimal reproducer. Include `pwd` at the top so we know where you
# were.
pwd
uv run python -m scripts.X --foo bar
```

## Environment

- OS: macOS / Linux / Windows + version
- Python: `python --version`
- Toolkit: `git rev-parse HEAD`
- Any optional deps installed (`playwright`, `libreoffice`,
  `git-filter-repo`):

## Additional context

Screenshots, log excerpts, hunches about what might be wrong. If the
bug is in a script that has a post-check (pdf_redact, exif_scrub,
history_sanitizer), please call out whether the post-check caught it
or missed it — the post-checks are the primary test target for those
tools.
