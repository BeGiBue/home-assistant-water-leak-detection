#!/usr/bin/env bash
# Only validation-gated manual workflows invoke publication. Protect release tags
# against force moves with GitHub Rulesets/Tag Protection for a full SHA guarantee.
set -euo pipefail
release_version="${1:?release version required}"
[[ "${2:-}" == "--target" && "${3:-}" == "$GITHUB_SHA" ]] || exit 1

resolve_tag() {
  if git ls-remote --exit-code --tags origin "refs/tags/${release_version}" >/dev/null 2>&1; then
    git fetch --no-tags origin "refs/tags/${release_version}" || exit 1
    tag_commit=$(git rev-parse 'FETCH_HEAD^{commit}') || exit 1
    [[ "$tag_commit" == "$GITHUB_SHA" ]] || {
      echo "Release tag does not point to checked commit ${GITHUB_SHA}." >&2
      exit 1
    }
    return 0
  else
    tag_status=$?
    [[ "$tag_status" == 2 ]] && return 2
    echo "Cannot verify remote release tag." >&2
    exit "$tag_status"
  fi
}

existing_tag=false
if resolve_tag; then existing_tag=true; else [[ "$?" == 2 ]] || exit 1; fi

release_error=$(mktemp)
trap 'rm -f "$release_error"' EXIT
existing_release=false
if gh release view "$release_version" --repo "$GITHUB_REPOSITORY" >/dev/null 2>"$release_error"; then
  existing_release=true
elif ! grep -Eqi 'release not found|HTTP 404|Not Found' "$release_error"; then
  cat "$release_error" >&2
  exit 1
fi
if $existing_release && ! $existing_tag; then
  echo "Existing release has no verified tag." >&2
  exit 1
fi

if ! $existing_tag; then
  # Atomic GitHub ref creation never updates an existing tag. A concurrent run
  # may win: both success and failure require rereading and verifying the ref.
  if ! gh api --method POST "repos/${GITHUB_REPOSITORY}/git/refs" \
      -f "ref=refs/tags/${release_version}" -f "sha=${GITHUB_SHA}"; then
    echo "Ref creation failed; checking whether another run created it." >&2
  fi
  resolve_tag || { echo "No verified tag after atomic creation." >&2; exit 1; }
fi

verify_release() {
  release_tag=$(gh release view "$release_version" --repo "$GITHUB_REPOSITORY" \
      --json tagName --jq '.tagName')
  [[ "$release_tag" == "$release_version" ]] || {
    echo "Release has an unexpected tag." >&2
    exit 1
  }
  resolve_tag || { echo "Release tag disappeared." >&2; exit 1; }
}

# Recheck immediately before using the tag, including existing-release reruns.
resolve_tag || exit 1
if ! $existing_release; then
  prerelease_args=()
  if [[ "$release_version" == *-beta.* ]]; then
    prerelease_args=(--prerelease --latest=false)
  fi
  if ! gh release create "$release_version" "${prerelease_args[@]}" \
      --repo "$GITHUB_REPOSITORY" --verify-tag --target "$GITHUB_SHA" \
      --title "Water Leak Guard ${release_version}" \
      --notes-file "RELEASE_NOTES_${release_version}.md"; then
    # A racing creator may have created the same release. Accept only a fully
    # verified release/tag, never an unchecked nonzero create result.
    verify_release
  fi
fi
verify_release
