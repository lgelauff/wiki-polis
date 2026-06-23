# Toolforge buildservice evaluation (#55)

Status: evaluated, not switched by default.

The current `python3.13` Toolforge webservice path is still the supported production
deploy path. Buildservice should be piloted on `wiki-polis-dev` first because this repo
contains legacy top-level Flask files while the live application is under `v2/`; a
generic root buildpack could build the wrong app unless the build context is explicit.

## Current path

- Code update: `git pull` on the bastion.
- Dependencies: `~/www/python/venv/bin/pip install -e ~/wiki-polis/v2`.
- Runtime: Toolforge `python3.13` webservice using `~/www/python/uwsgi.ini`.
- Pros: known-good, immediate restarts, migration path already scripted.
- Cons: the venv can drift if `pip install -e` is skipped after dependency changes.

## Buildservice target shape

Use an explicit Dockerfile or build context that starts from `v2/`, not the repository
root. A safe container entrypoint must:

1. install `v2/pyproject.toml` dependencies,
2. run the Flask app from `v2/app.py`,
3. preserve Toolforge envvar injection,
4. keep `uwsgi` or an equivalent production WSGI server,
5. continue using `MIGRATION_MODE=1 flask --app app db upgrade` for migrations before
   the webservice restart.

Do not rely on a root-level `Procfile` until the legacy top-level `app.py`, `db.py`, and
`pyproject.toml` are removed or the build context is proven to ignore them.

## Staging pilot

Run only as `wiki-polis-dev`:

```bash
become wiki-polis-dev
cd ~/wiki-polis
git fetch origin
git checkout <branch-to-test>

# Build from an explicit Dockerfile/build context once one exists.
toolforge build start
toolforge webservice buildservice start
```

Validate before considering production:

```bash
curl -fsS https://wiki-polis-dev.toolforge.org/health
python ~/wiki-polis/v2/synthetic_traffic.py \
  --base-url https://wiki-polis-dev.toolforge.org \
  --slug test --dry-run
```

Rollback:

```bash
toolforge webservice stop
toolforge webservice python3.13 start
```

## Recommendation

Stay on `python3.13` until deploy frequency or dependency churn makes venv drift a real
problem. When switching, add a Dockerfile dedicated to `v2/` and test the image on
`wiki-polis-dev` for at least one full deploy plus migration cycle before production.
