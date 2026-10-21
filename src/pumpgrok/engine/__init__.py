"""Screening engine: monitor, analyzer, scoring, reputation, exits, watcher, agents, pipeline, tune.

Also edge-triggered alert transitions (``alerts``) for the supervisor.

Ported from the retired oracle ``src/`` (pin 409e74c, docs/VENDOR_PIN.md;
R53). Every module runs on the injected clock with seeded randomness only,
so a Phase 4 replay reproduces each decision from the fixture alone (R27).
No trade subscription exists anywhere here: the monitor sends
``subscribeNewToken`` only (R45, R46).
"""
