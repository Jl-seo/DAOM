import { CheckCircle2, ScanLine, AlertCircle } from 'lucide-react'
import { Card } from '@/components/ui/card'
import type { Field } from '../../types/model'

interface DexSettingsPanelProps {
    fields: Field[]
    onChange: (fields: Field[]) => void
    disabled?: boolean
}

export function DexSettingsPanel({ fields, onChange, disabled = false }: DexSettingsPanelProps) {
    const targetField = fields.find(f => f.is_dex_target)

    const handleSetTarget = (fieldKey: string) => {
        if (disabled) return

        const newFields = fields.map(f => ({
            ...f,
            is_dex_target: f.key === fieldKey
        }))
        onChange(newFields)
    }

    const handleClearTarget = () => {
        if (disabled) return

        const newFields = fields.map(f => ({
            ...f,
            is_dex_target: false
        }))
        onChange(newFields)
    }

    return (
        <Card className="p-5 space-y-4 border border-blue-100 bg-blue-50/30">
            <div className="flex items-start justify-between">
                <div>
                    <h3 className="text-sm font-semibold flex items-center text-blue-900">
                        <ScanLine className="w-4 h-4 mr-2" />
                        DEX 바코드 교차 검증 (Target Mapping)
                    </h3>
                    <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                        추출 스키마 중 하나를 선택하면, <strong>실시간 바코드 스캔 결과(LIS 정답)</strong>와 <strong>LLM 추출 결과</strong>를 자동 대조하여 일치 여부를 판별합니다.
                    </p>
                </div>
            </div>

            <div className="bg-white rounded-lg border p-4">
                <div className="flex flex-col space-y-3">
                    <label className="text-xs font-medium text-slate-700">대조할 기준 필드 (DEX Target)</label>

                    {fields.length === 0 ? (
                        <div className="text-xs text-muted-foreground italic py-2">
                            먼저 상단에서 필드를 추가해주세요.
                        </div>
                    ) : (
                        <div className="flex items-center gap-3">
                            <select
                                value={targetField?.key || ''}
                                onChange={(e) => {
                                    if (e.target.value === '') {
                                        handleClearTarget()
                                    } else {
                                        handleSetTarget(e.target.value)
                                    }
                                }}
                                disabled={disabled}
                                className="flex h-9 w-[280px] rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                            >
                                <option value="">사용 안 함 (DEX 검증 끄기)</option>
                                {fields.map(f => (
                                    <option key={f.key} value={f.key}>
                                        {f.key} {f.label ? `(${f.label})` : ''}
                                    </option>
                                ))}
                            </select>

                            {targetField && (
                                <div className="flex items-center text-xs text-emerald-600 bg-emerald-50 px-2 py-1.5 rounded-md border border-emerald-100">
                                    <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />
                                    바코드 인식 시 '{targetField.key}' 값을 검증합니다
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>

            {targetField && (
                <div className="flex items-start bg-amber-50 text-amber-800 p-3 rounded-md text-xs border border-amber-100">
                    <AlertCircle className="w-4 h-4 mr-2 shrink-0 mt-0.5 text-amber-600" />
                    <div>
                        <strong>주의사항:</strong> 이 설정이 켜져있을 경우, 웹캠 스캐너 또는 바코드 리더기를 통해 바코드를 선행 스캔해야 전체 검증 파이프라인이 동작합니다. 바코드가 없는 일반 문서는 지속적으로 검증 실패 오류가 발생할 수 있습니다.
                    </div>
                </div>
            )}
        </Card>
    )
}
