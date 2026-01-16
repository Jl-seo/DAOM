import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import {
    defaultSiteConfig,
    colorsToCssVariables,
} from '../lib/siteConfig'
import type { SiteConfig, SiteColors } from '../lib/siteConfig'
import { apiClient } from '../lib/api'

interface SiteConfigContextType {
    config: SiteConfig
    updateConfig: (updates: Partial<SiteConfig>) => Promise<void>
    updateColors: (mode: 'light' | 'dark', colors: Partial<SiteColors>) => void
    resetToDefaults: () => Promise<void>
    isLoading: boolean
    resolvedTheme: 'light' | 'dark'
}

const SiteConfigContext = createContext<SiteConfigContextType | undefined>(undefined)

export function SiteConfigProvider({ children }: { children: React.ReactNode }) {
    const [config, setConfig] = useState<SiteConfig>(defaultSiteConfig)
    const [isLoading, setIsLoading] = useState(true)
    const [resolvedTheme, setResolvedTheme] = useState<'light' | 'dark'>('light')

    // Load config from backend
    useEffect(() => {
        const loadConfig = async () => {
            try {
                const response = await apiClient.get('/settings/site')
                if (response.data) {
                    setConfig({ ...defaultSiteConfig, ...response.data })
                }
            } catch {
                // Use defaults if API fails
                process.env.NODE_ENV === 'development' && console.log('Using default site config')
            } finally {
                setIsLoading(false)
            }
        }
        loadConfig()
    }, [])

    // Resolve theme (system preference handling)
    useEffect(() => {
        const getSystemTheme = () =>
            window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'

        const applyTheme = () => {
            const resolved = config.theme === 'system' ? getSystemTheme() : config.theme
            setResolvedTheme(resolved)

            // Apply theme class
            const root = document.documentElement
            root.classList.remove('light', 'dark')
            root.classList.add(resolved)

            // Apply CSS variables
            const colors = resolved === 'dark' ? config.colors.dark : config.colors.light
            const cssVars = colorsToCssVariables(colors)

            // Typography & Spacing variables
            const densityMap = {
                compact: '14px',
                normal: '16px',
                comfortable: '18px'
            }
            const baseFontSize = densityMap[config.density || 'normal']
            root.style.setProperty('--radius', `${config.radius ?? 0.5}rem`)
            root.style.setProperty('--base-font-size', baseFontSize)

            Object.entries(cssVars).forEach(([key, value]) => {
                root.style.setProperty(key, value)
            })
        }

        applyTheme()

        // Listen for system theme changes
        const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
        const handler = () => {
            if (config.theme === 'system') {
                applyTheme()
            }
        }
        mediaQuery.addEventListener('change', handler)
        return () => mediaQuery.removeEventListener('change', handler)
    }, [config])

    // Update config
    const updateConfig = useCallback(async (updates: Partial<SiteConfig>) => {
        const newConfig = { ...config, ...updates }
        setConfig(newConfig)

        // Save to backend (non-blocking)
        try {
            await apiClient.put('/settings/site', newConfig)
        } catch (error) {
            console.error('Failed to save site config:', error)
        }

        // Save to localStorage as backup
        localStorage.setItem('siteConfig', JSON.stringify(newConfig))
    }, [config])

    // Update colors for specific mode - uses functional update to avoid stale closure
    const updateColors = useCallback((mode: 'light' | 'dark', colors: Partial<SiteColors>) => {
        setConfig(prevConfig => {
            const newConfig = {
                ...prevConfig,
                colors: {
                    ...prevConfig.colors,
                    [mode]: { ...prevConfig.colors[mode], ...colors }
                }
            }

            // Save to localStorage immediately
            localStorage.setItem('siteConfig', JSON.stringify(newConfig))

            // Fire-and-forget API save (don't block UI)
            apiClient.put('/settings/site', newConfig).catch(error => {
                console.error('Failed to save colors:', error)
            })

            return newConfig
        })
    }, [])

    // Reset to defaults
    const resetToDefaults = useCallback(async () => {
        setConfig(defaultSiteConfig)

        try {
            await apiClient.put('/settings/site', defaultSiteConfig)
        } catch (error) {
            console.error('Failed to reset config:', error)
        }

        localStorage.removeItem('siteConfig')
    }, [])

    return (
        <SiteConfigContext.Provider value={{
            config,
            updateConfig,
            updateColors,
            resetToDefaults,
            isLoading,
            resolvedTheme
        }}>
            {children}
        </SiteConfigContext.Provider>
    )
}

export function useSiteConfig() {
    const context = useContext(SiteConfigContext)
    if (!context) {
        throw new Error('useSiteConfig must be used within a SiteConfigProvider')
    }
    return context
}
