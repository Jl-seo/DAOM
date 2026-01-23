
import { clsx } from 'clsx'
import { Card } from '@/components/ui/icon-card'
import { Switch } from '@/components/ui/switch'
import { Slider } from '@/components/ui/slider'
import { Settings, Tags } from 'lucide-react'
import type { ComparisonSettings } from '../ModelStudio'

const ALL_CATEGORIES = [
    { key: 'content', label: '내용 변경', description: '텍스트, 숫자 등 내용 변경' },
    { key: 'layout', label: '레이아웃', description: '구조, 배치 변경' },
    { key: 'style', label: '스타일', description: '색상, 폰트 등 시각적 변경' },
    { key: 'missing_element', label: '누락된 요소', description: '원본에 있던 것이 없어짐' },
    { key: 'added_element', label: '추가된 요소', description: '원본에 없던 것이 추가됨' }
]

interface ComparisonSettingsPanelProps {
    settings: ComparisonSettings | undefined;
    onChange: (settings: ComparisonSettings) => void;
    disabled?: boolean;
}

export function ComparisonSettingsPanel({ settings, onChange, disabled }: ComparisonSettingsPanelProps) {
    // Default values if undefined
    const currentSettings: ComparisonSettings = settings || {
        confidence_threshold: 0.85,
        ignore_position_changes: true,
        ignore_color_changes: false,
        ignore_font_changes: true,
        ignore_compression_noise: true
    }

    const handleChange = (key: keyof ComparisonSettings, value: any) => {
        onChange({
            ...currentSettings,
            [key]: value
        })
    }

    // Category exclusion toggle
    const toggleCategoryExclusion = (categoryKey: string) => {
        const currentExcluded = currentSettings.excluded_categories || []
        const isExcluded = currentExcluded.includes(categoryKey)

        if (isExcluded) {
            // Remove from exclusion
            handleChange('excluded_categories', currentExcluded.filter(c => c !== categoryKey))
        } else {
            // Add to exclusion
            handleChange('excluded_categories', [...currentExcluded, categoryKey])
        }
    }

    const isCategoryEnabled = (categoryKey: string) => {
        const excluded = currentSettings.excluded_categories || []
        return !excluded.includes(categoryKey)
    }

    return (
        <div className="space-y-4">
            <Card icon={Settings} title="비교 민감도 설정">
                <div className="space-y-6">
                    {/* Confidence Threshold */}
                    <div className="space-y-3">
                        <div className="flex items-center justify-between">
                            <label className="text-sm font-medium">신뢰도 임계값</label>
                            <span className="text-sm font-bold text-primary">{Math.round(currentSettings.confidence_threshold * 100)}%</span>
                        </div>
                        <Slider
                            value={[currentSettings.confidence_threshold]}
                            onValueChange={(val: number[]) => handleChange('confidence_threshold', val[0])}
                            min={0.5}
                            max={1.0}
                            step={0.01}
                            disabled={disabled}
                            className="py-2"
                        />
                        <p className="text-xs text-muted-foreground">
                            높을수록 확실한 차이만 리포트 (오탐지 감소)
                        </p>
                    </div>

                    <div className="h-px bg-border" />

                    {/* Ignore Toggles */}
                    <div className="space-y-3">
                        <label className="text-sm font-medium text-muted-foreground">무시할 차이 유형</label>

                        <div className="flex items-center justify-between py-1">
                            <span className="text-sm">이미지 압축 노이즈</span>
                            <Switch
                                checked={currentSettings.ignore_compression_noise ?? true}
                                onCheckedChange={(checked: boolean) => handleChange('ignore_compression_noise', checked)}
                                disabled={disabled}
                            />
                        </div>

                        <div className="flex items-center justify-between py-1">
                            <span className="text-sm">위치/레이아웃 이동</span>
                            <Switch
                                checked={currentSettings.ignore_position_changes}
                                onCheckedChange={(checked: boolean) => handleChange('ignore_position_changes', checked)}
                                disabled={disabled}
                            />
                        </div>

                        <div className="flex items-center justify-between py-1">
                            <span className="text-sm">폰트 스타일</span>
                            <Switch
                                checked={currentSettings.ignore_font_changes}
                                onCheckedChange={(checked: boolean) => handleChange('ignore_font_changes', checked)}
                                disabled={disabled}
                            />
                        </div>

                        <div className="flex items-center justify-between py-1">
                            <span className="text-sm">색상 변경</span>
                            <Switch
                                checked={currentSettings.ignore_color_changes}
                                onCheckedChange={(checked: boolean) => handleChange('ignore_color_changes', checked)}
                                disabled={disabled}
                            />
                        </div>
                    </div>

                    <div className="h-px bg-border" />

                    {/* Category Filter */}
                    <div className="space-y-3">
                        <label className="text-sm font-medium flex items-center gap-2">
                            <Tags className="w-4 h-4" />
                            감지할 카테고리
                        </label>
                        <div className="grid grid-cols-2 gap-2">
                            {ALL_CATEGORIES.map(cat => (
                                <button
                                    key={cat.key}
                                    onClick={() => !disabled && toggleCategoryExclusion(cat.key)}
                                    disabled={disabled}
                                    className={clsx(
                                        "px-3 py-2 text-left text-sm rounded-md border transition-colors",
                                        isCategoryEnabled(cat.key)
                                            ? "bg-primary/10 border-primary text-primary"
                                            : "bg-muted/50 border-transparent text-muted-foreground line-through"
                                    )}
                                >
                                    {cat.label}
                                </button>
                            ))}
                        </div>
                        <p className="text-xs text-muted-foreground">
                            비활성화된 카테고리는 아예 감지하지 않습니다. 예: style을 끄면 색상/스타일 관련 차이 미감지
                        </p>
                    </div>

                    <div className="h-px bg-border" />

                    {/* Custom Rules */}
                    <div className="space-y-2">
                        <label className="text-sm font-medium">추가 무시 규칙 (자연어)</label>
                        <textarea
                            value={currentSettings.custom_ignore_rules || ''}
                            onChange={(e) => handleChange('custom_ignore_rules', e.target.value)}
                            placeholder="예: 'QR코드 변경은 무시해', '바코드 위치는 중요하지 않아'"
                            disabled={disabled}
                            className="w-full h-20 px-3 py-2 text-sm border rounded-md resize-none bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                        />
                    </div>
                </div>
            </Card>
        </div>
    )
}
