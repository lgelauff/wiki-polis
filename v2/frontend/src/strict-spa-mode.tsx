import {
  createContext,
  useContext,
  useEffect,
  useState,
  type FormEvent,
  type MouseEvent,
  type ReactNode,
} from 'react';
import {useLocation} from 'react-router-dom';

const storageKey = 'wiki-polis:spa-only';

type StrictSpaContextValue = {
  disable: () => void;
  enabled: boolean;
};

const StrictSpaContext = createContext<StrictSpaContextValue | null>(null);

function readStoredMode(): boolean {
  try {
    return globalThis.sessionStorage.getItem(storageKey) === '1';
  } catch {
    return false;
  }
}

function storeMode(enabled: boolean) {
  try {
    if (enabled) globalThis.sessionStorage.setItem(storageKey, '1');
    else globalThis.sessionStorage.removeItem(storageKey);
  } catch {
    // Storage can be unavailable in privacy-restricted browser contexts.
  }
}

function requestedMode(search: string): boolean | null {
  const value = new URLSearchParams(search).get('spa_only');
  if (value === '1') return true;
  if (value === '0') return false;
  return null;
}

function isServerSupportRoute(pathname: string): boolean {
  return pathname === '/login'
    || pathname === '/logout'
    || pathname === '/oauth-callback'
    || pathname === '/dev-login'
    || pathname.startsWith('/dev/login/')
    || pathname === '/api'
    || pathname.startsWith('/api/')
    || pathname === '/static'
    || pathname.startsWith('/static/');
}

function legacyTarget(href: string): string | null {
  if (!href || href.startsWith('#')) return null;

  const url = new URL(href, globalThis.location.href);
  if (!['http:', 'https:'].includes(url.protocol)) return null;
  if (url.origin !== globalThis.location.origin) return null;
  if (url.pathname === '/app' || url.pathname.startsWith('/app/')) return null;
  if (isServerSupportRoute(url.pathname)) return null;

  return `${url.pathname}${url.search}${url.hash}`;
}

export function StrictSpaBoundary({children}: {children: ReactNode}) {
  const location = useLocation();
  const initialRequest = requestedMode(location.search);
  const [enabled, setEnabled] = useState(() => initialRequest ?? readStoredMode());
  const [blockedTarget, setBlockedTarget] = useState<string | null>(null);

  useEffect(() => {
    const request = requestedMode(location.search);
    if (request === null) return;
    setEnabled(request);
    storeMode(request);
    if (!request) setBlockedTarget(null);
  }, [location.search]);

  useEffect(() => {
    storeMode(enabled);
  }, [enabled]);

  function disable() {
    setEnabled(false);
    setBlockedTarget(null);
    storeMode(false);
  }

  function block(target: string) {
    console.warn(`[SPA-only] Blocked legacy navigation to ${target}`);
    setBlockedTarget(target);
  }

  function captureLink(event: MouseEvent<HTMLDivElement>) {
    if (!enabled || event.defaultPrevented || !(event.target instanceof Element)) return;
    const anchor = event.target.closest<HTMLAnchorElement>('a[href]');
    if (!anchor) return;
    const target = legacyTarget(anchor.getAttribute('href') ?? '');
    if (!target) return;
    event.preventDefault();
    event.stopPropagation();
    block(target);
  }

  function captureForm(event: FormEvent<HTMLDivElement>) {
    if (!enabled || event.defaultPrevented || !(event.target instanceof HTMLFormElement)) return;
    const action = event.target.getAttribute('action');
    if (!action) return;
    const target = legacyTarget(action);
    if (!target) return;
    event.preventDefault();
    event.stopPropagation();
    block(target);
  }

  return (
    <StrictSpaContext.Provider value={{disable, enabled}}>
      <div onClickCapture={captureLink} onSubmitCapture={captureForm}>
        {enabled && (
          <aside className="spa-only-banner" aria-label="SPA-only testing mode">
            <strong>SPA-only mode</strong>
            <span>Jinja fallbacks are blocked.</span>
            <button type="button" onClick={disable}>Allow Jinja fallbacks</button>
          </aside>
        )}
        {children}
        {blockedTarget && (
          <div className="spa-coverage-backdrop">
            <section
              className="spa-coverage-gap"
              role="alertdialog"
              aria-modal="true"
              aria-labelledby="spa-coverage-heading"
            >
              <p className="eyebrow">React coverage gap</p>
              <h1 id="spa-coverage-heading">Not implemented in the React SPA</h1>
              <p>SPA-only mode stopped navigation to a server-rendered route:</p>
              <code>{blockedTarget}</code>
              <div>
                <button type="button" onClick={() => setBlockedTarget(null)}>Keep testing the SPA</button>
                <button type="button" onClick={disable}>Allow Jinja fallbacks</button>
              </div>
            </section>
          </div>
        )}
      </div>
    </StrictSpaContext.Provider>
  );
}

export function useStrictSpaMode(): StrictSpaContextValue {
  const context = useContext(StrictSpaContext);
  if (!context) throw new Error('useStrictSpaMode must be used inside StrictSpaBoundary.');
  return context;
}

export function MissingSpaRoute() {
  const location = useLocation();
  const {disable} = useStrictSpaMode();
  const target = `${location.pathname}${location.search}${location.hash}`;

  return (
    <main className="spa-missing-route" id="main">
      <p className="eyebrow">React coverage gap</p>
      <h1>Not implemented in the React SPA</h1>
      <p>No React route matches this URL:</p>
      <code>{target}</code>
      <div>
        <a href="/app/real">Return to the SPA</a>
        <button type="button" onClick={disable}>Allow Jinja fallbacks</button>
      </div>
    </main>
  );
}
