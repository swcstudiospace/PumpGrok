# Phase 18 Plan Check

Verdict: FAIL, 0 blockers, 2 warnings, 2 advisories. Revision advised, execution not barred.

Covered: all 21 phase requirements mapped. Gate split in 18-02 and 18-05. Arm pairs with 72h default and 168h ceiling in 18-02. Signer core, fsync before send, no rebroadcast, UNKNOWN never retried in 18-03. Allowlist, signer blockhash, final-bytes verify in 18-04. Desk purity tightened INV-S-01 in 18-03 and 18-05. Amendment wait gates with stage nothing in 18-03, 18-04, 18-05, 18-06, 18-08, 18-09. Human gate in 18-07, owner applies and merges. Live exit 3 and both hash pins held. Seats verified against ownership.yaml. Waves 1 to 7 acyclic. No dishonest flags, red-first tests, no gateway imports.

WARNING 1 scope, plans 18-02, 18-03, 18-04, 18-05: 5 tasks each at the limit, though task 5 is receipt only. Fix: planner sign-off, or fold receipt into task 1.

WARNING 2 allowlist, plan 18-04: TransferChecked outside the wallet never named in tests though required. Fix: add it to the txpolicy test names.

Advisory: 18-07 planning PROJECT.md entry is compliant only via owner applies. Trading smoke pin file assumed from phases 11 and 12, matching depends_on.
