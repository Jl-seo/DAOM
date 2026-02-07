/* eslint-disable react-hooks/set-state-in-effect */
/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import type { ReactNode } from 'react'
import { useMsal, useIsAuthenticated } from '@azure/msal-react'
import { InteractionStatus } from '@azure/msal-browser'
import type { AccountInfo } from '@azure/msal-browser'
import { loginRequest } from './authConfig'

interface AuthContextType {
    user: AccountInfo | null
    isAuthenticated: boolean
    isLoading: boolean
    isSuperAdmin: boolean
    accessibleMenus: string[]  // List of accessible menu IDs
    login: () => Promise<void>
    logout: () => void
    getAccessToken: () => Promise<string | null>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
    const { instance, accounts, inProgress } = useMsal()
    const isAuthenticated = useIsAuthenticated()
    const [user, setUser] = useState<AccountInfo | null>(null)
    const [isSuperAdmin, setIsSuperAdmin] = useState(false)
    const [accessibleMenus, setAccessibleMenus] = useState<string[]>([])

    const getAccessToken = useCallback(async (): Promise<string | null> => {
        const account = accounts[0]
        if (!account) return null

        try {
            const response = await instance.acquireTokenSilent({
                ...loginRequest,
                account: account
            })
            return response.accessToken
        } catch (error) {
            console.error('Token error:', error)
            try {
                const response = await instance.acquireTokenPopup(loginRequest)
                return response.accessToken
            } catch {
                return null
            }
        }
    }, [instance, accounts])

    // Fetch user permissions from backend
    useEffect(() => {
        if (accounts.length > 0) {
            setUser(accounts[0])

            // Fetch /users/me to get isSuperAdmin and /menus/accessible for menu permissions
            const fetchPermissions = async () => {
                const token = await getAccessToken()
                if (!token) return

                const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002/api/v1'
                const headers = { Authorization: `Bearer ${token}` }

                try {
                    // Fetch user info
                    const userResponse = await fetch(`${apiBase}/users/me`, { headers })
                    if (userResponse.ok) {
                        const data = await userResponse.json()
                        setIsSuperAdmin(data.isSuperAdmin ?? false)
                    }

                    // Fetch accessible menus
                    const menusResponse = await fetch(`${apiBase}/menus/accessible`, { headers })
                    if (menusResponse.ok) {
                        const menus = await menusResponse.json()
                        setAccessibleMenus(menus.map((m: { id: string }) => m.id))
                    }
                } catch (e) {
                    console.error('Failed to fetch user permissions:', e)
                }
            }
            fetchPermissions()
        } else {
            setUser(null)
            setIsSuperAdmin(false)
            setAccessibleMenus([])
        }
    }, [accounts, getAccessToken])

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

    const isLoading = inProgress !== InteractionStatus.None

    return (
        <AuthContext.Provider
            value={{
                user,
                isAuthenticated,
                isLoading,
                isSuperAdmin,
                accessibleMenus,
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

