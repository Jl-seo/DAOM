import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { PublicClientApplication } from '@azure/msal-browser'
import { MsalProvider } from '@azure/msal-react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import './i18n'
import { Toaster } from 'sonner'
import App from './App.tsx'
import { msalConfig, AuthProvider } from './auth'
import { SiteConfigProvider } from './components/SiteConfigProvider'

// Create MSAL instance - exported for use in api.ts
export const msalInstance = new PublicClientApplication(msalConfig)

// Initialize MSAL before rendering
const queryClient = new QueryClient()

msalInstance.initialize().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <SiteConfigProvider>
        <QueryClientProvider client={queryClient}>
          <MsalProvider instance={msalInstance}>
            <AuthProvider>
              <Toaster position="top-right" richColors />
              <App />
            </AuthProvider>
          </MsalProvider>
        </QueryClientProvider>
      </SiteConfigProvider>
    </StrictMode>,
  )
})
