import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
    clearMocks: true,
    restoreMocks: true,
    // The send flow waits MIN_THINKING_MS per submission and reveals with real
    // rAF timing, so multi-send cases need more than the 5s default.
    testTimeout: 20_000,
  },
});
