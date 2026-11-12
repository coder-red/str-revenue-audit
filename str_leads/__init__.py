"""STR Owner Lead Finder — host-level lead scoring and outreach review queue.

Built on top of `str_audit` (the Listing Revenue Audit), which is imported and
reused untouched. Custom code in this package is limited, on purpose, to:
  * `score.py` — the transparent lead score (rule 7),
  * `pitch.py` — the pitch-drafting prompt that uses the audit's findings,
  * `store.py` — dedupe/status tracking of leads.

Everything else is orchestration or I/O.
"""

__version__ = "0.1.0"
