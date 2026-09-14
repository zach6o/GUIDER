import { Component, type ErrorInfo, type ReactNode } from 'react';

/**
 * The last thing standing when a render throws.
 *
 * Without this, one exception in the island or the plan screen unmounts the tree
 * and leaves a white page — the worst available failure for an application whose
 * whole job is to be trustworthy on screen while somebody works. A guide that
 * vanishes mid-task is worse than a guide that says it broke, because the user
 * is left wondering whether their task survived.
 *
 * So the fallback says three things, in this order: what happened, that the task
 * is still there, and how to get back to it. It never shows a stack trace: a
 * message the user cannot act on is noise, and an error string can carry
 * fragments of whatever the guide was handling.
 */

interface Props {
  children: ReactNode;
  /** Called on the way down, so a running guide can be stopped rather than left
   *  watching a screen nobody is guiding. */
  onError?: (error: Error) => void;
}

interface State {
  failed: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Console only. There is no error-reporting service configured, and sending
    // one would mean sending whatever the guide was holding.
    console.error('Guider stopped rendering', error, info.componentStack);
    this.props.onError?.(error);
  }

  render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="crash-page" role="alert">
        <h1>Guider stopped unexpectedly.</h1>
        <p>
          Nothing you did caused this, and nothing has been lost. Your task, your
          plan and everything you have already done are saved on the server.
        </p>
        <p className="crash-note">
          Watching, if it was on, has stopped. Reloading brings you back to your
          task history, where you can pick the task up again.
        </p>
        <button className="primary" onClick={() => window.location.reload()}>
          Reload Guider
        </button>
      </div>
    );
  }
}
