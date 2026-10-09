# Sourced by deploy.sh and guarded manual Toolforge operations.
wiki_polis_require_tool_account() {
  local operation_label="${1:-Toolforge operation}"
  local active_account

  if ! active_account="$(whoami 2>/dev/null)"; then
    printf '%s: unable to determine the active Toolforge account via whoami. Aborting.\n' \
      "$operation_label" >&2
    return 1
  fi

  case "$active_account" in
    tools.wiki-polis|tools.wiki-polis-dev)
      return 0
      ;;
  esac

  if [[ "${ALLOW_UNKNOWN_TOOL:-}" == "1" ]]; then
    printf '!!  WARNING: ALLOW_UNKNOWN_TOOL=1 permits %s under unlisted account %q. Confirm the target before proceeding.\n' \
      "$operation_label" "$active_account" >&2
    return 0
  fi

  printf "%s: active account is '%s', not a known wiki-polis tool. You are probably in the wrong 'become' context. Aborting.\n" \
    "$operation_label" "$active_account" >&2
  return 1
}
