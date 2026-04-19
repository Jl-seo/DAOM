/**
 * MSW Node server singleton used by setupTests.
 *
 * Tests override per-case handlers via `server.use(...)` inside
 * `beforeEach` / `beforeAll`. The server is stopped after all tests.
 */
import { setupServer } from 'msw/node'
import { handlers } from './handlers'

export const server = setupServer(...handlers)
