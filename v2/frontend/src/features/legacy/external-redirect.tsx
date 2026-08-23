import {useLayoutEffect} from 'react';
import {Navigate} from 'react-router-dom';

import {canonicalClientPath} from '../../client-routes';

export function NavigationRedirect({href}: {href: string}) {
  const clientPath = canonicalClientPath(href);

  useLayoutEffect(() => {
    if (!clientPath) globalThis.location.assign(href);
  }, [clientPath, href]);

  if (clientPath) return <Navigate to={clientPath} replace />;
  return null;
}
