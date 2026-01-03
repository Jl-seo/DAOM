// Site Configuration Schema and Defaults
// Central configuration for branding, themes, and site-wide settings

export interface SiteColors {
    primary: string
    primaryForeground: string
    secondary: string
    secondaryForeground: string
    background: string
    foreground: string
    card: string
    cardForeground: string
    muted: string
    mutedForeground: string
    accent: string
    accentForeground: string
    destructive: string
    border: string
    input: string
    ring: string
    sidebar: string
    sidebarForeground: string
    sidebarPrimary: string
    sidebarPrimaryForeground: string
    sidebarAccent: string
    sidebarAccentForeground: string
    sidebarBorder: string
}

export interface SiteConfig {
    // Branding
    siteName: string
    siteDescription: string
    logoUrl?: string
    faviconUrl?: string

    // Theme
    theme: 'light' | 'dark' | 'system'
    radius: number
    density: 'compact' | 'normal' | 'comfortable'
    colors: {
        light: SiteColors
        dark: SiteColors
    }

    // Typography
    fontFamily: string

    // Advanced
    customCss?: string
}

// Default DAOM theme colors (Blue primary)
export const defaultLightColors: SiteColors = {
    primary: 'oklch(0.6723 0.1606 244.9955)',
    primaryForeground: 'oklch(1.0000 0 0)',
    secondary: 'oklch(0.1884 0.0128 248.5103)',
    secondaryForeground: 'oklch(1.0000 0 0)',
    background: 'oklch(1.0000 0 0)',
    foreground: 'oklch(0.1884 0.0128 248.5103)',
    card: 'oklch(0.9784 0.0011 197.1387)',
    cardForeground: 'oklch(0.1884 0.0128 248.5103)',
    muted: 'oklch(0.9222 0.0013 286.3737)',
    mutedForeground: 'oklch(0.1884 0.0128 248.5103)',
    accent: 'oklch(0.9392 0.0166 250.8453)',
    accentForeground: 'oklch(0.6723 0.1606 244.9955)',
    destructive: 'oklch(0.6188 0.2376 25.7658)',
    border: 'oklch(0.9317 0.0118 231.6594)',
    input: 'oklch(0.9809 0.0025 228.7836)',
    ring: 'oklch(0.6818 0.1584 243.3540)',
    sidebar: 'oklch(0.9784 0.0011 197.1387)',
    sidebarForeground: 'oklch(0.1884 0.0128 248.5103)',
    sidebarPrimary: 'oklch(0.6723 0.1606 244.9955)',
    sidebarPrimaryForeground: 'oklch(1.0000 0 0)',
    sidebarAccent: 'oklch(0.9392 0.0166 250.8453)',
    sidebarAccentForeground: 'oklch(0.6723 0.1606 244.9955)',
    sidebarBorder: 'oklch(0.9271 0.0101 238.5177)',
}

export const defaultDarkColors: SiteColors = {
    primary: 'oklch(0.6692 0.1607 245.0110)',
    primaryForeground: 'oklch(1.0000 0 0)',
    secondary: 'oklch(0.9622 0.0035 219.5331)',
    secondaryForeground: 'oklch(0.1884 0.0128 248.5103)',
    background: 'oklch(0 0 0)',
    foreground: 'oklch(0.9328 0.0025 228.7857)',
    card: 'oklch(0.2097 0.0080 274.5332)',
    cardForeground: 'oklch(0.8853 0 0)',
    muted: 'oklch(0.2090 0 0)',
    mutedForeground: 'oklch(0.5637 0.0078 247.9662)',
    accent: 'oklch(0.1928 0.0331 242.5459)',
    accentForeground: 'oklch(0.6692 0.1607 245.0110)',
    destructive: 'oklch(0.6188 0.2376 25.7658)',
    border: 'oklch(0.2674 0.0047 248.0045)',
    input: 'oklch(0.3020 0.0288 244.8244)',
    ring: 'oklch(0.6818 0.1584 243.3540)',
    sidebar: 'oklch(0.2097 0.0080 274.5332)',
    sidebarForeground: 'oklch(0.8853 0 0)',
    sidebarPrimary: 'oklch(0.6818 0.1584 243.3540)',
    sidebarPrimaryForeground: 'oklch(1.0000 0 0)',
    sidebarAccent: 'oklch(0.1928 0.0331 242.5459)',
    sidebarAccentForeground: 'oklch(0.6692 0.1607 245.0110)',
    sidebarBorder: 'oklch(0.3795 0.0220 240.5943)',
}

export const defaultSiteConfig: SiteConfig = {
    siteName: 'DAOM',
    siteDescription: '문서 자동화',
    theme: 'system',
    radius: 0.5,
    density: 'normal',
    fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
    colors: {
        light: defaultLightColors,
        dark: defaultDarkColors,
    },
}

// Preset themes
export const themePresets = {
    blue: {
        name: '블루 (기본)',
        primary: 'oklch(0.6723 0.1606 244.9955)',
    },
    purple: {
        name: '퍼플',
        primary: 'oklch(0.6500 0.1800 300.0000)',
    },
    green: {
        name: '그린',
        primary: 'oklch(0.6500 0.1500 145.0000)',
    },
    orange: {
        name: '오렌지',
        primary: 'oklch(0.7000 0.1800 45.0000)',
    },
} as const

// CSS variable mapping
export function colorsToCssVariables(colors: SiteColors, prefix: string = ''): Record<string, string> {
    const vars: Record<string, string> = {}
    const p = prefix ? `${prefix}-` : ''

    vars[`--${p}primary`] = colors.primary
    vars[`--${p}primary-foreground`] = colors.primaryForeground
    vars[`--${p}secondary`] = colors.secondary
    vars[`--${p}secondary-foreground`] = colors.secondaryForeground
    vars[`--${p}background`] = colors.background
    vars[`--${p}foreground`] = colors.foreground
    vars[`--${p}card`] = colors.card
    vars[`--${p}card-foreground`] = colors.cardForeground
    vars[`--${p}muted`] = colors.muted
    vars[`--${p}muted-foreground`] = colors.mutedForeground
    vars[`--${p}accent`] = colors.accent
    vars[`--${p}accent-foreground`] = colors.accentForeground
    vars[`--${p}destructive`] = colors.destructive
    vars[`--${p}border`] = colors.border
    vars[`--${p}input`] = colors.input
    vars[`--${p}ring`] = colors.ring
    vars[`--${p}sidebar`] = colors.sidebar
    vars[`--${p}sidebar-foreground`] = colors.sidebarForeground
    vars[`--${p}sidebar-primary`] = colors.sidebarPrimary
    vars[`--${p}sidebar-primary-foreground`] = colors.sidebarPrimaryForeground
    vars[`--${p}sidebar-accent`] = colors.sidebarAccent
    vars[`--${p}sidebar-accent-foreground`] = colors.sidebarAccentForeground
    vars[`--${p}sidebar-border`] = colors.sidebarBorder

    return vars
}
