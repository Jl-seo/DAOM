import { createContext, useContext, useState, useEffect } from 'react'
import type { ReactNode } from 'react'
import { useMsal, useIsAuthenticated } from '@azure/msal-react'
import { InteractionStatus } from '@azure/msal-browser'
import type { AccountInfo } from '@azure/msal-browser'
import { loginRequest } from './authConfig'

interface AuthContextType {
    user: AccountInfo | null
    isAuthenticated: boolean
    isLoading: boolean
    login: () => Promise<void>
    logout: () => void
    getAccessToken: () => Promise<string | null>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
    const { instance, accounts, inProgress } = useMsal()
    const isAuthenticated = useIsAuthenticated()
    const [user, setUser] = useState<AccountInfo | null>(null)

    useEffect(() => {
        if (accounts.length > 0) {
            setUser(accounts[0])
        } else {
            setUser(null)
        }
    }, [accounts])

    const login = async () => {
        try {
            await instance.loginPopup(loginRequest)
        } catch (error) {
            console.error('Login error:', error)
        }
    }

    const logout = () => {
        instance.logoutPopup({
            postLogoutRedirectUri: window.location.origin
        })
    }

    const getAccessToken = async (): Promise<string | null> => {
        if (!user) return null

        try {
            const response = await instance.acquireTokenSilent({
                ...loginRequest,
                account: user
            })
            return response.accessToken
        } catch (error) {
            console.error('Token error:', error)
            // Try popup if silent fails
            try {
                const response = await instance.acquireTokenPopup(loginRequest)
                return response.accessToken
            } catch {
                return null
            }
        }
    }

    const isLoading = inProgress !== InteractionStatus.None

    return (
        <AuthContext.Provider
            value={{
                user,
                isAuthenticated,
                isLoading,
                login,
                logout,
                getAccessToken
            }}
        >
            {children}
        </AuthContext.Provider>
    )
}

export function useAuth() {
    const context = useContext(AuthContext)
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider')
    }
    return context
}
