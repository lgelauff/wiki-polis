import {
  createContext,
  useContext,
  useEffect,
  useState,
  type FormEvent,
  type MouseEvent,
  type ReactNode,
} from 'react';
import {useLocation, useNavigate} from 'react-router-dom';
import {InternalLink} from './internal-link';
import {canonicalClientPath} from './client-routes';

const storageKey = 'wiki-polis:spa-only';
const cookieName = 'wiki-polis-spa-only';

type StrictSpaContextValue = {
  disable: () => void;
  enable: () => void;
  enabled: boolean;
};

const StrictSpaContext = createContext<StrictSpaContextValue | null>(null);

function readStoredMode(): boolean {
  const cookie = document.cookie.split(';').find((part) => (
    part.trim().startsWith(`${cookieName}=`)
  ))?.trim();
  if (cookie === `${cookieName}=0`) return false;
  if (cookie === `${cookieName}=1`) return true;
  try {
    if (globalThis.localStorage.getItem(storageKey) === '0') return false;
    if (globalThis.localStorage.getItem(storageKey) === '1') return true;
    if (globalThis.sessionStorage.getItem(storageKey) === '0') return false;
    if (globalThis.sessionStorage.getItem(storageKey) === '1') return true;
  } catch {
    // Storage can be unavailable in privacy-restricted browser contexts.
  }
  return true;
}

function storeMode(enabled: boolean) {
  try {
    globalThis.localStorage.setItem(storageKey, enabled ? '1' : '0');
    globalThis.sessionStorage.removeItem(storageKey);
  } catch {
    // Storage can be unavailable in privacy-restricted browser contexts.
  }
  try {
    document.cookie = `${cookieName}=${enabled ? '1' : '0'}; Path=/; Max-Age=31536000; SameSite=Lax`;
  } catch {
    // Cookies can be unavailable in privacy-restricted browser contexts.
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
  if (canonicalClientPath(href)) return null;

  const url = new URL(href, globalThis.location.href);
  if (!['http:', 'https:'].includes(url.protocol)) return null;
  if (url.origin !== globalThis.location.origin) return null;
  if (isServerSupportRoute(url.pathname)) return null;

  return `${url.pathname}${url.search}${url.hash}`;
}

export function StrictSpaBoundary({children}: {children: ReactNode}) {
  const location = useLocation();
  const navigate = useNavigate();
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
    const search = new URLSearchParams(location.search);
    if (search.has('spa_only')) {
      search.delete('spa_only');
      navigate({pathname: location.pathname, search: search.toString(), hash: location.hash}, {replace: true});
    }
  }

  function enable() {
    setEnabled(true);
    setBlockedTarget(null);
    storeMode(true);
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
    <StrictSpaContext.Provider value={{disable, enable, enabled}}>
      <div onClickCapture={captureLink} onSubmitCapture={captureForm}>
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

export function SpaModeToggle({developerMode}: {developerMode: boolean}) {
  const {disable, enable, enabled} = useStrictSpaMode();
  if (!developerMode) return null;

  return (
    <button
      type="button"
      className="spa-dev-toggle"
      role="switch"
      aria-checked={enabled}
      onClick={enabled ? disable : enable}
      title="Persistently block or allow Jinja route fallbacks in this browser"
    >
      SPA only <span>{enabled ? 'on' : 'off'}</span>
    </button>
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
        <InternalLink href="/consultations">Return to the SPA</InternalLink>
        <button type="button" onClick={disable}>Allow Jinja fallbacks</button>
      </div>
    </main>
  );
}
