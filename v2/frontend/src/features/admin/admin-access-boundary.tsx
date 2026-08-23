import {Component, useEffect, type ErrorInfo, type ReactNode} from 'react';
import {useLocation} from 'react-router-dom';

import {ApiContractError} from '../../api/client';

function LegacyForbiddenPage() {
  useEffect(() => {
    const previousTitle = document.title;
    const root = document.documentElement;
    const previousBackground = root.style.background;
    const previousFontSynthesis = root.style.fontSynthesis;
    const previousTextRendering = root.style.textRendering;
    const previousBodyMargin = document.body.style.margin;
    const previousBodyMinHeight = document.body.style.minHeight;
    document.title = '403 Forbidden';
    root.style.background = 'white';
    root.style.fontSynthesis = 'weight style small-caps';
    root.style.textRendering = 'auto';
    document.body.style.margin = '8px';
    document.body.style.minHeight = '0';
    return () => {
      document.title = previousTitle;
      root.style.background = previousBackground;
      root.style.fontSynthesis = previousFontSynthesis;
      root.style.textRendering = previousTextRendering;
      document.body.style.margin = previousBodyMargin;
      document.body.style.minHeight = previousBodyMinHeight;
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
