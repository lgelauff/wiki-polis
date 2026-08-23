import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import {QueryClientProvider} from '@tanstack/react-query';
import {BrowserRouter} from 'react-router-dom';

import {App} from './app';
import {createQueryClient} from './query-client';
import './styles.css';
import '../../static/style.css';

const root = document.getElementById('root');
if (!root) throw new Error('SPA root element is missing.');

if (window.location.pathname === '/app/demo' || window.location.pathname === '/demo') {
  document.body.dataset.demo = 'true';
  document.body.dataset.spaInitialDemo = 'true';
}

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={createQueryClient()}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
