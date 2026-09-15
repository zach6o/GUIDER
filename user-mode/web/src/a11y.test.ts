import { describe, expect, it } from 'vitest';
import { nextFocus } from './a11y';

/**
 * No DOM here: the part worth testing is where Tab goes at the two ends, and
 * that is arithmetic. The browser tests hold the rest — that focus enters the
 * dialog, stays inside it, and comes back afterwards.
 */
const order = ['first', 'middle', 'last'] as unknown as HTMLElement[];

describe('where Tab goes inside a dialog', () => {
  it('leaves the middle alone, because the browser already gets it right', () => {
    expect(nextFocus(order, order[1], false)).toBeNull();
    expect(nextFocus(order, order[1], true)).toBeNull();
  });

  it('wraps from the last control to the first', () => {
    expect(nextFocus(order, order[2], false)).toBe(order[0]);
  });

  it('wraps backwards from the first control to the last', () => {
    expect(nextFocus(order, order[0], true)).toBe(order[2]);
  });

  it('pulls focus back in when it is somewhere outside entirely', () => {
    // A click on the page behind the dialog, or a browser that moved focus on
    // its own: the next Tab returns to the near end rather than continuing
    // through a page the user was told they had left.
    expect(nextFocus(order, null, false)).toBe(order[0]);
    expect(nextFocus(order, null, true)).toBe(order[2]);
  });

  it('has nowhere to send focus in a dialog with no controls', () => {
    expect(nextFocus([], null, false)).toBeNull();
  });
});
