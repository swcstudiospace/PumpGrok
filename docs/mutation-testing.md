# Mutation testing smoke (QLT-08, G-02)

`make mutation-smoke` runs [mutmut](https://github.com/boxed/mutmut) 3.x over the risk and
execution math that decides money and limits. It is an on-demand smoke check. It is not part of
`make check`, `make test` or any CI job, so a surviving mutant never fails a build.

## Scope

Set in `[tool.mutmut]` in `pyproject.toml`:

| Source file | Why it is in scope |
|---|---|
| `src/pumpgrok/risk/limits.py` | position and exposure caps |
| `src/pumpgrok/risk/sizing.py` | order sizing from the risk budget |
| `src/pumpgrok/execution/curve_math.py` | bonding-curve buy and sell quotes |
| `src/pumpgrok/execution/fees.py` | fee and network cost arithmetic |

Mutants are generated only on lines the selected tests execute (`mutate_only_covered_lines`).
The selected tests are the direct unit tests for these modules:

- `tests/execution/test_curve_math.py`
- `tests/execution/test_paper_fill_model.py`
- `tests/characterization/test_vendor_risk.py`

Add a file to `pytest_add_cli_args_test_selection` only when it exercises the scoped module
directly. Broad selections such as `tests/risk` or `tests/execution` make each mutant run minutes
long and are not used.

## Run

```sh
make mutation-smoke
uv run mutmut results      # list survivors and killed mutants
uv run mutmut show <name>  # show the diff for one mutant
```

The target syncs the locked dev group and then runs `uv run mutmut run`. Each run copies
`src/pumpgrok` and `contracts/` into `mutants/` at the repository root. The copies are generated
and must not be committed; delete `mutants/` when you are done.

## Reading the result

A mutant is **killed** when a selected test fails under it and **survived** when every selected
test still passes. Survivors point at arithmetic or branches that no selected test pins. Treat
them as a list of tests to write, not as a score.

Recorded run (2026-11-03, branch `bot-02-risk/v4-p11-quality-foundation-ratchet`, base
`origin/main` at `3182763`): 102 mutants generated, 74 killed, 28 survived, exit code 0.

## Limits

- The selection is deliberately narrow. A killed mutant proves a selected test notices a change,
  nothing more.
- mutmut writes into `mutants/` in the repository root. That directory is not in `.gitignore`.
- Mutation testing is not gated in CI (CONTEXT, deferred ideas).
