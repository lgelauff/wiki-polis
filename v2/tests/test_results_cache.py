"""Unit tests for the in-process Phase 6 results aggregate cache (app._phase6_agg_cached)."""

import app


def test_phase6_agg_cache_memoises_expires_and_invalidates(monkeypatch):
    calls = {'n': 0}

    def producer():
        calls['n'] += 1
        return calls['n']

    # The autouse fixture disables the cache (TTL=0); enable it and pin the clock.
    monkeypatch.setattr(app, '_PHASE6_AGG_TTL', 100.0)
    clock = {'now': 1000.0}
    monkeypatch.setattr(app.time, 'monotonic', lambda: clock['now'])
    app._invalidate_phase6_results_cache()

    key = ('z6', 'z2', (1, 2), (3,), ())

    assert app._phase6_agg_cached(key, producer) == 1   # miss -> produce
    assert app._phase6_agg_cached(key, producer) == 1   # hit -> no reproduce
    assert calls['n'] == 1

    clock['now'] += 200.0                                # past TTL
    assert app._phase6_agg_cached(key, producer) == 2    # expired -> reproduce
    assert calls['n'] == 2

    app._invalidate_phase6_results_cache()               # explicit drop
    assert app._phase6_agg_cached(key, producer) == 3
    assert calls['n'] == 3


def test_phase6_agg_cache_skips_uncacheable_value(monkeypatch):
    # FIX-3: a degraded fetch (pg_available False) must NOT be memoised for the TTL.
    monkeypatch.setattr(app, '_PHASE6_AGG_TTL', 100.0)
    clock = {'now': 1000.0}
    monkeypatch.setattr(app.time, 'monotonic', lambda: clock['now'])
    app._invalidate_phase6_results_cache()
    calls = {'n': 0}

    def producer():
        calls['n'] += 1
        return {'pg_available': False}

    key = ('z6', 'z2', (), (), ())
    ok = lambda v: v['pg_available']  # noqa: E731
    app._phase6_agg_cached(key, producer, cacheable=ok)
    app._phase6_agg_cached(key, producer, cacheable=ok)
    assert calls['n'] == 2   # recomputed each time — the degraded value was not cached


def test_phase6_agg_cache_disabled_when_ttl_zero(monkeypatch):
    calls = {'n': 0}

    def producer():
        calls['n'] += 1
        return 'x'

    monkeypatch.setattr(app, '_PHASE6_AGG_TTL', 0.0)
    key = ('z6', 'z2', (), (), ())
    app._phase6_agg_cached(key, producer)
    app._phase6_agg_cached(key, producer)
    assert calls['n'] == 2   # no memoisation when disabled


def test_phase6_invalidate_scoped_to_one_conversation(monkeypatch):
    monkeypatch.setattr(app, '_PHASE6_AGG_TTL', 100.0)
    app._invalidate_phase6_results_cache()
    app._phase6_agg_cached(('zA', 'x', (), (), ()), lambda: 'a')
    app._phase6_agg_cached(('zB', 'x', (), (), ()), lambda: 'b')

    class _Conv:
        phase6_polis_conversation_id = 'zA'

    app._invalidate_phase6_results_cache(_Conv())
    # zA dropped (reproduced), zB retained (cached)
    assert app._phase6_agg_cached(('zA', 'x', (), (), ()), lambda: 'a2') == 'a2'
    assert app._phase6_agg_cached(('zB', 'x', (), (), ()), lambda: 'b2') == 'b'
