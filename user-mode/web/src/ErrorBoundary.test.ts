import { describe, expect, it, vi } from 'vitest';
import { ErrorBoundary } from './ErrorBoundary';

/**
 * No DOM here on purpose: this suite runs in node, and pulling in jsdom plus a
 * rendering library to assert on a fallback would be a dependency for one test.
 * What can be checked without rendering is the part that actually matters —
 * that a thrown error switches the boundary into its fallback, and that a
 * running guide is told before the tree goes.
 */

describe('when a render throws', () => {
  it('switches to the fallback rather than unmounting to nothing', () => {
    expect(ErrorBoundary.getDerivedStateFromError()).toEqual({ failed: true });
  });

  it('tells the caller, so a running guide can be stopped', () => {
    const onError = vi.fn();
    const boundary = new ErrorBoundary({ children: null, onError });
    const failure = new Error('something threw');
    vi.spyOn(console, 'error').mockImplementation(() => {});

    boundary.componentDidCatch(failure, { componentStack: 'at Island' } as never);

    // Otherwise a crashed page could leave a watcher encoding frames for a guide
    // nobody is looking at.
    expect(onError).toHaveBeenCalledWith(failure);
  });

  it('survives having no handler at all', () => {
    const boundary = new ErrorBoundary({ children: null });
    vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() =>
      boundary.componentDidCatch(new Error('x'), { componentStack: '' } as never),
    ).not.toThrow();
  });

  it('starts out showing its children', () => {
    expect(new ErrorBoundary({ children: null }).state).toEqual({ failed: false });
  });
});
