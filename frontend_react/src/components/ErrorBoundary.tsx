import React from 'react';
import { useTranslation } from 'react-i18next';

import { logError } from '../utils/log';

interface ErrorBoundaryProps {
  children: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    logError('Uncaught error:', error, errorInfo);
    // Log to remote monitoring service here if available
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    // Class component can't use hooks — ErrorBoundaryFallback renders the
    // translated UI so this class stays hook-free.
    return <ErrorBoundaryFallback error={this.state.error} />;
  }
}

/**
 * Presentational fallback with i18n. Split out of the class component because
 * React hooks (``useTranslation``) cannot be used inside a class body.
 */
function ErrorBoundaryFallback({ error }: { error?: Error }): JSX.Element {
  const { t } = useTranslation();
  const showDetails = import.meta.env?.DEV === true && error;
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        backgroundColor: '#f8fafc',
        color: '#1e293b',
        padding: '20px',
        textAlign: 'center',
      }}
      role="alert"
    >
      <h1>{t('spa.error_boundary.heading')}</h1>
      <p>{t('spa.error_boundary.description')}</p>
      {showDetails && (
        <details style={{ whiteSpace: 'pre-wrap', textAlign: 'left', marginTop: '20px' }}>
          <summary>Error details</summary>
          {error?.toString()}
        </details>
      )}
      <button
        onClick={() => window.location.reload()}
        style={{
          marginTop: '20px',
          padding: '10px 20px',
          fontSize: '16px',
          cursor: 'pointer',
          backgroundColor: '#3b82f6',
          color: 'white',
          border: 'none',
          borderRadius: '6px',
        }}
      >
        {t('spa.error_boundary.reload')}
      </button>
    </div>
  );
}
