import {Component, type ErrorInfo, type ReactNode} from 'react';
import {useQueryErrorResetBoundary, useSuspenseQuery} from '@tanstack/react-query';
import {useLocation} from 'react-router-dom';

import {ApiContractError} from '../../api/client';
import {sessionQuery} from '../../api/queries';
import {loginHref} from '../../login-href';
import {isMaintenance} from '../../maintenance';
import {AccessDeniedPage} from '../legacy/access-denied-page';
import {MaintenancePage} from '../legacy/maintenance-page';
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
  {children: ReactNode; onReset: () => void},
  {error: unknown | null}
> {
  state: {error: unknown | null} = {error: null};

  /** Shows the page again, and lets its refused queries fetch anew instead of rethrowing. */
  reset = () => {
    this.props.onReset();
    this.setState({error: null});
  };

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
    // Organizer and moderator reads are paused while maintenance mode is on (#619).
    if (isMaintenance(error)) return <MaintenancePage onOver={this.reset} />;
    if (error) throw error;
    return this.props.children;
  }
}

export function AdminAccessBoundary({children}: {children: ReactNode}) {
  const location = useLocation();
  const {reset} = useQueryErrorResetBoundary();
  return <AdminErrorBoundary key={location.pathname} onReset={reset}>{children}</AdminErrorBoundary>;
}
