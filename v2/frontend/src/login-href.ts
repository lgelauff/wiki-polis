import {useLocation} from 'react-router-dom';

/** The login link with a way back (#432): `?next=` names the page the visitor was on, and
 *  the server returns there after the Wikimedia login if it is a plain path on this site.
 *  A voucher code (`v`) is a credential and never rides along. */
export function loginHref(login: string, location: {pathname: string; search: string}): string {
  const params = new URLSearchParams(location.search);
  params.delete('v');
  const query = params.toString();
  const next = `${location.pathname}${query ? `?${query}` : ''}`;
  return `${login}${login.includes('?') ? '&' : '?'}next=${encodeURIComponent(next)}`;
}

/** {@link loginHref} for the page the router is on now. */
export function useLoginHref(login: string): string {
  return loginHref(login, useLocation());
}
