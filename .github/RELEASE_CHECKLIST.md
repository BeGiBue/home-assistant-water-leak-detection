# Release checklist

This repository uses one generic, validation-gated release workflow:
`.github/workflows/release.yml`.

## Before publishing

- Update `custom_components/water_leak_detection/manifest.json`.
- Update `VERSION` in `custom_components/water_leak_detection/const.py`.
- Update the project version in `pyproject.toml`.
- Update `README.md` current release.
- Add the new version to `CHANGELOG.md`.
- Add `RELEASE_NOTES_<version>.md`.
- Keep `integration_type: "service"`.
- Keep the AGPL-3.0-only license metadata consistent.
- Run the complete repository test and validation suite.
- Obtain the required independent review for safety-relevant changes.

## Publishing

Use a final commit with the exact subject:

`Release <version>`

A push of that commit to `main` triggers the generic release workflow. The workflow:

1. runs the shared validation workflow,
2. verifies manifest, constants, pyproject, README, changelog, release notes, integration type and license,
3. creates or verifies an immutable-by-convention tag at the exact validated commit,
4. creates or verifies the GitHub Release using `RELEASE_NOTES_<version>.md`,
5. deletes only non-main branches whose tips are already ancestors of the released commit.

The helper script `.github/release_checked_commit.sh` refuses to accept an existing release tag that points at a different commit.

## Manual rerun

The same workflow can be started with `workflow_dispatch`. Supply the exact version already present in the checked-out release commit.

## After publishing

- Verify the GitHub Release exists and its tag points to the intended release commit.
- Verify HACS sees the new release.
- Verify the tagged manifest still reports `integration_type: "service"`.
- Keep unmerged branches; merged branches are removed automatically after a successful release.
