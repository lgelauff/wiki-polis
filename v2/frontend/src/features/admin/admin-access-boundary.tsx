import {Component, useEffect, type ErrorInfo, type ReactNode} from 'react';
import {useLocation} from 'react-router-dom';

import {ApiContractError} from '../../api/client';

function LegacyForbiddenPage() {
  useEffect(() => {
    const previousTitle = document.title;
    const root = document.documentElement;
    const previousBackground = root.style.background;
    const previousBodyMargin = document.body.style.margin;
    document.title = '403 Forbidden';
    root.style.background = 'white';
    document.body.style.margin = '8px';
    return () => {
      document.title = previousTitle;
      root.style.background = previousBackground;
      document.body.style.margin = previousBodyMargin;
    };
  }, []);

  return (
    <div style={{color: 'black', fontFamily: 'serif', fontSize: 16, lineHeight: 'normal'}}>
      <h1>Forbidden</h1>
      <p>
        You don&apos;t have the permission to access the requested resource. It is either
        {' '}read-protected or not readable by the server.
      </p>
    </div>
  );
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
    if (error instanceof ApiContractError && error.code === 'forbidden') {
      return <LegacyForbiddenPage />;
    }
    if (error) throw error;
    return this.props.children;
  }
}

export function AdminAccessBoundary({children}: {children: ReactNode}) {
  const location = useLocation();
  return <AdminErrorBoundary key={location.pathname}>{children}</AdminErrorBoundary>;
}
