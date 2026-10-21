"""Screening engine: monitor, analyzer, scoring, reputation, exits, watcher.

Ported from ``vendor/grokbot-pumpfun/src/`` (oracle, kept byte-identical per
R53). Every module runs on the injected clock with seeded randomness only,
so a Phase 4 replay reproduces each decision from the fixture alone (R27).
No trade subscription exists anywhere here: the monitor sends
``subscribeNewToken`` only (R45, R46).
"""
