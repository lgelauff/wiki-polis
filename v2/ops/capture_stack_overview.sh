#!/usr/bin/env bash
# Capture what this environment is actually running, so it can be reconstructed later.
#
# The stack has no single version number. Polis arrives as container images tagged
# `:latest`, built by a third party from a pinned upstream commit; Particiapi may be a
# locally built image; and the app itself is a git checkout. Nothing records which
# combination was live on a given day, which is exactly what you need when results look
# wrong and you are trying to work out what changed.
#
# Run it wherever part of the stack lives. It captures what it can see and says plainly
# what it cannot, rather than guessing:
#
#   ./capture_stack_overview.sh production     # on the Cloud VPS (containers)
#   ./capture_stack_overview.sh production     # again on Toolforge (the app)
#   ./capture_stack_overview.sh staging
#   ./capture_stack_overview.sh local
#
# Writes/updates  v2/ops/stack-overview-<env>.md   (current state, human-readable)
# and appends to  v2/ops/stack-history.jsonl       (one line per capture, for history)
#
# Both are committed deliberately: they contain digests, commit SHAs and dates — no
# secrets, no hostnames, no paths. Keep it that way; this file is public.

set -uo pipefail

ENV_NAME="${1:-}"
case "$ENV_NAME" in
  production|staging|local) ;;
  *) echo "usage: $0 {production|staging|local}" >&2; exit 2 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUT_MD="$SCRIPT_DIR/stack-overview-${ENV_NAME}.md"
OUT_LOG="$SCRIPT_DIR/stack-history.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ── helpers ───────────────────────────────────────────────────────────────────
have() { command -v "$1" >/dev/null 2>&1; }
git_at() { git -C "$1" "${@:2}" 2>/dev/null; }
json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }

# ── the app checkout ──────────────────────────────────────────────────────────
APP_SHA="$(git_at "$REPO_ROOT" rev-parse --short HEAD || echo unknown)"
APP_BRANCH="$(git_at "$REPO_ROOT" rev-parse --abbrev-ref HEAD || echo unknown)"
APP_DATE="$(git_at "$REPO_ROOT" log -1 --format=%cI || echo unknown)"
APP_DIRTY="clean"
[ -n "$(git_at "$REPO_ROOT" status --porcelain)" ] && APP_DIRTY="DIRTY"

# ── the docker stack, if this host has one ────────────────────────────────────
DOCKER_DIR="${PARTICIAPP_DOCKER_DIR:-$REPO_ROOT/../particiapp-docker}"
STACK_SHA="unavailable"; STACK_DATE=""; PARTICIAPI_SUB=""; PARTICIAPI_BRANCH=""; PARTICIAPI_PINNED=""
if [ -d "$DOCKER_DIR/.git" ]; then
  STACK_SHA="$(git_at "$DOCKER_DIR" rev-parse --short HEAD || echo unknown)"
  STACK_DATE="$(git_at "$DOCKER_DIR" log -1 --format=%cI || true)"
  if [ -d "$DOCKER_DIR/subprojects/particiapi/.git" ] || [ -f "$DOCKER_DIR/subprojects/particiapi/.git" ]; then
    PARTICIAPI_SUB="$(git_at "$DOCKER_DIR/subprojects/particiapi" rev-parse --short HEAD || true)"
    PARTICIAPI_BRANCH="$(git_at "$DOCKER_DIR/subprojects/particiapi" rev-parse --abbrev-ref HEAD || true)"
    # A leading '+' from `git submodule status` means the checkout differs from the pin.
    case "$(git_at "$DOCKER_DIR" submodule status -- subprojects/particiapi)" in
      \+*) PARTICIAPI_PINNED="off-pin" ;;
      *)   PARTICIAPI_PINNED="on-pin" ;;
    esac
  fi
fi

# ── container images: digest is the only reproducible identifier ──────────────
IMAGES_MD=""; IMAGES_JSON=""
if have docker && docker info >/dev/null 2>&1; then
  while IFS=$'\t' read -r repo tag digest id created; do
    [ -z "$repo" ] && continue
    short="${repo##*/}"
    [ "$digest" = "<none>" ] && digest="(built locally — not from a registry)"
    IMAGES_MD="${IMAGES_MD}| \`${short}\` | \`${tag}\` | \`${id}\` | ${created} | ${digest} |
