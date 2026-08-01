import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach, vi } from 'vitest';

/**
 * jsdom implements neither `Element.scrollTo` nor `window.matchMedia`, both of
 * which the chat shell calls on every render. Without these the very first
 * render throws and every test fails for a reason unrelated to the product.
 */

if (!Element.prototype.scrollTo) {
  Element.prototype.scrollTo = () => {};
}

let reducedMotionEnabled = false;

/** Toggle `prefers-reduced-motion: reduce` for the current test. */
export function setReducedMotion(enabled: boolean): void {
  reducedMotionEnabled = enabled;
}

function installMatchMedia(): void {
  window.matchMedia = ((query: string) => ({
    matches: query.includes('prefers-reduced-motion: reduce') ? reducedMotionEnabled : false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

beforeEach(() => {
  reducedMotionEnabled = false;
  installMatchMedia();
  window.sessionStorage.clear();
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.clearAllTimers();
});
