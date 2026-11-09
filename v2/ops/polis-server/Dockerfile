# The Polis server we run, plus one line from upstream f79f992be (lgelauff/wiki-polis#594):
# moderation (hide, approve, meta) stamps comments.modified, so Polis math sees the change.
#
# Base: particiapp's build of upstream fd440c3e, the image both stacks ran as :latest.
# Remove this file when we move off that pin (see the follow-up issue linked from #594).
FROM registry.gitlab.com/particiapp/polis/server@sha256:adf9b8b45e134ad4da3596cbdf1748cb3f9f0cbf88b6d77bef0fbee43c16c8e2

# The build fails unless the statement matches exactly once before and after.
RUN old='is_meta = $3 WHERE zid = $4 AND tid = $5' \
 && new='is_meta = $3, modified = now_as_millis() WHERE zid = $4 AND tid = $5' \
 && for f in dist/src/server.js src/server.ts; do \
      test "$(grep -cF "$old" "$f")" = 1 || { echo "unexpected match count in $f" >&2; exit 1; }; \
      sed -i 's/is_meta = \$3 WHERE zid = \$4 AND tid = \$5/is_meta = $3, modified = now_as_millis() WHERE zid = $4 AND tid = $5/' "$f"; \
      test "$(grep -cF "$new" "$f")" = 1 || { echo "patch did not apply to $f" >&2; exit 1; }; \
    done
