/**
 * Test render helper that wraps a component with the same providers
 * real pages get in main.tsx: QueryClientProvider and MemoryRouter.
 *
 * MSAL / AuthProvider / SiteConfigProvider are intentionally NOT
 * included — tests that need them should mock at the module level
 * (see setupTests.ts for the default `@azure/msal-react` mock).
 */
import type { ReactElement, ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, type RenderOptions, type RenderResult } from '@testing-library/react'

interface RenderWithProvidersOptions extends Omit<RenderOptions, 'wrapper'> {
  /** Initial URL the MemoryRouter should land on (default `/`) */
  route?: string
  /** Supply a pre-built QueryClient to share state across renders */
  queryClient?: QueryClient
}

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  })

export function renderWithProviders(
  ui: ReactElement,
  { route = '/', queryClient, ...renderOptions }: RenderWithProvidersOptions = {}
): RenderResult & { queryClient: QueryClient } {
  const client = queryClient ?? createTestQueryClient()

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <MemoryRouter initialEntries={[route]}>
        <QueryClientProvider client={client}>
          {children}
        </QueryClientProvider>
      </MemoryRouter>
    )
  }

  return {
    ...render(ui, { wrapper: Wrapper, ...renderOptions }),
    queryClient: client,
  }
}
