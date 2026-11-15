#!/usr/bin/env bash
# Fetch and build the latest released KiCAD MCP server without losing local edits.
set -Eeuo pipefail

repo="${KICAD_MCP_REPO:-$HOME/KiCAD-MCP-Server}"
branch="${KICAD_MCP_BRANCH:-stable}"
log_dir="${XDG_STATE_HOME:-$HOME/.local/state}/kicad-mcp-updater"
mkdir -p "$log_dir"
exec 9>"$log_dir/update.lock"
flock -n 9 || exit 0

log() { printf '[%s] %s\n' "$(date --iso-8601=seconds)" "$*"; }
if [[ ! -d "$repo/.git" ]]; then
  log "ERROR: KiCAD MCP repository not found: $repo"
  exit 1
fi

cd "$repo"
current_branch="$(git branch --show-current)"
if [[ "$current_branch" != "$branch" ]]; then
  log "ERROR: expected branch '$branch', found '$current_branch'; refusing to update"
  exit 1
fi

old_commit="$(git rev-parse HEAD)"
stash_ref=""
if [[ -n "$(git status --porcelain)" ]]; then
  git stash push --include-untracked -m "kicad-mcp-auto-update-$(date +%Y%m%d%H%M%S)" >&2
  stash_ref="$(git rev-parse -q --verify refs/stash || true)"
fi

restore_local_changes() {
  if [[ -n "$stash_ref" && "$(git rev-parse -q --verify refs/stash || true)" == "$stash_ref" ]]; then
    git stash pop --index
  fi
}
trap 'status=$?; if [[ $status -ne 0 ]]; then log "ERROR: update failed (exit $status); inspect this log and repository state"; fi' EXIT

git fetch --quiet origin "$branch"
new_commit="$(git rev-parse FETCH_HEAD)"
if [[ "$old_commit" == "$new_commit" ]]; then
  restore_local_changes
  stash_ref=""
  log "Already current at $(git describe --tags --always "$old_commit")"
  exit 0
fi

git merge --ff-only "$new_commit"
restore_local_changes
stash_ref=""

# Reconcile dependencies using the restored local package manifest/lockfile, then compile.
npm ci --no-audit --no-fund
npm run build

log "Updated KiCAD MCP server: $old_commit -> $new_commit"
