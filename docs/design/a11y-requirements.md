# A11y requirements - PumpGrok operator console (T1482-ux, PROVISIONAL lofi)

Target: WCAG 2.2 AA. Tokens v1.0.0 (docs/design/tokens.json).
Verdict source: shared_verdict over severities below (see result).

| Area | WCAG 2.2 SC | Threshold | Measured (this run) | Status |
|---|---|---|---|---|
| Text contrast default | 1.4.3 | 4.5 | 17.73 (ux_contrast #111827/#ffffff) | pass |
| Text contrast muted | 1.4.3 | 4.5 | 7.0 (ux_contrast #595959/#ffffff) | pass |
| On-primary text | 1.4.3 | 4.5 | 6.18 (ux_contrast #ffffff/#1a56db) | pass |
| Status success | 1.4.3 | 4.5 | 5.69 (ux_contrast #067647/#ffffff) lowest | pass |
| Status danger | 1.4.3 | 4.5 | 6.57 (ux_contrast #b42318/#ffffff) | pass |
| Status warning | 1.4.3 | 4.5 | 7.48 (ux_contrast #7a4a00/#ffffff) | pass |
| Focus indicator | 1.4.11 | 3.0 | 6.18 lowest (ux_focus_contrast_check #1a56db on #ffffff) | pass |
| Focus order/visibility | 2.4.3, 2.4.7 | all interactive ids in focus_order | ux_spec_completeness_check complete true, 7/7 screens | pass |
| Target size | 2.5.8 | 24 CSS px (44 specified) | ux_target_size_check compliant true, 7/7 meet minimum | pass |
| Spacing grid | design policy | multiples of 4px | ux_spacing_scale_check on_scale true | pass |
| Token names | design policy | kebab dot-path, depth 4 | ux_token_name_check conforming true | pass |
| Breakpoints | design policy | ascending, base 0 | ux_breakpoint_order_check valid true | pass |
| Motion | 2.2.2 bound + reduced-motion policy | max 300ms, variant required | ux_motion_duration_check compliant true, max 200ms | pass |
| State coverage | design policy | default/loading/error/empty/success | ux_state_coverage_check complete true; ux_spec_completeness_check complete true 7/7 | pass |
| AC trace | design policy | 100% AC-001..AC-030 covered | ux_ac_trace_check coverage_pct 100, traced true | pass |
| Tone scale ramp | 1.4.3 | monotonic luminance | not audited: no tone ramp defined in tokens.json | not audited |
| ASCII/i18n (NFR-A1/I1) | design policy | 0 non-ASCII bytes in operator docs/errors | spec mandates single-line ASCII errors, ISO8601 UTC; verified by A08 check-sh, not by A04 tools | not audited by A04 |

Initial token finding (auto-revised, non-brand): color.text.inverse
#ffffff on color.background.primary measured 1.0 by
scripts/ux_tokens.py (python fail, 1 major finding UF-001); the token
was removed and on-primary text is specified as #ffffff on
#1a56db measured 6.18. Re-run: python and bun twins both pass,
0 findings.

Paper-only constraint: no screen asks for a seed phrase or private
key; SCR-SafetyPaperOnly renders live-refusal exit 3 with 9 unmet
precondition lines (AC-019).
