# Water Leak Guard 1.1.0

Version 1.1.0 is a feature release focused on clearer detector boundaries, earlier recognition of stable Low Flow, and safer seasonal learning of legitimate high water use.

## Static High Flow threshold

High Flow now uses the configured High threshold as its authoritative detector boundary.

- Default High threshold: **600 L/h**.
- The threshold remains user-configurable in Expert settings.
- Adaptive learning no longer raises or lowers High.
- High still becomes ACTIVE after **45 minutes or 500 litres**, whichever occurs first.
- The physical High reset remains unchanged.
- High Flow bypass still suppresses only High Flow; Burst detection remains active.

This keeps the alarm boundary predictable while allowing adaptive learning to focus on Burst context.

## Stable Low Flow detection

Low Flow now has an additional stability-based early path while the existing normal duration path remains available as a safety net.

With defaults:

- normal Low Flow path: **60 minutes**,
- stable early path: **30 minutes**,
- stability window: **15 minutes**,
- at least **90%** of confirmed window time must be inside the stability band,
- tolerance is the larger of **±20 L/h** or **±10%** around the time-weighted median,
- default Low reset is now **3 minutes** below the quiet threshold.

Explicitly stored older reset values remain preserved. Legacy configurations with shorter Low detection times receive compatible derived stability defaults without destructive migration.

## Seasonal learning of normal High Flow

Legitimate High Flow use can now be learned without making the static High detector adaptive.

A safely completed High MONITORING episode is first stored only as a candidate. It becomes normal learning evidence only when at least **three comparable episodes** occur inside the existing rolling learning window.

The confirmation rule is:

`max_peak <= min_peak * 1.15`

The default learning window remains **30 days**. Pending and confirmed High evidence ages out with the same window, so older seasonal behavior naturally loses influence.

Examples such as several similar showers can therefore become part of the normal Burst reference, while a single unusual high-flow event cannot immediately raise the learned context.

## Safety rules for High learning

A High episode is never admitted as normal learning evidence if it encounters:

- High ACTIVE,
- Burst MONITORING or ACTIVE, including Rapid Rise candidates,
- another active leak alarm,
- High Flow bypass,
- unavailable, unknown, invalid or non-finite flow,
- a real excluded measurement/evidence gap,
- a source rebind,
- an interrupted in-progress episode across restart.

After every Home Assistant startup or restore, High learning stays blocked until the full configured physical High reset has been observed using valid measurement evidence. A brief zero-flow or sub-High report is not enough.

Confirmed High samples retain their original completion timestamps and enter the existing P95, short/long-reference and confidence model. They can influence only the existing adaptive Burst context; **High itself stays static**.

## Persistence and seasonal history

Pending and confirmed High learning history:

- survives restart once an episode has been safely completed,
- remains bound to the existing F15 clock-rollback protections,
- is deduplicated,
- is pruned by the configured learning window,
- keeps only the newest **4096** valid in-window High-history records,
- never restores confirmed High history without a matching admitted LearningSample.

Running High-learning episodes themselves are intentionally not persisted.

## Compatibility

- Existing configuration is preserved.
- No new Home Assistant entities are required.
- No new user-facing options are required for the three-confirmation / 15% gate.
- Technical domain remains `water_leak_detection`.
- Integration type remains `service`.
- Acknowledgement still does not end the physical leak state or an existing Water Shut Off request.
- High Flow bypass still never disables Burst Leak detection.

## Validation

The final reviewed repository state passed:

- **995 repository tests**,
- the focused High-Normal-Learning suite with **136 tests**,
- Ruff,
- Home Assistant hassfest,
- Python compile validation,
- JSON/YAML validation,
- release diff checks.

The independent final follow-up review additionally ran **49 external tests** and reported:

- Critical: **0**
- High: **0**
- Medium: **0**
- Low: **0**

Both previously identified High-learning merge blockers were independently verified as closed.

## Still open

F04 / Rapid Rise remains a separate detector-design topic. This release intentionally does not redesign Rapid Rise.

## License

This release is distributed under the **GNU Affero General Public License v3.0 only (AGPL-3.0-only)**.
