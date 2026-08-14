import {useEffect} from 'react';

export function ExternalRedirect({href}: {href: string}) {
  useEffect(() => {
    globalThis.location.assign(href);
  }, [href]);
  return null;
}
