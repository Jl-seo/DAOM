/**
 * Vitest setup:
 *  - jest-dom matchers
 *  - react-i18next stub (renders keys as text)
 *  - MSW node server lifecycle
 *  - pdfjs-dist worker stub (avoids "fake worker" load errors in jsdom)
 *  - @azure/msal-react stub (prevents provider-less rendering failures)
 */
import '@testing-library/jest-dom'
import { vi, afterAll, afterEach, beforeAll } from 'vitest'
import { server } from './test-utils/msw-server'

// ---------------------------------------------------------------------------
// MSW server lifecycle
// ---------------------------------------------------------------------------
beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

// ---------------------------------------------------------------------------
// react-i18next — render translation keys verbatim
// ---------------------------------------------------------------------------
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      changeLanguage: () => new Promise(() => {}),
      language: 'en',
    },
  }),
  initReactI18next: {
    type: '3rdParty',
    init: () => {},
  },
  Trans: ({ children }: { children?: unknown }) => children as never,
}))

// ---------------------------------------------------------------------------
// pdfjs-dist — noop worker to keep the PDF viewer modules importable
// ---------------------------------------------------------------------------
vi.mock('pdfjs-dist/build/pdf.worker.min.js?url', () => ({
  default: '',
}))

vi.mock('pdfjs-dist', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>
  return {
    ...actual,
    GlobalWorkerOptions: { workerSrc: '' },
  }
})

// ---------------------------------------------------------------------------
// `../main` (and variants) — importing main.tsx triggers top-level
// createRoot() which errors in jsdom. `src/lib/api.ts` re-exports
// msalInstance from there, so any test that transitively touches api.ts
// would crash. Stub with an in-memory instance.
// ---------------------------------------------------------------------------
const fakeMsalInstance = {
  initialize: () => Promise.resolve(),
  getAllAccounts: () => [],
  acquireTokenSilent: () =>
    Promise.resolve({ accessToken: 'test-token' }),
  acquireTokenPopup: () =>
    Promise.resolve({ accessToken: 'test-token' }),
  loginPopup: () => Promise.resolve(),
  logoutPopup: () => Promise.resolve(),
}

vi.mock('../main', () => ({ msalInstance: fakeMsalInstance }))
vi.mock('../../main', () => ({ msalInstance: fakeMsalInstance }))
vi.mock('../../../main', () => ({ msalInstance: fakeMsalInstance }))

// ---------------------------------------------------------------------------
// @azure/msal-react — provide a harmless default so components that read
// the MSAL context during render don't explode. Tests that need auth
// behavior can override these mocks per file.
// ---------------------------------------------------------------------------
vi.mock('@azure/msal-react', () => ({
  MsalProvider: ({ children }: { children: unknown }) => children as never,
  useMsal: () => ({
    instance: {
      initialize: () => Promise.resolve(),
      loginPopup: () => Promise.resolve(),
      logoutPopup: () => Promise.resolve(),
      acquireTokenSilent: () =>
        Promise.resolve({ accessToken: 'test-token' }),
    },
    accounts: [],
    inProgress: 'none',
  }),
  useIsAuthenticated: () => false,
  AuthenticatedTemplate: ({ children }: { children: unknown }) =>
    children as never,
  UnauthenticatedTemplate: ({ children }: { children: unknown }) =>
    children as never,
}))

// ---------------------------------------------------------------------------
// window.matchMedia — jsdom doesn't implement it; Radix UI and some hooks
// rely on it.
// ---------------------------------------------------------------------------
if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })
}
