const serverSupportPaths = [
  '/login',
  '/logout',
  '/oauth-callback',
  '/dev-login',
];

function isServerSupportPath(pathname: string): boolean {
  return serverSupportPaths.includes(pathname)
    || pathname.startsWith('/dev/login/')
    || pathname === '/api'
    || pathname.startsWith('/api/')
    || pathname === '/static'
    || pathname.startsWith('/static/');
}

function temporaryPathToCanonical(pathname: string): string | null {
  const exact: Record<string, string> = {
    '/app': '/',
    '/app/parity/fork': '/',
    '/app/demo': '/demo',
    '/app/real': '/consultations',
    '/app/parity/help/statements': '/help/statements',
    '/app/parity/help/arguments': '/help/arguments',
    '/app/admin': '/admin',
  };
  if (exact[pathname]) return exact[pathname];

  let match = pathname.match(/^\/app\/conversations\/([^/]+)\/(join|about|explore|arguments|informed-voting|results|identity-reveal)$/);
  if (match) {
    const [, slug, page] = match;
    if (page === 'join') return `/accept/${slug}`;
    if (page === 'about') return `/c/${slug}/about`;
    if (page === 'arguments') return `/c/${slug}#tab-arguments`;
    if (page === 'informed-voting') return `/c/${slug}#tab-informed-voting`;
    if (page === 'results') return `/c/${slug}/report`;
    if (page === 'identity-reveal') return `/c/${slug}/reveal`;
    return `/c/${slug}`;
  }

  match = pathname.match(/^\/app\/parity\/conversations\/([^/]+)\/(moderation-log|outputs\/[^/]+)$/);
  if (match) return `/c/${match[1]}/${match[2]}`;

  match = pathname.match(/^\/app\/admin\/conversations\/(\d+)(?:\/(.*))?$/);
  if (match) {
    const suffix = match[2] === 'moderation'
      ? 'flags'
      : match[2] === 'invitations'
        ? 'invites'
        : match[2];
    return `/admin/conversations/${match[1]}${suffix ? `/${suffix}` : ''}`;
  }
  return null;
}

export function isCanonicalClientPath(pathname: string): boolean {
  if (['/', '/demo', '/consultations', '/help/statements', '/help/arguments', '/admin'].includes(pathname)) return true;
  if (/^\/accept\/[^/]+$/.test(pathname)) return true;
  if (/^\/c\/[^/]+(?:\/(?:about|moderation-log|report|reveal|outputs\/[^/]+))?$/.test(pathname)) return true;
  return /^\/admin\/conversations\/\d+(?:\/(?:participants|flags|invites|statements|featured|settings|termination|roles))?$/.test(pathname);
}

export function canonicalClientPath(href: string): string | null {
  if (!href || href.startsWith('#')) return null;
  const url = new URL(href, globalThis.location.href);
  if (!['http:', 'https:'].includes(url.protocol)) return null;
  if (url.origin !== globalThis.location.origin || isServerSupportPath(url.pathname)) return null;

  const mapped = temporaryPathToCanonical(url.pathname);
  const pathname = mapped?.split('#', 1)[0] ?? url.pathname;
  if (!mapped && !isCanonicalClientPath(pathname)) return null;

  const mappedHash = mapped?.includes('#') ? `#${mapped.split('#', 2)[1]}` : '';
  return `${pathname}${url.search}${url.hash || mappedHash}`;
}
