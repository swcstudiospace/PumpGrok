"""Settings section modules, grouped by domain; config/settings.py composes them into Settings.

- ``core``: run mode, data and RPC ingress, LLM and quote endpoints, wallet allowlist.
- ``engine``: launch-monitor filter, scoring, exit rules and safety thresholds.
- ``ops``: process state paths, alert destinations and the health bind.

A new section is one class in one of these modules plus one import and one field line in
config/settings.py. Never edit a PRE-v4 section: its digest is pinned by the surface test.
"""
