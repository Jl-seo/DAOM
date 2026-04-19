/**
 * Default MSW request handlers for frontend tests.
 *
 * Intentionally minimal — tests are expected to call `server.use(...)`
 * with per-test handlers for specific endpoints they exercise. Everything
 * unhandled returns 200 with empty JSON so unrelated queries don't throw.
 */
import { http, HttpResponse } from 'msw'

const API_BASE = '*/api/v1'

export const handlers = [
  // Site config
  http.get(`${API_BASE}/site-settings`, () =>
    HttpResponse.json({ branding: {}, theme: {} })
  ),

  // Current user (supports the AuthContext bootstrap path)
  http.get(`${API_BASE}/users/me`, () =>
    HttpResponse.json({
      id: 'test-user-id',
      email: 'tester@example.com',
      name: 'Test User',
      isSuperAdmin: false,
    })
  ),

  // Accessible menu list
  http.get(`${API_BASE}/menus/accessible`, () =>
    HttpResponse.json([])
  ),

  // Default model list
  http.get(`${API_BASE}/models`, () =>
    HttpResponse.json([])
  ),

  // Default extractions list
  http.get(`${API_BASE}/extractions`, () =>
    HttpResponse.json([])
  ),
]
