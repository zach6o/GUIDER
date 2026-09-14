import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { ErrorBoundary } from './ErrorBoundary';
import './style.css';

/**
 * A render that throws must not leave a white page. The boundary wraps the
 * application rather than sitting inside it, so a failure while building the
 * page itself is still caught.
 */
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
);
