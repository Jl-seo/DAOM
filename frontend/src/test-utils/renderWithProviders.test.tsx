/**
 * Smoke test for the renderWithProviders helper and MSW pipeline.
 * Keeps the harness honest: if any provider or MSW breaks, CI fails
 * here instead of in a domain test with a confusing symptom.
 */
import { describe, it, expect } from 'vitest'
import { useQuery } from '@tanstack/react-query'
import { useLocation } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { renderWithProviders } from './renderWithProviders'
import { server } from './msw-server'

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="route">{location.pathname}</div>
}

function QueryProbe() {
  const { data, isLoading } = useQuery({
    queryKey: ['probe'],
    queryFn: async () => {
      const res = await fetch('https://api.example.com/api/v1/probe')
      return res.json() as Promise<{ hello: string }>
    },
  })
  if (isLoading) return <div data-testid="loading">loading</div>
  return <div data-testid="payload">{data?.hello}</div>
}

describe('renderWithProviders', () => {
  it('supplies a MemoryRouter with the given route', () => {
    const { getByTestId } = renderWithProviders(<LocationProbe />, {
      route: '/models/abc',
    })
    expect(getByTestId('route').textContent).toBe('/models/abc')
  })

  it('supplies a QueryClient so TanStack Query works', async () => {
    server.use(
      http.get('https://api.example.com/api/v1/probe', () =>
        HttpResponse.json({ hello: 'world' })
      )
    )

    const { findByTestId } = renderWithProviders(<QueryProbe />)
    const payload = await findByTestId('payload')
    expect(payload.textContent).toBe('world')
  })
})
