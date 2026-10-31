import {Component, type ErrorInfo, type ReactNode} from 'react';
import {useSuspenseQuery} from '@tanstack/react-query';
import {useLocation} from 'react-router-dom';

import {ApiContractError} from '../../api/client';
import {sessionQuery} from '../../api/queries';
import {loginHref} from '../../login-href';
import {AccessDeniedPage} from '../legacy/access-denied-page';
import {NavigationRedirect} from '../legacy/external-redirect';

/** A signed-out visitor on a console page that needs a sign-in goes to the login, and comes
 *  back here afterwards (`?next=`, #432), as on a consultation page. */
function LoginRedirect() {
  const {data: session} = useSuspenseQuery(sessionQuery());
  const location = useLocation();
  // The login is the server's, so this is a full navigation (`NavigationRedirect`).
  return <NavigationRedirect href={loginHref(session.links.login, location)} />;
}

class AdminErrorBoundary extends Component<
  {children: ReactNode},
  {error: unknown | null}
> {
  state: {error: unknown | null} = {error: null};

  static getDerivedStateFromError(error: unknown) {
    return {error};
  }

  componentDidCatch(_error: unknown, _info: ErrorInfo) {
    // The API error is rendered below; browser logging is intentionally unnecessary.
  }

  render() {
    const {error} = this.state;
    // A refusal is the app's own access page (#538), not a bare "Forbidden" document.
    if (error instanceof ApiContractError && error.code === 'forbidden') {
      return <AccessDeniedPage />;
    }
    if (error instanceof ApiContractError && error.code === 'unauthorized') {
      return <LoginRedirect />;
    }
    if (error) throw error;
    return this.props.children;
  }
}

export function AdminAccessBoundary({children}: {children: ReactNode}) {
  const location = useLocation();
  return <AdminErrorBoundary key={location.pathname}>{children}</AdminErrorBoundary>;
}
