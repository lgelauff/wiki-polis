import {useEffect} from 'react';
import {useNavigate} from 'react-router-dom';

import {canonicalClientPath} from '../../client-routes';

export function NavigationRedirect({href}: {href: string}) {
  const navigate = useNavigate();
  useEffect(() => {
    const clientPath = canonicalClientPath(href);
    if (clientPath) navigate(clientPath, {replace: true});
    else globalThis.location.assign(href);
  }, [href, navigate]);
  return null;
}
