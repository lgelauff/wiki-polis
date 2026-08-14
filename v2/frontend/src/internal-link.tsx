import {Link, type LinkProps} from 'react-router-dom';

import {canonicalClientPath} from './client-routes';

type InternalLinkProps = Omit<LinkProps, 'to'> & {
  href?: string | undefined;
};

export function InternalLink({download, href, target, ...props}: InternalLinkProps) {
  const clientPath = href ? canonicalClientPath(href) : null;
  if (!clientPath || download || (target && target !== '_self')) {
    return <a {...props} download={download} href={href} target={target} />;
  }
  return <Link {...props} target={target} to={clientPath} />;
}
