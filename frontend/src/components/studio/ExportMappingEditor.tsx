import { useState, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Plus, Trash2, ChevronDown, ChevronUp, Share2, Layers, Key, CopyPlus, X } from 'lucide-react'
import type { Model, ExportConfig } from '@/types/model'

interface ExportMappingEditorProps {
    model: Model
    onUpdate: (model: Model) => void
}

const DEFAULT_EXPORT_CONFIG: ExportConfig = {
    enabled: false,
    definition: {
        base_table: '',
        merge_keys: [],
        pivot_tables: [],
        final_column_mappings: {},
        conflict_policy: 'first_non_empty',
        group_by_keys: [],
        aggregation_strategy: 'first_non_empty',
        inject_metadata: false
    }
}

export function ExportMappingEditor({ model, onUpdate }: ExportMappingEditorProps) {
    const config: ExportConfig = model.export_config || DEFAULT_EXPORT_CONFIG
    const def = config.definition || DEFAULT_EXPORT_CONFIG.definition

    const [isExpanded, setIsExpanded] = useState(false)
    const [expandedPivotIdx, setExpandedPivotIdx] = useState<number | null>(null)

    // Table fields are those with type === 'array'
    const tableFields = model.fields
        .filter(f => f.type === 'array')
        .map(f => f.key)

    const availableKeys = useMemo(() => {
        const keys = new Set<string>()
        model.fields.forEach(f => {
            if (f.type === 'array' && f.sub_fields) {
                f.sub_fields.forEach(c => keys.add(c.key as string))
            } else {
                keys.add(f.key)
            }
        })
        return Array.from(keys)
    }, [model.fields])

    const updateConfig = (updates: Partial<ExportConfig>) => {
        onUpdate({
            ...model,
            export_config: { ...config, ...updates }
        })
    }

    const updateDef = (updates: Partial<typeof def>) => {
        updateConfig({
            definition: { ...def, ...updates }
        })
    }

    const handleMappingChange = (oldKey: string, newKey: string, val: string) => {
        const newMap = { ...def.final_column_mappings }
        if (oldKey !== newKey) {
            delete newMap[oldKey]
        }
        if (newKey) {
            newMap[newKey] = val
        }
        updateDef({ final_column_mappings: newMap })
    }

    const removeMapping = (key: string) => {
        const newMap = { ...def.final_column_mappings }
        delete newMap[key]
        updateDef({ final_column_mappings: newMap })
    }

    const renderMultiSelect = (label: string, values: string[] = [], onChange: (vals: string[]) => void, placeholder: string) => (
        <div>
            <label className="text-xs font-bold text-muted-foreground block mb-1">{label}</label>
            <div className="flex flex-wrap gap-1.5 mb-1.5 p-1.5 border rounded-md bg-muted/10 min-h-[38px] items-center">
                {values.map(val => (
                    <Badge key={val} variant="secondary" className="flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium font-mono border-emerald-200/50 bg-emerald-50 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300">
                        {val}
                        <button onClick={() => onChange(values.filter(v => v !== val))} className="hover:text-destructive text-emerald-600 ml-0.5">
                            <X className="w-3 h-3" />
                        </button>
                    </Badge>
                ))}
                {values.length === 0 && <span className="text-[10px] text-muted-foreground px-1">선택된 키가 없습니다.</span>}
            </div>
            <select
                className="w-full text-[11px] px-2 py-1.5 rounded border bg-background font-mono text-muted-foreground"
                onChange={e => {
                    if (e.target.value && !values.includes(e.target.value)) {
                        onChange([...values, e.target.value])
                    }
                    e.target.value = "" // reset
                }}
                defaultValue=""
            >
                <option value="" disabled>{placeholder}</option>
                {availableKeys.map(opt => (
                    <option key={opt} value={opt}>{opt}</option>
                ))}
            </select>
        </div>
    )

    return (
        <div className="bg-emerald-50/50 p-3 rounded-lg border border-emerald-100 dark:bg-emerald-900/10 dark:border-emerald-800 mt-4 shadow-sm">
            <div className="flex items-center justify-between cursor-pointer" onClick={() => setIsExpanded(!isExpanded)}>
                <div className="flex items-center gap-3">
                    <div className="bg-emerald-100 dark:bg-emerald-900/40 p-1.5 rounded-md">
                        <Share2 className="w-4 h-4 text-emerald-700 dark:text-emerald-400" />
                    </div>
                    <div>
                        <h3 className="text-sm font-semibold text-emerald-800 dark:text-emerald-300 flex items-center gap-2">
                            내보내기 매핑 엔진 (Deterministic Export)
                        </h3>
                        <p className="text-[10px] text-emerald-700/80 dark:text-emerald-400/70 mt-0.5">
                            복잡한 서차지 구조 등을 한 줄의 Flat Data로 자동 압축 병합하여 Power Automate에 전달합니다.
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
                        <span className="text-xs font-medium text-emerald-800 dark:text-emerald-300">사용 여부</span>
                        <Switch
                            checked={config.enabled}
                            onCheckedChange={(checked) => updateConfig({ enabled: checked })}
                        />
                    </div>
                    {isExpanded ? <ChevronUp className="w-5 h-5 text-emerald-600" /> : <ChevronDown className="w-5 h-5 text-emerald-600" />}
                </div>
            </div>

            {isExpanded && (
                <div className="mt-4 pt-4 border-t border-emerald-200/50 dark:border-emerald-800/50 space-y-5">
                    
                    {/* Basic Settings */}
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="text-xs font-bold text-muted-foreground block mb-1">기준 테이블 (Base Table)</label>
                            <select
                                value={def.base_table}
                                onChange={e => updateDef({ base_table: e.target.value })}
                                className="w-full text-sm px-2 py-1.5 rounded border bg-background shadow-sm"
                            >
                                <option value="">선택</option>
                                {tableFields.map(f => <option key={f} value={f}>{f}</option>)}
                            </select>
                        </div>
                        {renderMultiSelect(
                            "병합/조인 기준 키 (Merge Keys)", 
                            def.merge_keys || [], 
                            (vals) => updateDef({ merge_keys: vals }), 
                            "+ 키 선택 추가..."
                        )}
                    </div>

                    {/* Metadata & Grouping */}
                    <div className="bg-background/80 p-3 rounded-lg border border-emerald-100 dark:border-emerald-800/50 shadow-sm">
                        <h4 className="text-xs font-bold mb-3 flex items-center gap-1.5 text-emerald-800 dark:text-emerald-300">
                            <Layers className="w-3.5 h-3.5" /> 행 병합 & 메타데이터 (Row Grouping & Injection)
                        </h4>
                        <div className="grid grid-cols-2 gap-4">
                            {renderMultiSelect(
                                "데이터 병합 키 (Group By Keys)", 
                                def.group_by_keys || [], 
                                (vals) => updateDef({ group_by_keys: vals }), 
                                "+ 그룹 키 선택 추가..."
                            )}
                            <div>
                                <label className="text-xs font-bold text-muted-foreground block mb-1">
                                    중복 병합 전략 (Aggregation)
                                </label>
                                <select
                                    value={def.aggregation_strategy}
                                    onChange={e => updateDef({ aggregation_strategy: e.target.value })}
                                    className="w-full text-sm px-2 py-1.5 rounded border bg-background shadow-sm mt-[38px]"
                                >
                                    <option value="first_non_empty">최초 비어있지 않은 값 (Coalesce)</option>
                                    <option value="concat">이어 붙이기 (Concat 콤마 구분)</option>
                                    <option value="sum">합계 (Sum, 숫자인 경우만)</option>
                                </select>
                            </div>
                            <div className="col-span-2 flex items-center gap-2 mt-1">
                                <Switch
                                    checked={def.inject_metadata}
                                    onCheckedChange={(checked) => updateDef({ inject_metadata: checked })}
                                    id="inject-meta"
                                />
                                <label htmlFor="inject-meta" className="text-xs font-medium cursor-pointer text-muted-foreground hover:text-foreground">
                                    Power Automate로 유입된 입력 메타데이터(파일명/ID 등)를 결과 행(Row)에 컬럼으로 자동 삽입
                                </label>
                            </div>
                        </div>
                    </div>

                    {/* Pivot Tables */}
                    <div className="bg-background/50 p-2 rounded-lg border border-emerald-100/50 dark:border-emerald-800/30">
                        <div className="flex items-center justify-between mb-2">
                            <h4 className="text-xs font-bold flex items-center gap-1.5 text-emerald-800 dark:text-emerald-300">
                                <CopyPlus className="w-3.5 h-3.5" /> 세로 행 → 가로 열 피벗 정책 (Pivot Tables)
                            </h4>
                            <Button size="sm" variant="outline" className="h-6 text-[10px] px-2 shadow-sm border-emerald-200 hover:bg-emerald-50 dark:border-emerald-800 dark:hover:bg-emerald-900/50" onClick={() => {
                                updateDef({ pivot_tables: [...(def.pivot_tables || []), { table: '', category_field: '', subcategory_field: '', value_field: '', column_naming: '{category_field}_{value_field}' }] })
                                setExpandedPivotIdx(def.pivot_tables ? def.pivot_tables.length : 0)
                            }}>
                                <Plus className="w-3 h-3 mr-1" /> 피벗 추가
                            </Button>
                        </div>
                        
                        <div className="space-y-2">
                            {def.pivot_tables?.map((pivot, idx) => (
                                <div key={idx} className="border rounded-md bg-background shadow-sm overflow-hidden transition-all duration-200">
                                    <div 
                                        className="flex items-center justify-between p-2 cursor-pointer hover:bg-muted/50"
                                        onClick={() => setExpandedPivotIdx(expandedPivotIdx === idx ? null : idx)}
                                    >
                                        <div className="flex items-center gap-2">
                                            {expandedPivotIdx === idx ? <ChevronUp className="w-3.5 h-3.5 text-muted-foreground" /> : <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />}
                                            <span className="text-xs font-semibold text-emerald-800 dark:text-emerald-400">
                                                {pivot.table || `피벗 규칙 ${idx + 1}`}
                                            </span>
                                            {pivot.category_field && (
                                                <Badge variant="outline" className="h-4 text-[9px] px-1 font-mono bg-muted/30 ml-2 border-dashed">{pivot.category_field}</Badge>
                                            )}
                                        </div>
                                        <Button size="sm" variant="ghost" className="h-5 w-5 p-0 text-destructive hover:bg-destructive/10 hover:text-destructive" onClick={(e) => {
                                            e.stopPropagation()
                                            const newPivots = [...def.pivot_tables]
                                            newPivots.splice(idx, 1)
                                            updateDef({ pivot_tables: newPivots })
                                        }}>
                                            <Trash2 className="w-3 h-3" />
                                        </Button>
                                    </div>
                                    {expandedPivotIdx === idx && (
                                        <div className="p-3 border-t grid grid-cols-2 gap-3 bg-muted/10">
                                            <div>
                                                <label className="text-[10px] font-bold text-muted-foreground block mb-1">대상 테이블</label>
                                                <select
                                                    value={pivot.table}
                                                    onChange={e => {
                                                        const p = [...def.pivot_tables]; p[idx].table = e.target.value; updateDef({ pivot_tables: p })
                                                    }}
                                                    className="w-full text-xs px-2 py-1.5 rounded border bg-background shadow-sm"
                                                >
                                                    <option value="">선택</option>
                                                    {tableFields.map(f => <option key={f} value={f}>{f}</option>)}
                                                </select>
                                            </div>
                                            <div>
                                                <label className="text-[10px] font-bold text-muted-foreground block mb-1">이름 명명 규칙 패턴</label>
                                                <input
                                                    type="text"
                                                    value={pivot.column_naming}
                                                    onChange={e => {
                                                        const p = [...def.pivot_tables]; p[idx].column_naming = e.target.value; updateDef({ pivot_tables: p })
                                                    }}
                                                    className="w-full text-xs px-2 py-1.5 rounded border bg-background shadow-sm font-mono text-emerald-700 dark:text-emerald-400"
                                                    placeholder="{category_field}_{value_field}"
                                                />
                                            </div>
                                            <div>
                                                <label className="text-[10px] font-bold text-muted-foreground block mb-1">Category 필드 (예: charge_code)</label>
                                                <select
                                                    value={pivot.category_field || ''}
                                                    onChange={e => {
                                                        const p = [...def.pivot_tables]; p[idx].category_field = e.target.value; updateDef({ pivot_tables: p })
                                                    }}
                                                    className="w-full text-xs px-2 py-1.5 rounded border bg-background shadow-sm font-mono"
                                                >
                                                    <option value="">선택 안함</option>
                                                    {availableKeys.map(k => <option key={k} value={k}>{k}</option>)}
                                                </select>
                                            </div>
                                            <div>
                                                <label className="text-[10px] font-bold text-muted-foreground block mb-1">Subcategory 필드 (예: container)</label>
                                                <select
                                                    value={pivot.subcategory_field || ''}
                                                    onChange={e => {
                                                        const p = [...def.pivot_tables]; p[idx].subcategory_field = e.target.value; updateDef({ pivot_tables: p })
                                                    }}
                                                    className="w-full text-xs px-2 py-1.5 rounded border bg-background shadow-sm font-mono"
                                                >
                                                    <option value="">선택 안함</option>
                                                    {availableKeys.map(k => <option key={k} value={k}>{k}</option>)}
                                                </select>
                                            </div>
                                            <div className="col-span-2">
                                                <label className="text-[10px] font-bold text-muted-foreground block mb-1">Value 추출 필드 (예: amount)</label>
                                                <select
                                                    value={pivot.value_field || ''}
                                                    onChange={e => {
                                                        const p = [...def.pivot_tables]; p[idx].value_field = e.target.value; updateDef({ pivot_tables: p })
                                                    }}
                                                    className="w-full text-xs px-2 py-1.5 rounded border bg-background shadow-sm font-mono"
                                                >
                                                    <option value="">선택 안함</option>
                                                    {availableKeys.map(k => <option key={k} value={k}>{k}</option>)}
                                                </select>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ))}
                            {def.pivot_tables?.length === 0 && (
                                <p className="text-[10px] text-muted-foreground flex items-center justify-center h-8 border border-dashed rounded bg-background/50">
                                    설정된 피벗이 없습니다.
                                </p>
                            )}
                        </div>
                    </div>

                    {/* Final Mappings */}
                    <div className="bg-background/50 p-2 rounded-lg border border-emerald-100/50 dark:border-emerald-800/30">
                        <div className="flex items-center justify-between mb-2">
                            <h4 className="text-xs font-bold flex items-center gap-1.5 text-emerald-800 dark:text-emerald-300">
                                <Key className="w-3.5 h-3.5" /> 최종 결과 스키마 매핑 (Column Mappings)
                            </h4>
                            <Button size="sm" variant="outline" className="h-6 text-[10px] px-2 shadow-sm border-emerald-200 hover:bg-emerald-50 dark:border-emerald-800 dark:hover:bg-emerald-900/50" onClick={() => handleMappingChange('', `Target_Col_${Object.keys(def.final_column_mappings || {}).length + 1}`, availableKeys[0] || 'Source_Col')}>
                                <Plus className="w-3 h-3 mr-1" /> 열 추가
                            </Button>
                        </div>
                        <div className="bg-background rounded-lg border shadow-sm p-3 space-y-2.5">
                            <div className="grid grid-cols-[1fr_auto_1fr_auto] gap-3 px-1 mb-1">
                                <span className="text-[10px] font-bold text-muted-foreground text-center bg-muted/30 py-1 rounded-sm">원본 추출 필드 (Source)</span>
                                <span className="w-4"></span>
                                <span className="text-[10px] font-bold text-muted-foreground text-center bg-muted/30 py-1 rounded-sm">최종 내보내기 열 이름 (Target)</span>
                                <span className="w-6"></span>
                            </div>
                            {Object.entries(def.final_column_mappings || {}).map(([targetCol, sourceCol], idx) => (
                                <div key={idx} className="grid grid-cols-[1fr_auto_1fr_auto] gap-3 items-center group">
                                    <div className="relative">
                                        <select
                                            value={sourceCol}
                                            onChange={e => handleMappingChange(targetCol, targetCol, e.target.value)}
                                            className="text-[11px] font-mono px-2 py-1.5 rounded border w-full bg-emerald-50/50 text-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300 shadow-sm transition-colors hover:border-emerald-300 dark:hover:border-emerald-700"
                                        >
                                            <option value="">선택 안함</option>
                                            <optgroup label="모델 등록 필드 (Fields)">
                                                {availableKeys.map(k => <option key={k} value={k}>{k}</option>)}
                                            </optgroup>
                                            <optgroup label="동적 생성/피벗 필드 (Dynamic)">
                                                {sourceCol && !availableKeys.includes(sourceCol) && <option value={sourceCol}>{sourceCol}</option>}
                                            </optgroup>
                                        </select>
                                    </div>
                                    <span className="text-xs text-muted-foreground font-mono">→</span>
                                    <input
                                        type="text"
                                        value={targetCol}
                                        onChange={e => handleMappingChange(targetCol, e.target.value, sourceCol)}
                                        className="text-xs px-2 py-1.5 rounded border w-full font-semibold shadow-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
                                        placeholder="최종 컬럼명"
                                    />
                                    <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive hover:bg-destructive/10 opacity-50 group-hover:opacity-100 transition-opacity" onClick={() => removeMapping(targetCol)}>
                                        <Trash2 className="w-3.5 h-3.5" />
                                    </Button>
                                </div>
                            ))}
                            {Object.keys(def.final_column_mappings || {}).length === 0 && (
                                <div className="text-[10px] text-muted-foreground text-center py-6 border border-dashed rounded-md bg-muted/10 mx-1">
                                    <Key className="w-4 h-4 mx-auto mb-2 opacity-50" />
                                    매핑이 없습니다. 상단에서 열을 추가하세요.<br/>
                                    (이곳에 선언된 컬럼만 최종 추출 결과물에 포함됩니다.)
                                </div>
                            )}
                        </div>
                    </div>

                    <div className="pt-2 border-t border-emerald-100 dark:border-emerald-800/50">
                        <label className="text-xs font-bold text-muted-foreground block mb-1">선택: 변환 완료 후 알림 전송 웹훅 (Webhook URL)</label>
                        <input
                            type="text"
                            value={config.webhook_url || ''}
                            onChange={e => updateConfig({ webhook_url: e.target.value })}
                            className="w-full text-sm px-2 py-1.5 rounded border bg-background shadow-sm"
                            placeholder="https://prod-10.koreacentral.logic.azure.com:443/workflows/..."
                        />
                    </div>
                </div>
            )}
        </div>
    )
}
