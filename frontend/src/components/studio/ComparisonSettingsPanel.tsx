/* eslint-disable @typescript-eslint/no-explicit-any */

import React from 'react'
import { clsx } from 'clsx'
import { Card } from '@/components/ui/icon-card'
import { Switch } from '@/components/ui/switch'
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
                        {/* Confidence Threshold Slider */}
                        <div className="space-y-2">
                            <div className="flex items-center justify-between">
                                <label htmlFor="confidence-threshold-slider" className="text-sm font-medium">AI 신뢰도 기준</label>
                                <span className="text-sm font-mono tabular-nums text-primary font-bold">
                                    {Math.round((currentSettings.confidence_threshold ?? 0.85) * 100)}%
                                </span>
                            </div>
                            <input
                                id="confidence-threshold-slider"
                                name="confidence-threshold-slider"
                                type="range"
                                min={0.5}
                                max={1.0}
                                step={0.05}
                                value={currentSettings.confidence_threshold ?? 0.85}
                                onChange={(e) => handleChange('confidence_threshold', parseFloat(e.target.value))}
                                disabled={disabled}
                                className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
                            />
                            <div className="flex justify-between text-[10px] text-muted-foreground">
                                <span>50% (관대)</span>
                                <span>100% (엄격)</span>
                            </div>
                            <p className="text-[10px] text-muted-foreground">
                                * 이 기준 이하의 차이점은 자동으로 필터링됩니다.
                            </p>
                        </div>

                        <div className="border-t pt-3 flex items-center justify-between">
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
                            <label htmlFor="custom-ignore-rules" className="text-sm font-medium">추가 무시 규칙 (자연어)</label>
                            <textarea
                                id="custom-ignore-rules"
                                name="custom-ignore-rules"
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

                {/* 3. 검사 아키텍처 (Architecture) */}
                <div className="space-y-4 md:col-span-2 border-t pt-4">
                    <h3 className="text-sm font-bold flex items-center gap-2 text-primary">
                        <Settings className="w-4 h-4" />
                        Component-Based Architecture (3-Layer Pipeline)
                    </h3>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="bg-muted/30 p-4 rounded-lg flex items-center justify-between">
                            <div>
                                <div className="text-sm font-medium">Physical Layer (SSIM)</div>
                                <div className="text-xs text-muted-foreground">물리적 구조 변경 감지 (미세 픽셀 차이)</div>
                            </div>
                            <Switch
                                checked={currentSettings.use_ssim_analysis !== false} // Default to true if undefined
                                onCheckedChange={(c) => handleChange('use_ssim_analysis', c)}
                                disabled={disabled}
                            />
                        </div>

                        <div className="bg-muted/30 p-4 rounded-lg flex items-center justify-between">
                            <div>
                                <div className="text-sm font-medium">Visual Layer (Azure Vision)</div>
                                <div className="text-xs text-muted-foreground">시각적 의미 분석 (색상, 로고, 객체)</div>
                            </div>
                            <Switch
                                checked={currentSettings.use_vision_analysis === true}
                                onCheckedChange={(c) => handleChange('use_vision_analysis', c)}
                                disabled={disabled}
                            />
                        </div>
                    </div>
                </div>
            </div>
        </Card>
    )
}

