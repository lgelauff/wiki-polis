import {useLocation} from 'react-router-dom';

/** The login link with a way back (#432): `?next=` names the page the visitor was on, and
 *  the server returns there after the Wikimedia login if it is a plain path on this site.
 *  A voucher code (`v`) is a credential and never rides along. */
export function loginHref(login: string, location: {pathname: string; search: string}): string {
  return `${login}${login.includes('?') ? '&' : '?'}next=${encodeURIComponent(returnPath(location))}`;
}

/** The page the visitor is on, as a `next` to come back to: path and query, without a
 *  voucher code (`v`), which is a credential and never rides along. */
export function returnPath(location: {pathname: string; search: string}): string {
  const params = new URLSearchParams(location.search);
  params.delete('v');
  const query = params.toString();
  return `${location.pathname}${query ? `?${query}` : ''}`;
}

/** {@link loginHref} for the page the router is on now. */
export function useLoginHref(login: string): string {
  return loginHref(login, useLocation());
}
