# Stack overview — local

Captured **2026-09-03T08:49:48Z** by `v2/ops/capture_stack_overview.sh`. Regenerate by running that
script on a host in this environment; it overwrites this file and appends a line to
`stack-history.jsonl`.

Environments are captured independently and drift apart — staging and production are
normally one or more cycles behind local. That is expected; the point is that the gap is
visible rather than guessed.

## Application

| | |
|---|---|
| wiki-polis commit | `f3987ca` (feat/version-manifest) |
| committed | 2026-09-03T08:39:48+02:00 |
| working tree | DIRTY |

## Backend stack

| | |
|---|---|
| particiapp-docker commit | `9a65a1b` (2026-03-18T16:12:37+01:00) |
| particiapi submodule | 7d419b8 on `feat/trusted-sub-identity` — off-pin |
| upstream Polis revision | `fd440c3e3ca302d08ce3cca870fc39b834c96b86` |

The Polis images are built by a third party from a pinned upstream commit; that commit is
recorded in the builder's CI rather than in the images, so the row above is read live and
reflects the value **now**, which matches our images only if it has not since moved.

## Container images

A digest identifies an image reproducibly; a tag does not. `:latest` means the running
version is whatever this host last pulled.

| image | tag | id | age | digest |
|---|---|---|---|---|
| `particiapi` | `latest` | `a69861632aaf` | 3 months ago | (built locally — not from a registry) |
| `file-server` | `latest` | `a0a2971a291d` | 5 months ago | sha256:fed21aa4aa8c23810ea3c24e49f556d78a53d09e7fb30dbf0df2d080e384d1e4 |
| `math` | `latest` | `4d16791145a8` | 5 months ago | sha256:446e9704af72cca7a2111f00a475549dc6697ae7e8e204d9b06e28a389c354b1 |
| `server` | `latest` | `36fc9ea36280` | 5 months ago | sha256:adf9b8b45e134ad4da3596cbdf1748cb3f9f0cbf88b6d77bef0fbee43c16c8e2 |

## Reading this

- **`(built locally)`** — no registry digest, so this image exists only on the host that
  built it and cannot be pulled elsewhere.
- **`off-pin`** — the submodule checkout differs from the commit the superproject
  records, so what runs is not what the repo says should run.
- **`DIRTY`** — uncommitted changes were present at capture, so the commit alone does
  not describe what ran.
