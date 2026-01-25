
import React from 'react'
import { clsx } from 'clsx'
import { Card } from '@/components/ui/icon-card'
import { Switch } from '@/components/ui/switch'
import { Slider } from '@/components/ui/slider'
import { Settings, Eye, EyeOff, CheckCircle2, XCircle } from 'lucide-react'
import type { ComparisonSettings } from '../ModelStudio'

const CHECK_CATEGORIES = [
    { key: 'content', label: '텍스트 내용 (Content)', description: '글자, 숫자, 기호의 변경' },
    { key: 'added_element', label: '추가된 요소 (Added)', description: '새로 생긴 이미지나 UI 요소' },
    { key: 'missing_element', label: '누락된 요소 (Missing)', description: '사라진 이미지나 UI 요소' },
]

const OPTIONAL_CATEGORIES = [
    { key: 'layout', label: '레이아웃 (Layout)', description: '위치 이동이나 크기 변경' },
    { key: 'style', label: '스타일 (Style)', description: '폰트, 색상, 테두리 등 스타일 변경' },
]

interface ComparisonSettingsPanelProps {
    settings: ComparisonSettings | undefined;
    onChange: (settings: ComparisonSettings) => void;
    disabled?: boolean;
}

export function ComparisonSettingsPanel({ settings, onChange, disabled }: ComparisonSettingsPanelProps) {
    // Default values
    const currentSettings: ComparisonSettings = settings || {
        confidence_threshold: 0.85,
        ignore_position_changes: true,
        ignore_color_changes: false,
        ignore_font_changes: true,
        ignore_compression_noise: true,
        excluded_categories: [],
        custom_categories: []
    }

    // Local state for new category input
    const [newCatKey, setNewCatKey] = React.useState('')
    const [newCatLabel, setNewCatLabel] = React.useState('')
    const [newCatDesc, setNewCatDesc] = React.useState('')
    const [isAddingCat, setIsAddingCat] = React.useState(false)

    const handleChange = (key: keyof ComparisonSettings, value: any) => {
        onChange({
            ...currentSettings,
            [key]: value
        })
    }

    const toggleCategoryExclusion = (categoryKey: string) => {
        const currentExcluded = currentSettings.excluded_categories || []
        const isExcluded = currentExcluded.includes(categoryKey)
        if (isExcluded) {
            handleChange('excluded_categories', currentExcluded.filter(c => c !== categoryKey))
        } else {
            handleChange('excluded_categories', [...currentExcluded, categoryKey])
        }
    }

    const handleAddCustomCategory = () => {
        if (!newCatKey || !newCatLabel) return

        // Key validation: no duplicates, simplified chars
        const safeKey = newCatKey.trim().toLowerCase().replace(/[^a-z0-9_]/g, '')
        const existingKeys = [...CHECK_CATEGORIES, ...OPTIONAL_CATEGORIES, ...(currentSettings.custom_categories || [])].map(c => c.key)

        if (existingKeys.includes(safeKey)) {
            // Toast or visual error? For now just return
            return
        }

        const newCat = {
            key: safeKey,
            label: newCatLabel,
            description: newCatDesc
        }

        const updatedCustom = [...(currentSettings.custom_categories || []), newCat]
        handleChange('custom_categories', updatedCustom)

        // Reset form
        setNewCatKey('')
        setNewCatLabel('')
        setNewCatDesc('')
        setIsAddingCat(false)
    }

    const handleDeleteCustomCategory = (key: string) => {
        const updatedCustom = (currentSettings.custom_categories || []).filter(c => c.key !== key)
        handleChange('custom_categories', updatedCustom)

        // Also remove from exclusion list if it was there (cleanup)
        if ((currentSettings.excluded_categories || []).includes(key)) {
            handleChange('excluded_categories', (currentSettings.excluded_categories || []).filter(c => c !== key))
        }
    }

    const isEnabled = (key: string) => !(currentSettings.excluded_categories || []).includes(key)

    // Combine standard and custom categories for display
    const allDisplayCategories = [
        ...CHECK_CATEGORIES,
        ...OPTIONAL_CATEGORIES,
        ...(currentSettings.custom_categories || []).map(c => ({ ...c, isCustom: true }))
    ]

    return (
        <Card icon={Settings} title="비교 규칙 설정 (Comparison Rules)">
            <p className="text-sm text-muted-foreground mb-4">
                AI가 두 이미지를 비교할 때 <b>무엇을 찾고, 무엇을 무시할지</b> 결정합니다.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* 1. 검사할 항목 (What to Retrieve) */}
                <div className="space-y-4">
                    <div className="flex items-center justify-between">
                        <h3 className="text-sm font-bold flex items-center gap-2 text-primary">
                            <Eye className="w-4 h-4" />
                            반드시 찾아낼 항목 (Categories)
                        </h3>
                        {!isAddingCat && !disabled && (
                            <button
                                onClick={() => setIsAddingCat(true)}
                                className="text-xs text-primary hover:underline flex items-center gap-1"
                            >
                                + 카테고리 추가
                            </button>
                        )}
                    </div>

                    {isAddingCat && (
                        <div className="bg-muted/50 p-3 rounded-lg space-y-2 border border-primary/20">
                            <div className="grid grid-cols-2 gap-2">
                                <input
                                    placeholder="키 (예: logo_change)"
                                    className="text-xs p-1.5 rounded border"
                                    value={newCatKey}
                                    onChange={e => setNewCatKey(e.target.value)}
                                />
                                <input
                                    placeholder="라벨 (예: 로고 변경)"
                                    className="text-xs p-1.5 rounded border"
                                    value={newCatLabel}
                                    onChange={e => setNewCatLabel(e.target.value)}
                                />
                            </div>
                            <input
                                placeholder="설명 (AI가 이해할 수 있게)"
                                className="w-full text-xs p-1.5 rounded border"
                                value={newCatDesc}
                                onChange={e => setNewCatDesc(e.target.value)}
                            />
                            <div className="flex justify-end gap-2">
                                <button onClick={() => setIsAddingCat(false)} className="text-xs px-2 py-1 text-muted-foreground">취소</button>
                                <button
                                    onClick={handleAddCustomCategory}
                                    disabled={!newCatKey || !newCatLabel}
                                    className="text-xs px-3 py-1 bg-primary text-primary-foreground rounded disabled:opacity-50"
                                >
                                    추가
                                </button>
                            </div>
                        </div>
                    )}

                    <div className="space-y-2 max-h-[400px] overflow-y-auto pr-1 custom-scrollbar">
                        {allDisplayCategories.map((cat) => (
                            <div
                                key={cat.key}
                                className={clsx(
                                    "relative group flex items-start gap-3 p-3 rounded-lg border transition-all select-none",
                                    isEnabled(cat.key)
                                        ? "bg-primary/5 border-primary shadow-sm"
                                        : "bg-muted/30 border-transparent opacity-60 grayscale"
                                )}
                            >
                                <div
                                    className="flex-1 flex items-start gap-3 cursor-pointer"
                                    onClick={() => !disabled && toggleCategoryExclusion(cat.key)}
                                >
                                    <div className={clsx(
                                        "mt-0.5 w-5 h-5 rounded-full flex items-center justify-center shrink-0 transition-colors",
                                        isEnabled(cat.key) ? "text-primary" : "text-muted-foreground"
                                    )}>
                                        {isEnabled(cat.key) ? <CheckCircle2 className="w-5 h-5" /> : <XCircle className="w-5 h-5" />}
                                    </div>
                                    <div>
                                        <div className="flex items-center gap-2">
                                            <div className={clsx("text-sm font-bold", isEnabled(cat.key) ? "text-foreground" : "text-muted-foreground")}>
                                                {cat.label}
                                            </div>
                                            {(cat as any).isCustom && (
                                                <span className="text-[10px] px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded-full">Custom</span>
                                            )}
                                        </div>
                                        <div className="text-xs text-muted-foreground mt-0.5">{cat.description}</div>
                                    </div>
                                </div>

                                {/* Delete button for custom categories */}
                                {(cat as any).isCustom && !disabled && (
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation()
                                            handleDeleteCustomCategory(cat.key)
                                        }}
                                        className="absolute top-2 right-2 p-1 text-muted-foreground hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                                    >
                                        <XCircle className="w-4 h-4" />
                                    </button>
                                )}
                            </div>
                        ))}
                    </div>
                </div>

                {/* 2. 세부 민감도 (Noise Filter) */}
                <div className="space-y-4">
                    <h3 className="text-sm font-bold flex items-center gap-2 text-muted-foreground">
                        <EyeOff className="w-4 h-4" />
                        무시할 노이즈 (Sensitivity)
                    </h3>

                    <div className="bg-muted/30 p-4 rounded-lg space-y-4">
                        <div className="flex items-center justify-between">
                            <label className="text-sm">미세 픽셀 노이즈 무시</label>
                            <Switch
                                checked={currentSettings.ignore_compression_noise}
                                onCheckedChange={(c) => handleChange('ignore_compression_noise', c)}
                                disabled={disabled}
                            />
                        </div>

                        <div className="flex items-center justify-between">
                            <label className="text-sm">단순 위치 이동 무시 (Position)</label>
                            <Switch
                                checked={currentSettings.ignore_position_changes}
                                onCheckedChange={(c) => handleChange('ignore_position_changes', c)}
                                disabled={disabled}
                            />
                        </div>

                        <div className="space-y-2 pt-2 border-t">
                            <label className="text-sm font-medium">추가 무시 규칙 (자연어)</label>
                            <textarea
                                value={currentSettings.custom_ignore_rules || ''}
                                onChange={(e) => handleChange('custom_ignore_rules', e.target.value)}
                                placeholder="예: 'QR 코드는 변경되어도 상관없음', '전화번호 변경은 무시해'"
                                className="w-full text-xs h-20 p-2 border rounded-md resize-none"
                                disabled={disabled}
                            />
                            <p className="text-[10px] text-muted-foreground">
                                * AI가 이 규칙을 해석하여 하이브리드 검사 시 반영합니다.
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </Card>
    )
}

