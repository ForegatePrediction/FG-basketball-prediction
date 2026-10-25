#!/usr/bin/env bash
# Mirrored in each engine. Only the isolated data worktree is ever pushed.
set -euo pipefail
mode=${1:?prepare or publish}
engine=${2:?engine required}
case "$engine" in football|basketball|esports) ;; *) exit 2 ;; esac
branch=refs/heads/data-snapshots
scratch=$(mktemp -d "${RUNNER_TEMP:-/tmp}/fg-data-backup.XXXXXX")
tree="$scratch/tree"
cleanup() { git worktree remove --force "$tree" >/dev/null 2>&1 || true; rm -rf "$scratch"; }
trap cleanup EXIT
exists=0
git ls-remote --exit-code origin "$branch" > "$scratch/ref" || exists=$?
case "$exists" in
  0) git fetch --depth=1 origin "$branch"; git worktree add --detach "$tree" FETCH_HEAD ;;
  2) if [ "$mode" = prepare ]; then echo 'First backup run: bootstrap from committed snapshot'; exit 0; fi
     git worktree add --detach "$tree" HEAD
     git -C "$tree" switch --orphan "data-bootstrap-${GITHUB_RUN_ID:-local}" ;;
  *) echo 'Cannot inspect backup branch' >&2; exit 1 ;;
esac
case "$mode" in
  prepare)
    python3 data_bundle.py restore --engine "$engine" --source . --bundle "$tree"
    ;;
  publish)
    if [ "${GITHUB_REF:-}" != refs/heads/main ]; then
      echo 'Only main may publish the canonical backup branch' >&2; exit 1
    fi
    python3 data_bundle.py create --engine "$engine" --source . --bundle "$scratch/output"
    git -C "$tree" rm -r --ignore-unmatch -- .
    python3 data_bundle.py restore --engine "$engine" --source "$tree" --bundle "$scratch/output"
    cp "$scratch/output/manifest.json" "$tree/manifest.json"
    git -C "$tree" config user.name 'github-actions[bot]'
    git -C "$tree" config user.email 'github-actions[bot]@users.noreply.github.com'
    git -C "$tree" add --all
    git -C "$tree" commit -m "data: daily $engine backup"
    git -C "$tree" push origin "HEAD:$branch"
    ;;
  *) echo 'Unknown mode' >&2; exit 2 ;;
esac
