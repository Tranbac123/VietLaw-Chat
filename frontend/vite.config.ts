import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { ApiBaseUrlConfigError, normalizeApiBaseUrl } from './src/lib/apiBaseUrl';

// Deployment Correction Round 2 (MEDIUM-03): validate `VITE_API_BASE_URL`
// at BUILD time, not only at runtime in the browser. An independent
// review's actual `vite build` with `VITE_API_BASE_URL=
// http://localhost:8000` previously succeeded and embedded that value in
// `dist/` -- runtime-only validation cannot prevent a bad bundle from
// being produced and shipped in the first place, only from being USED
// once shipped. `loadEnv(mode, cwd, '')` (the empty prefix loads every
// variable, matching what Vite itself does for `import.meta.env` at
// bundle time) reads the same value the runtime code will see.
//
// `mode === 'production'` (not `command === 'build'`) is the signal used
// for "is this a production build": `vite build --mode development` is a
// real, supported way to get a dev-flavored build, and this check must
// track the SAME environment `import.meta.env.DEV`/`.PROD` reflect in the
// bundle it produces, not merely "was `build` typed on the command line".
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const isDev = mode !== 'production';

  try {
    const configured = normalizeApiBaseUrl(env.VITE_API_BASE_URL, isDev);
    if (!isDev && !configured) {
      throw new ApiBaseUrlConfigError(
        'VIETLAW: VITE_API_BASE_URL is not set for this production build. Set it ' +
          'at build time (see frontend/.env.production.example) -- the build must ' +
          'fail closed rather than produce a bundle that would throw only once ' +
          'loaded in a browser.',
      );
    }
  } catch (error) {
    if (error instanceof ApiBaseUrlConfigError) {
      // Re-thrown as a plain Error: Vite's config-loading error reporter
      // does not depend on this being any particular Error subclass, and a
      // custom class crossing the Vite-config/Node boundary has no benefit
      // here (nothing catches it more specifically upstream).
      throw new Error(error.message);
    }
    throw error;
  }

  return {
    plugins: [react()],
    server: { port: 5173 },
  };
});
