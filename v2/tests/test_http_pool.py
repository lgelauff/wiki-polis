"""Regression tests for the shared pooled HTTP session (http_pool)."""

from http.cookiejar import Cookie

import http_pool


def test_shared_session_jar_never_stores_response_cookies():
    """FIX-1: the process-wide Session must reject storing response cookies, or one
    participant's Particiapi `session=` cookie would leak onto another's request."""
    jar = http_pool.session.cookies
    jar.clear()
    cookie = Cookie(0, 'session', 'LEAK', None, False,
                    'polis.test', True, False, '/', True, False,
                    None, True, None, None, {})
    # set_cookie_if_ok consults the policy exactly as requests does on a response.
    jar.set_cookie_if_ok(cookie, object())   # dummy request; the no-store policy ignores it
    assert len(jar) == 0


def test_no_store_policy_rejects_everything():
    assert http_pool._NoStoreCookiePolicy().set_ok(object(), object()) is False
