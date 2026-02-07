/* eslint-disable @typescript-eslint/no-unused-vars */
/**
 * useGraphApi - Hook for searching Entra ID users and groups
 * Uses MSAL to get Graph API access token
 */
import { useState, useCallback } from 'react'
import { useMsal } from '@azure/msal-react'

const GRAPH_API_BASE = 'https://graph.microsoft.com/v1.0'

export interface EntraUser {
    id: string
    displayName: string
    mail: string
    userPrincipalName: string
}

export interface EntraGroup {
    id: string
    displayName: string
    description: string
}

export function useGraphApi() {
    const { instance, accounts } = useMsal()
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    // Get Graph API access token
    const getAccessToken = useCallback(async () => {
        if (accounts.length === 0) {
            throw new Error('No account signed in')
        }

        try {
            const response = await instance.acquireTokenSilent({
                scopes: [
                    'https://graph.microsoft.com/User.Read.All',
                    'https://graph.microsoft.com/Group.Read.All'
                ],
                account: accounts[0]
            })
            return response.accessToken
        } catch (error) {
            // If silent fails, try popup
            const response = await instance.acquireTokenPopup({
                scopes: [
                    'https://graph.microsoft.com/User.Read.All',
                    'https://graph.microsoft.com/Group.Read.All'
                ]
            })
            return response.accessToken
        }
    }, [instance, accounts])

    // Search Entra users
    const searchUsers = useCallback(async (query: string): Promise<EntraUser[]> => {
        if (!query || query.length < 2) return []

        setLoading(true)
        setError(null)

        try {
            const token = await getAccessToken()

            const response = await fetch(
                `${GRAPH_API_BASE}/users?$search="displayName:${query}" OR "mail:${query}"&$top=10&$select=id,displayName,mail,userPrincipalName`,
                {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'ConsistencyLevel': 'eventual'
                    }
                }
            )

            if (!response.ok) {
                throw new Error(`Graph API error: ${response.status}`)
            }

            const data = await response.json()
            return data.value || []
        } catch (err) {
            console.error('Error searching users:', err)
            setError('사용자 검색에 실패했습니다. Graph API 권한을 확인해주세요.')
            return []
        } finally {
            setLoading(false)
        }
    }, [getAccessToken])

    // Search Entra security groups
    const searchGroups = useCallback(async (query: string): Promise<EntraGroup[]> => {
        if (!query || query.length < 2) return []

        setLoading(true)
        setError(null)

        try {
            const token = await getAccessToken()

            const response = await fetch(
                `${GRAPH_API_BASE}/groups?$search="displayName:${query}"&$filter=securityEnabled eq true&$top=10&$select=id,displayName,description`,
                {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'ConsistencyLevel': 'eventual'
                    }
                }
            )

            if (!response.ok) {
                throw new Error(`Graph API error: ${response.status}`)
            }

            const data = await response.json()
            return data.value || []
        } catch (err) {
            console.error('Error searching groups:', err)
            setError('그룹 검색에 실패했습니다. Graph API 권한을 확인해주세요.')
            return []
        } finally {
            setLoading(false)
        }
    }, [getAccessToken])

    return {
        searchUsers,
        searchGroups,
        loading,
        error
    }
}
