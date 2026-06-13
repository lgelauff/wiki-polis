# Plan: #55 — Evaluate switching to Toolforge buildservice

**Verdict: FITS — framed as a bounded evaluation spike with a concrete deliverable.**

## Context

The roadmap lists this under "Admin & ops" deferred items. The issue asks for an evaluation,
not a migration. Current deploy is `git pull` + optional `pip install` + `toolforge webservice restart`
(documented in `guide_deployment.md` § Ongoing deploys and `deploy.sh`).

**Buildservice** would replace this with `toolforge build start` (builds a Docker image from
the repo's `Procfile` or `Dockerfile`) + `toolforge webservice buildservice start`. Trade-offs
are documented in the issue.

**This plan delivers:**
1. A spike branch that adds the required `Procfile` / `Dockerfile` and tests whether
   `toolforge build start` succeeds on `wiki-polis-dev`.
2. A written evaluation report (`v2/.claude/eval-buildservice-55.md`) comparing the two
   approaches against concrete criteria (deploy speed, reproducibility, Toolforge-specific
   gotchas, rollback ease).
3. A go/no-go recommendation.

**No production change is made.** The spike is tested on `wiki-polis-dev` only.

## Files to change

| File | Action |
|---|---|
| `Procfile` | Create (repo root) — buildservice entry point |
| `v2/.claude/eval-buildservice-55.md` | Create — spike log + evaluation report |

Optionally (if Procfile alone is insufficient):

| File | Action |
|---|---|
| `Dockerfile` | Create (repo root) — explicit Docker build for buildservice |

## Implementation steps

### Step 1 — research current Toolforge buildservice constraints (HUMAN STEP + Agent)

Run the following on the Toolforge bastion to check current buildservice availability and
Python version support:

```bash
# HUMAN STEP — SSH to login.toolforge.org, become wiki-polis-dev
toolforge build --help
toolforge webservice buildservice --help
# Check what base image is available for Python 3.13
toolforge build list-base-images 2>/dev/null || echo "no such command"
```

Research: https://wikitech.wikimedia.org/wiki/Help:Toolforge/Build_Service

Key questions to answer in the evaluation:
- Does buildservice support Python 3.13 as a base image?
- Is `pip install -e .` (editable install with `pyproject.toml`) supported?
- Does the build environment have internet access to PyPI?
- What is the actual build time for a `pip install -e wiki-polis/v2`?
- Can the built image access Toolforge envvars?
- Can `toolforge webservice python3.13` and `buildservice` run in parallel on different
  tools (`wiki-polis` vs `wiki-polis-dev`)?

### Step 2 — write `Procfile` (minimal buildservice entry point)

```
web: uwsgi --ini /data/project/wiki-polis/www/python/uwsgi.ini --wsgi-file /data/project/wiki-polis/www/python/src/app.py --callable app
```

(Adjust paths to match the buildservice container's working directory — verify from
`toolforge build` docs.)

Alternatively, if a `Dockerfile` is needed:

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY v2/ /app/
RUN pip install --no-cache-dir -e .
CMD ["uwsgi", "--ini", "uwsgi.ini", "--wsgi-file", "app.py", "--callable", "app"]
```

### Step 3 — test on wiki-polis-dev (HUMAN STEP)

```bash
# SSH to login.toolforge.org, become wiki-polis-dev
cd ~/wiki-polis
toolforge build start   # triggers image build from Procfile/Dockerfile
# wait for build to complete; note build time
toolforge build show    # confirm success or diagnose failure
# If build succeeds:
toolforge webservice buildservice start
curl -s -o /dev/null -w "%{http_code}" https://wiki-polis-dev.toolforge.org/health
# expect 200
```

Record: build time, any errors, whether envvars are injected correctly.

### Step 4 — fill in `v2/.claude/eval-buildservice-55.md`

The evaluation document structure:

```markdown
# Buildservice evaluation — issue #55

## Date: <date>
## Tested on: wiki-polis-dev

## Spike results

| Criterion | python3.13 webservice | buildservice |
|---|---|---|
| Deploy time (typical) | ~30s (git pull + restart) | <measured> |
| Build time | n/a | <measured> |
| Python 3.13 available? | yes | <confirmed / gap> |
| Editable install works? | yes | <confirmed / gap> |
| Envvars injected? | yes | <confirmed / gap> |
| Rollback | redeploy previous branch | <procedure> |
| Build failures visible? | n/a | <log location> |
| Blocking issues found | none | <list or none> |

## Recommendation

[ADOPT / DEFER / DECLINE] — [one paragraph rationale]

If ADOPT: migration steps are:
1. ...
If DEFER: revisit when [condition].
If DECLINE: close issue with reason.
```

## Tests

No automated tests for this spike — it's an ops evaluation. The test is:

1. `toolforge build start` succeeds without errors.
2. `https://wiki-polis-dev.toolforge.org/health` returns `{"status": "ok"}`.
3. Logging in via Wikimedia OAuth works (session cookie is set correctly).
4. A vote can be cast on the `test` conversation.

## Verification

- Evaluation report (`v2/.claude/eval-buildservice-55.md`) filled in.
- Go/no-go recommendation recorded.
- If ADOPT: migration steps added to `guide_deployment.md` § Ongoing deploys.
- If DEFER/DECLINE: issue closed with evaluation comment summary.
