import {Link, type LinkProps} from 'react-router-dom';

import {canonicalClientPath} from './client-routes';
import {prefetchClientRoute} from './route-modules';

type InternalLinkProps = Omit<LinkProps, 'to'> & {
  href?: string | undefined;
};

export function InternalLink({download, href, target, ...props}: InternalLinkProps) {
  const clientPath = href ? canonicalClientPath(href) : null;
  if (!clientPath || download || (target && target !== '_self')) {
    return <a {...props} download={download} href={href} target={target} />;
  }
  return <Link
    {...props}
    target={target}
    to={clientPath}
    onFocus={(event) => {
      props.onFocus?.(event);
      if (!event.defaultPrevented) prefetchClientRoute(clientPath);
    }}
    onMouseEnter={(event) => {
      props.onMouseEnter?.(event);
      if (!event.defaultPrevented) prefetchClientRoute(clientPath);
    }}
  />;
}