"
    IMAGES_JSON="${IMAGES_JSON}{\"image\":\"$(json_escape "$repo")\",\"tag\":\"$(json_escape "$tag")\",\"id\":\"$(json_escape "$id")\",\"digest\":\"$(json_escape "$digest")\"},"
  done < <(docker images --digests --format '{{.Repository}}\t{{.Tag}}\t{{.Digest}}\t{{.ID}}\t{{.CreatedSince}}' 2>/dev/null | grep -iE 'particiapp|polis' || true)
fi
[ -z "$IMAGES_MD" ] && IMAGES_MD="| _no container images visible from this host_ | | | | |
"
IMAGES_JSON="[${IMAGES_JSON%,}]"

# ── which upstream Polis commit the images were built from ────────────────────
# Not recorded in the images (they carry no OCI labels), so it has to be read from
# the builder's CI config. Best-effort: needs network, and reports the value NOW,
# which is only the value used for our images if nobody has since moved it.
POLIS_REV="not checked"
if have curl; then
  fetched="$(curl -fsS --max-time 15 \
    'https://gitlab.com/api/v4/projects/particiapp%2Fpolis/repository/files/.gitlab-ci.yml/raw?ref=main' 2>/dev/null \
    | grep -oE 'POLIS_REVISION:[[:space:]]*"?[0-9a-f]{7,40}' | grep -oE '[0-9a-f]{7,40}' | head -1)"
  [ -n "$fetched" ] && POLIS_REV="$fetched"
fi

# ── write the human-readable overview ─────────────────────────────────────────
cat > "$OUT_MD" <<EOF
# Stack overview — ${ENV_NAME}

Captured **${NOW}** by \`v2/ops/capture_stack_overview.sh\`. Regenerate by running that
script on a host in this environment; it overwrites this file and appends a line to
\`stack-history.jsonl\`.

Environments are captured independently and drift apart — staging and production are
normally one or more cycles behind local. That is expected; the point is that the gap is
visible rather than guessed.

## Application

| | |
|---|---|
| wiki-polis commit | \`${APP_SHA}\` (${APP_BRANCH}) |
| committed | ${APP_DATE} |
| working tree | ${APP_DIRTY} |

## Backend stack

| | |
|---|---|
| particiapp-docker commit | \`${STACK_SHA}\`${STACK_DATE:+ (${STACK_DATE})} |
| particiapi submodule | ${PARTICIAPI_SUB:-unavailable}${PARTICIAPI_BRANCH:+ on \`${PARTICIAPI_BRANCH}\`}${PARTICIAPI_PINNED:+ — ${PARTICIAPI_PINNED}} |
| upstream Polis revision | \`${POLIS_REV}\` |

The Polis images are built by a third party from a pinned upstream commit; that commit is
recorded in the builder's CI rather than in the images, so the row above is read live and
reflects the value **now**, which matches our images only if it has not since moved.

## Container images

A digest identifies an image reproducibly; a tag does not. \`:latest\` means the running
version is whatever this host last pulled.

| image | tag | id | age | digest |
|---|---|---|---|---|
${IMAGES_MD}
## Reading this

- **\`(built locally)\`** — no registry digest, so this image exists only on the host that
  built it and cannot be pulled elsewhere.
- **\`off-pin\`** — the submodule checkout differs from the commit the superproject
  records, so what runs is not what the repo says should run.
- **\`DIRTY\`** — uncommitted changes were present at capture, so the commit alone does
  not describe what ran.
EOF

# ── append the machine-readable history line ──────────────────────────────────
printf '{"captured":"%s","env":"%s","app":{"sha":"%s","branch":"%s","committed":"%s","tree":"%s"},"stack":{"particiapp_docker":"%s","particiapi":"%s","particiapi_branch":"%s","particiapi_pin":"%s"},"upstream_polis_revision":"%s","images":%s}\n' \
  "$NOW" "$ENV_NAME" "$APP_SHA" "$APP_BRANCH" "$APP_DATE" "$APP_DIRTY" \
  "$STACK_SHA" "${PARTICIAPI_SUB:-}" "${PARTICIAPI_BRANCH:-}" "${PARTICIAPI_PINNED:-}" \
  "$POLIS_REV" "$IMAGES_JSON" >> "$OUT_LOG"

echo "wrote  $OUT_MD"
echo "appended to  $OUT_LOG"
