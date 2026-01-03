import { useSiteConfig } from '../SiteConfigProvider'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { themePresets } from '../../lib/siteConfig'
import { Palette, RotateCcw, Sun, Moon, Check } from 'lucide-react'
import { toast } from 'sonner'
import { useState } from 'react'

export function ThemeCustomizer() {
    const { config, updateConfig, updateColors, resetToDefaults, resolvedTheme } = useSiteConfig()
    const [activePreset, setActivePreset] = useState<string | null>(null)

    const handlePrimaryColorChange = (color: string) => {
        // Update primary and related colors
        updateColors(resolvedTheme, {
            primary: color,
            ring: color,
            sidebarPrimary: color,
            accentForeground: color,
            sidebarAccentForeground: color,
        })
        toast.success('Primary 색상이 변경되었습니다')
    }

    const handleThemeChange = (theme: 'light' | 'dark' | 'system') => {
        updateConfig({ theme })
        toast.success(`테마가 ${theme === 'light' ? '라이트' : theme === 'dark' ? '다크' : '시스템'} 모드로 변경되었습니다`)
    }

    const applyPreset = (presetKey: keyof typeof themePresets) => {
        const preset = themePresets[presetKey]

        // Update all related colors for both light and dark modes
        const colorUpdates = {
            primary: preset.primary,
            ring: preset.primary,
            sidebarPrimary: preset.primary,
            accentForeground: preset.primary,
            sidebarAccentForeground: preset.primary,
        }

        updateColors('light', colorUpdates)
        updateColors('dark', colorUpdates)

        setActivePreset(presetKey)
        toast.success(`${preset.name} 테마가 적용되었습니다`)
    }

    return (
        <div className="space-y-6">
            {/* Theme Mode */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                        <Sun className="w-4 h-4" />
                        테마 모드
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex gap-2">
                        <Button
                            variant={config.theme === 'light' ? 'default' : 'outline'}
                            onClick={() => handleThemeChange('light')}
                            className="flex-1"
                        >
                            <Sun className="w-4 h-4 mr-2" />
                            라이트
                        </Button>
                        <Button
                            variant={config.theme === 'dark' ? 'default' : 'outline'}
                            onClick={() => handleThemeChange('dark')}
                            className="flex-1"
                        >
                            <Moon className="w-4 h-4 mr-2" />
                            다크
                        </Button>
                        <Button
                            variant={config.theme === 'system' ? 'default' : 'outline'}
                            onClick={() => handleThemeChange('system')}
                            className="flex-1"
                        >
                            시스템
                        </Button>
                    </div>
                </CardContent>
            </Card>

            {/* Color Presets */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                        <Palette className="w-4 h-4" />
                        컬러 프리셋
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="grid grid-cols-2 gap-3">
                        {Object.entries(themePresets).map(([key, preset]) => {
                            const isActive = activePreset === key
                            return (
                                <button
                                    key={key}
                                    onClick={() => applyPreset(key as keyof typeof themePresets)}
                                    className={`flex items-center gap-3 p-3 rounded-lg border-2 transition-all text-left relative ${isActive
                                        ? 'border-primary bg-primary/10 shadow-sm'
                                        : 'border-border hover:bg-accent hover:border-primary/50'
                                        }`}
                                >
                                    <div
                                        className="w-8 h-8 rounded-full shadow-inner flex items-center justify-center"
                                        style={{ background: preset.primary }}
                                    >
                                        {isActive && <Check className="w-4 h-4 text-white" />}
                                    </div>
                                    <span className="text-sm font-medium flex-1">{preset.name}</span>
                                </button>
                            )
                        })}
                    </div>
                </CardContent>
            </Card>

            {/* Custom Primary Color */}
            <Card>
                <CardHeader>
                    <CardTitle className="text-base">커스텀 Primary 색상</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex items-center gap-4">
                        <input
                            type="color"
                            className="w-12 h-12 rounded-lg border-2 border-border cursor-pointer"
                            onChange={(e) => {
                                // Convert hex to oklch (simplified - just use hex for now)
                                handlePrimaryColorChange(e.target.value)
                            }}
                        />
                        <div className="flex-1">
                            <p className="text-sm text-muted-foreground">
                                색상 피커로 원하는 색상을 선택하세요
                            </p>
                        </div>
                    </div>
                </CardContent>
            </Card>



            {/* Typography & Spacing */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                        <Palette className="w-4 h-4" />
                        스타일 & 크기
                    </CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                    {/* Density */}
                    <div className="space-y-3">
                        <label className="text-sm font-medium text-muted-foreground block">
                            UI 밀도 (텍스트 & 여백)
                        </label>
                        <div className="flex gap-2">
                            {(['compact', 'normal', 'comfortable'] as const).map((density) => (
                                <Button
                                    key={density}
                                    variant={config.density === density ? 'default' : 'outline'}
                                    onClick={() => updateConfig({ density })}
                                    className="flex-1 capitalize"
                                >
                                    {density === 'compact' && '좁게'}
                                    {density === 'normal' && '보통'}
                                    {density === 'comfortable' && '넓게'}
                                </Button>
                            ))}
                        </div>
                        <p className="text-xs text-muted-foreground">
                            전체적인 텍스트 크기와 여백을 조절합니다.
                        </p>
                    </div>

                    {/* Radius */}
                    <div className="space-y-3">
                        <label className="text-sm font-medium text-muted-foreground block">
                            모서리 둥글기
                        </label>
                        <div className="grid grid-cols-5 gap-2">
                            {[0, 0.3, 0.5, 0.75, 1.0].map((r) => (
                                <Button
                                    key={r}
                                    variant={config.radius === r ? 'default' : 'outline'}
                                    onClick={() => updateConfig({ radius: r })}
                                    className="px-2"
                                    title={`${r}rem`}
                                >
                                    <div
                                        className="w-4 h-4 border-2 border-current"
                                        style={{ borderRadius: `${r}rem` }}
                                    />
                                </Button>
                            ))}
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Reset */}
            <Button
                variant="outline"
                onClick={resetToDefaults}
                className="w-full"
            >
                <RotateCcw className="w-4 h-4 mr-2" />
                기본값으로 초기화
            </Button>
        </div >
    )
}
