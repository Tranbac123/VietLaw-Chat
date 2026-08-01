import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    // Must stay enabled: with `css: false` Vitest stubs stylesheet imports to
    // an empty string, including `?raw`, which would make the typography
    // assertions pass vacuously against no content at all.
    css: true,
    clearMocks: true,
    restoreMocks: true,
    // The send flow waits MIN_THINKING_MS per submission and reveals with real
    // rAF timing, so multi-send cases need more than the 5s default.
    testTimeout: 20_000,
  },
});
