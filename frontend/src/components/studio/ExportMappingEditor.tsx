import { useState, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Plus, Trash2, ChevronDown, ChevronUp, Share2, Layers, Key, CopyPlus, X, AlertTriangle, Wand2, Table } from 'lucide-react'
import type { Model, ExportConfig, Field, ColumnMappingDef } from '@/types/model'

interface ExportMappingEditorProps {
    model: Model
    onUpdate: (model: Model) => void
}

function createDefaultExportConfig(): ExportConfig {
    return {
        enabled: false,
        definition: {
            base_table: '',
            merge_keys: [],
            pivot_tables: [],
            final_column_mappings: [],
            conflict_policy: 'first_non_empty',
            group_by_keys: [],
            aggregation_strategy: 'first_non_empty',
            inject_metadata: false
        }
    }
}

const isTableLikeField = (f: Field) => ['array', 'table', 'list'].includes(f.type)

// -- Subcomponent: MultiKeySelector --
function MultiKeySelector({ 
    label, 
    values = [], 
    options, 
    onChange, 
    placeholder,
    tooltip
}: { 
    label: string, 
    values: string[], 
    options: { value: string, label: string }[], 
    onChange: (vals: string[]) => void, 
    placeholder: string,
    tooltip?: string
}) {
    return (
        <div>
            <div className="flex items-center gap-1 mb-1">
                <label className="text-xs font-bold text-muted-foreground block">{label}</label>
                {tooltip && <span className="text-[9px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded-full">{tooltip}</span>}
            </div>
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
                {options.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
            </select>
        </div>
    )
}

export function ExportMappingEditor({ model, onUpdate }: ExportMappingEditorProps) {
    const config: ExportConfig = model.export_config || createDefaultExportConfig()
    const rawDef = config.definition || createDefaultExportConfig().definition
    const finalMappingsRaw = rawDef.final_column_mappings as any
    const finalMappings: ColumnMappingDef[] = Array.isArray(finalMappingsRaw) 
        ? finalMappingsRaw 
        : Object.entries(finalMappingsRaw || {}).map(([target, source]) => ({ target, source: String(source) }))
        
    const def = {
        ...rawDef,
        final_column_mappings: finalMappings
    }

    const [isExpanded, setIsExpanded] = useState(false)
    const [showAdvanced, setShowAdvanced] = useState(false)
    const [expandedPivotIdx, setExpandedPivotIdx] = useState<number | null>(null)
    const [targetError, setTargetError] = useState<string | null>(null)

    const tableFields = model.fields
        .filter(isTableLikeField)
        .map(f => f.key)

    const availableKeyOptions = useMemo(() => {
        const options: { value: string, label: string, source: string }[] = []
        model.fields.forEach(f => {
            if (isTableLikeField(f) && f.sub_fields) {
                f.sub_fields.forEach(c => {
                    options.push({ value: c.key as string, label: `${c.key} (${f.key})`, source: f.key })
                })
            } else {
                options.push({ value: f.key, label: f.key, source: 'scalar' })
            }
        })
        const seen = new Set<string>()
        return options.filter(opt => {
            if (seen.has(opt.value)) return false
            seen.add(opt.value)
            return true
        })
    }, [model.fields])

    const availableKeysFlat = availableKeyOptions.map(o => o.value)

    const validationErrors = useMemo(() => {
        const errors: string[] = []
        if (config.enabled) {
            if (def.merge_keys?.length > 0 && !def.base_table) {
                errors.push("메인 데이터(Base Table)를 선택해야 연결 조건을 사용할 수 있습니다.")
            }
            if (def.final_column_mappings.length === 0) {
                errors.push("최종 결과 스키마(열)가 비어있습니다. 적어도 1개의 열 매핑이 필요합니다.")
            }
            const targets = def.final_column_mappings.map(m => m.target)
            if (new Set(targets).size !== targets.length) {
                errors.push("최종 내보내기 열 이름(Target)에 중복된 값이 존재합니다.")
            }
        }
        return errors
    }, [config.enabled, def.base_table, def.merge_keys, def.final_column_mappings])

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

    const autoConfigureExport = () => {
        const tableOpts = model.fields.filter(isTableLikeField)
        const baseTable = tableOpts.find(f => f.key.toLowerCase().includes('basic') || f.key.toLowerCase().includes('rate'))?.key || tableOpts[0]?.key || ''
        const surchargeTable = tableOpts.find(f => f.key.toLowerCase().includes('surcharge') || f.key.toLowerCase().includes('optional'))?.key || ''
        
        let mergeKeys = [...(def.merge_keys || [])]
        const baseSubFields = model.fields.find(f => f.key === baseTable)?.sub_fields || []
        const polField = baseSubFields.find(sf => (sf as any).key.toLowerCase() === 'pol')
        const podField = baseSubFields.find(sf => (sf as any).key.toLowerCase() === 'pod')
        
        if (polField && !mergeKeys.includes('pol')) mergeKeys.push('pol')
        if (podField && !mergeKeys.includes('pod')) mergeKeys.push('pod')

        const startPivots = surchargeTable ? [{
            table: surchargeTable,
            category_field: 'charge_code',
            subcategory_field: 'container',
            value_field: 'amount',
            column_naming: '{category_field}_{subcategory_field}'
        }] : []

        const pivot_tables = def.pivot_tables && def.pivot_tables.length > 0 ? def.pivot_tables : startPivots

        const mappings: ColumnMappingDef[] = []
        if (polField) mappings.push({ target: 'POL', source: 'pol' })
        if (podField) mappings.push({ target: 'POD', source: 'pod' });
        
        ['20dc', '20gp', '40dc', '40gp', '40hc'].forEach(sz => {
            if (baseSubFields.find(sf => (sf as any).key.toLowerCase() === sz)) mappings.push({ target: sz.toUpperCase(), source: sz })
        })
        
        // Ensure we don't overwrite user's existing mappings if they are already substantial
        const finalMaps = def.final_column_mappings.length > 0 ? def.final_column_mappings : mappings

        updateDef({
            base_table: baseTable,
            merge_keys: mergeKeys,
            pivot_tables,
            final_column_mappings: finalMaps,
            group_by_keys: mergeKeys,
            aggregation_strategy: 'first_non_empty'
        })
        setTargetError(null)
    }

    const handleMappingChange = (idx: number, field: 'target' | 'source', val: string) => {
        setTargetError(null)
        const newMappings = [...def.final_column_mappings]
        
        if (field === 'target') {
            if (newMappings.some((m, i) => i !== idx && m.target === val)) {
                setTargetError(`'${val}' 이름은 이미 사용 중입니다.`)
            }
        }
        
        newMappings[idx] = { ...newMappings[idx], [field]: val }
        updateDef({ final_column_mappings: newMappings })
    }

    const addMapping = () => {
        const newTarget = `Target_Col_${def.final_column_mappings.length + 1}`
        updateDef({ 
            final_column_mappings: [...def.final_column_mappings, { target: newTarget, source: availableKeyOptions[0]?.value || 'Source_Col' }] 
        })
    }

    const removeMapping = (idx: number) => {
        const newMappings = [...def.final_column_mappings]
        newMappings.splice(idx, 1)
        updateDef({ final_column_mappings: newMappings })
    }

    const moveMapping = (idx: number, direction: 'up' | 'down') => {
        if (direction === 'up' && idx > 0) {
            const newMappings = [...def.final_column_mappings]
            const temp = newMappings[idx - 1]
            newMappings[idx - 1] = newMappings[idx]
            newMappings[idx] = temp
            updateDef({ final_column_mappings: newMappings })
        } else if (direction === 'down' && idx < def.final_column_mappings.length - 1) {
            const newMappings = [...def.final_column_mappings]
            const temp = newMappings[idx + 1]
            newMappings[idx + 1] = newMappings[idx]
            newMappings[idx] = temp
            updateDef({ final_column_mappings: newMappings })
        }
    }

    return (
        <div className="bg-emerald-50/50 p-3 rounded-lg border border-emerald-100 dark:bg-emerald-900/10 dark:border-emerald-800 mt-4 shadow-sm">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3 cursor-pointer flex-1" onClick={() => setIsExpanded(!isExpanded)}>
                    <div className="bg-emerald-100 dark:bg-emerald-900/40 p-1.5 rounded-md">
                        <Share2 className="w-4 h-4 text-emerald-700 dark:text-emerald-400" />
                    </div>
                    <div>
                        <h3 className="text-sm font-semibold text-emerald-800 dark:text-emerald-300 flex items-center gap-2">
                            내보내기 매핑 마법사 (Excel Export Shaping)
                        </h3>
                        <p className="text-[10px] text-emerald-700/80 dark:text-emerald-400/70 mt-0.5">
                            복잡하게 나뉜 데이터(기본 운임, 부대비용 등)를 평범한 엑셀(Flat) 표 1장으로 예쁘게 병합합니다.
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                        <span className="text-xs font-medium text-emerald-800 dark:text-emerald-300">자동 병합 내보내기 켜기</span>
                        <Switch
                            checked={config.enabled}
                            onCheckedChange={(checked) => updateConfig({ enabled: checked })}
                        />
                    </div>
                    <button onClick={() => setIsExpanded(!isExpanded)} className="p-1 hover:bg-emerald-100 dark:hover:bg-emerald-900/50 rounded transition-colors">
                        {isExpanded ? <ChevronUp className="w-5 h-5 text-emerald-600" /> : <ChevronDown className="w-5 h-5 text-emerald-600" />}
                    </button>
                </div>
            </div>

            {isExpanded && (
                <div className="mt-4 pt-4 border-t border-emerald-200/50 dark:border-emerald-800/50 space-y-5">
                    
                    <div className="flex justify-end">
                        <Button
                            variant="default"
                            size="sm"
                            className="h-8 text-[11px] bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm"
                            onClick={autoConfigureExport}
                        >
                            <Wand2 className="w-3.5 h-3.5 mr-1.5" /> ✨ 운임표 표준 내보내기 자동 셋팅
                        </Button>
                    </div>

                    {validationErrors.length > 0 && (
                        <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/50 rounded-md p-3">
                            <h4 className="flex items-center gap-1.5 text-xs font-bold text-amber-800 dark:text-amber-300 mb-1.5">
                                <AlertTriangle className="w-3.5 h-3.5" /> 설정 오류 (저장 전 확인 요망)
                            </h4>
                            <ul className="list-disc pl-5 text-[11px] text-amber-700/90 dark:text-amber-400/80 space-y-0.5">
                                {validationErrors.map((err, i) => <li key={i}>{err}</li>)}
                            </ul>
                        </div>
                    )}

                    {/* Basic Settings */}
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <div className="flex items-center gap-1 mb-1">
                                <label className="text-xs font-bold text-muted-foreground block">메인 데이터 (행 단위 생성)</label>
                                <span className="text-[9px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded-full">Base Table</span>
                            </div>
                            <select
                                value={def.base_table}
                                onChange={e => updateDef({ base_table: e.target.value })}
                                className="w-full text-sm px-2 py-1.5 rounded border bg-background shadow-sm"
                            >
                                <option value="">선택 안함</option>
                                {tableFields.map(f => <option key={f} value={f}>{f}</option>)}
                            </select>
                            <p className="text-[10px] text-muted-foreground mt-1 opacity-80">최종 엑셀의 각 행(Row) 기준이 될 데이터를 선택하세요.</p>
                        </div>
                        <MultiKeySelector
                            label="데이터 연결 조건"
                            tooltip="Merge Keys"
                            values={def.merge_keys || []}
                            options={availableKeyOptions}
                            placeholder="+ 연결할 키 선택 추가..."
                            onChange={(vals) => updateDef({ merge_keys: vals })}
                        />
                    </div>

                    {/* Pivot Tables */}
                    <div className="bg-background/50 p-2 rounded-lg border border-emerald-100/50 dark:border-emerald-800/30">
                        <div className="flex items-center justify-between mb-2">
                            <div>
                                <h4 className="text-xs font-bold flex items-center gap-1.5 text-emerald-800 dark:text-emerald-300">
                                    <CopyPlus className="w-3.5 h-3.5" /> 부가 데이터 세로 → 가로로 이어붙이기
                                </h4>
                                <p className="text-[9px] text-muted-foreground ml-5 mt-0.5">Surcharge처럼 세로로 나열되는 항목들을 우측으로 길게 펼쳐줍니다.</p>
                            </div>
                            <Button size="sm" variant="outline" className="h-6 text-[10px] px-2 shadow-sm border-emerald-200 hover:bg-emerald-50 dark:border-emerald-800 dark:hover:bg-emerald-900/50" onClick={() => {
                                updateDef({ pivot_tables: [...(def.pivot_tables || []), { table: '', category_field: '', subcategory_field: '', value_field: '', column_naming: '{category_field}_{value_field}' }] })
                                setExpandedPivotIdx(def.pivot_tables ? def.pivot_tables.length : 0)
                            }}>
                                <Plus className="w-3 h-3 mr-1" /> 항목 추가
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
                                                {pivot.table || `규칙 ${idx + 1}`}
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
                                                        const newPivots = def.pivot_tables.map((item, i) => i === idx ? { ...item, table: e.target.value } : item)
                                                        updateDef({ pivot_tables: newPivots })
                                                    }}
                                                    className="w-full text-xs px-2 py-1.5 rounded border bg-background shadow-sm"
                                                >
                                                    <option value="">선택 안함</option>
                                                    {tableFields.map(f => <option key={f} value={f}>{f}</option>)}
                                                </select>
                                            </div>
                                            <div>
                                                <label className="text-[10px] font-bold text-muted-foreground block mb-1">새로운 열 표기방식 (예: {'{category}'})</label>
                                                <input
                                                    type="text"
                                                    value={pivot.column_naming}
                                                    onChange={e => {
                                                        const newPivots = def.pivot_tables.map((item, i) => i === idx ? { ...item, column_naming: e.target.value } : item)
                                                        updateDef({ pivot_tables: newPivots })
                                                    }}
                                                    className="w-full text-xs px-2 py-1.5 rounded border bg-background shadow-sm font-mono text-emerald-700 dark:text-emerald-400"
                                                    placeholder="{category_field}_{subcategory_field}"
                                                    title="{category_field}와 {subcategory_field} 매크로 변수를 사용하여 컬럼명을 동적으로 생성합니다."
                                                />
                                            </div>
                                            <div>
                                                <label className="text-[10px] font-bold text-muted-foreground block mb-1">헤더 이름 기준이 될 필드 (예: charge_code)</label>
                                                <select
                                                    value={pivot.category_field || ''}
                                                    onChange={e => {
                                                        const newPivots = def.pivot_tables.map((item, i) => i === idx ? { ...item, category_field: e.target.value } : item)
                                                        updateDef({ pivot_tables: newPivots })
                                                    }}
                                                    className="w-full text-xs px-2 py-1.5 rounded border bg-background shadow-sm font-mono"
                                                >
                                                    <option value="">선택 안함</option>
                                                    {availableKeyOptions.map(k => <option key={k.value} value={k.value}>{k.label}</option>)}
                                                </select>
                                            </div>
                                            <div>
                                                <label className="text-[10px] font-bold text-muted-foreground block mb-1">구분 필드 (예: container size)</label>
                                                <select
                                                    value={pivot.subcategory_field || ''}
                                                    onChange={e => {
                                                        const newPivots = def.pivot_tables.map((item, i) => i === idx ? { ...item, subcategory_field: e.target.value } : item)
                                                        updateDef({ pivot_tables: newPivots })
                                                    }}
                                                    className="w-full text-xs px-2 py-1.5 rounded border bg-background shadow-sm font-mono"
                                                >
                                                    <option value="">선택 안함</option>
                                                    {availableKeyOptions.map(k => <option key={k.value} value={k.value}>{k.label}</option>)}
                                                </select>
                                            </div>
                                            <div className="col-span-2">
                                                <label className="text-[10px] font-bold text-muted-foreground block mb-1">실제 값으로 채울 필드 (예: amount مبلغ)</label>
                                                <select
                                                    value={pivot.value_field || ''}
                                                    onChange={e => {
                                                        const newPivots = def.pivot_tables.map((item, i) => i === idx ? { ...item, value_field: e.target.value } : item)
                                                        updateDef({ pivot_tables: newPivots })
                                                    }}
                                                    className="w-full text-xs px-2 py-1.5 rounded border bg-background shadow-sm font-mono"
                                                >
                                                    <option value="">선택 안함</option>
                                                    {availableKeyOptions.map(k => <option key={k.value} value={k.value}>{k.label}</option>)}
                                                </select>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ))}
                            {def.pivot_tables?.length === 0 && (
                                <p className="text-[10px] text-muted-foreground flex items-center justify-center h-8 border border-dashed rounded bg-background/50">
                                    추가된 항목이 없습니다.
                                </p>
                            )}
                        </div>
                    </div>

                    {/* Final Mappings */}
                    <div className="bg-background/50 p-2 rounded-lg border border-emerald-100/50 dark:border-emerald-800/30">
                        <div className="flex items-center justify-between mb-2">
                            <div>
                                <h4 className="text-xs font-bold flex items-center gap-1.5 text-emerald-800 dark:text-emerald-300">
                                    <Key className="w-3.5 h-3.5" /> 최종 결과 엑셀 컬럼 매핑 (Schema Mapping)
                                </h4>
                                <p className="text-[9px] text-muted-foreground ml-5 mt-0.5">이곳에 작성돤 순서와 이름(Target)대로 엑셀이 추출됩니다.</p>
                            </div>
                            <div className="flex items-center gap-2">
                                {targetError && <span className="text-[10px] text-destructive font-semibold bg-destructive/10 px-2 py-0.5 rounded animate-pulse">{targetError}</span>}
                                <Button size="sm" variant="outline" className="h-6 text-[10px] px-2 shadow-sm border-emerald-200 hover:bg-emerald-50 dark:border-emerald-800 dark:hover:bg-emerald-900/50" onClick={addMapping}>
                                    <Plus className="w-3 h-3 mr-1" /> 열 추가
                                </Button>
                            </div>
                        </div>
                        <div className="bg-background rounded-lg border shadow-sm p-3 space-y-2.5">
                            <div className="grid grid-cols-[1fr_auto_1fr_auto_auto] gap-2 px-1 mb-1 items-center">
                                <span className="text-[10px] font-bold text-muted-foreground text-center bg-muted/30 py-1 rounded-sm">결과에 반영될 데이터 (Source)</span>
                                <span className="w-4"></span>
                                <span className="text-[10px] font-bold text-muted-foreground text-center bg-emerald-50 py-1 rounded-sm text-emerald-800 border border-emerald-200/50">최종 출력될 이름 (Target)</span>
                                <span className="w-6 text-center text-[10px] text-muted-foreground">순서</span>
                                <span className="w-7 text-center"></span>
                            </div>
                            {def.final_column_mappings.map((mapping, idx) => (
                                <div key={idx} className="grid grid-cols-[1fr_auto_1fr_auto_auto] gap-2 items-center group bg-background transition-colors hover:bg-muted/30 -mx-2 px-2 py-1 rounded-md">
                                    <div className="relative">
                                        <select
                                            value={mapping.source}
                                            onChange={e => handleMappingChange(idx, 'source', e.target.value)}
                                            className="text-[11px] font-mono px-2 py-1.5 rounded border w-full bg-slate-50 text-slate-700 dark:bg-slate-900/50 dark:text-slate-300 shadow-sm transition-colors hover:border-slate-300"
                                        >
                                            <option value="">선택 안함</option>
                                            <optgroup label="모델 원본 필드">
                                                {availableKeyOptions.map(k => <option key={k.value} value={k.value}>{k.label}</option>)}
                                            </optgroup>
                                            <optgroup label="피벗/동적 생성 항목 (직접 선언된 이름)">
                                                {mapping.source && !availableKeysFlat.includes(mapping.source) && <option value={mapping.source}>{mapping.source}</option>}
                                            </optgroup>
                                        </select>
                                    </div>
                                    <span className="text-xs text-muted-foreground font-mono opacity-50">→</span>
                                    <input
                                        type="text"
                                        value={mapping.target}
                                        onChange={e => handleMappingChange(idx, 'target', e.target.value)}
                                        className="text-[11.5px] px-2 py-1.5 rounded border w-full font-semibold shadow-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 bg-emerald-50/10"
                                        placeholder="엑셀 헤더 열 명칭"
                                    />
                                    <div className="flex flex-col gap-0 items-center justify-center">
                                        <button disabled={idx === 0} onClick={() => moveMapping(idx, 'up')} className="text-muted-foreground hover:text-emerald-600 disabled:opacity-20 flex pt-1"><ChevronUp className="w-3.5 h-3.5" /></button>
                                        <button disabled={idx === def.final_column_mappings.length - 1} onClick={() => moveMapping(idx, 'down')} className="text-muted-foreground hover:text-emerald-600 disabled:opacity-20 flex pb-1"><ChevronDown className="w-3.5 h-3.5" /></button>
                                    </div>
                                    <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive hover:bg-destructive/10" onClick={() => removeMapping(idx)}>
                                        <Trash2 className="w-3.5 h-3.5" />
                                    </Button>
                                </div>
                            ))}
                            {def.final_column_mappings.length === 0 && (
                                <div className="text-[10px] text-muted-foreground text-center py-6 border border-dashed rounded-md bg-muted/10 mx-1">
                                    <Key className="w-4 h-4 mx-auto mb-2 opacity-30" />
                                    출력 엑셀의 컬럼이 하나도 없습니다.<br/>
                                </div>
                            )}
                        </div>
                    </div>
                    
                    {/* Live Preview UI */}
                    {def.final_column_mappings.length > 0 && (
                        <div className="bg-white dark:bg-slate-900 border shadow-sm p-3 rounded-md overflow-hidden animate-in fade-in duration-300">
                            <h4 className="text-[11px] font-bold flex items-center gap-1.5 text-slate-700 dark:text-slate-300 mb-2">
                                <Table className="w-3.5 h-3.5" /> 최종 결과 엑셀 형태 예상도 (Live Preview)
                            </h4>
                            <div className="overflow-x-auto pb-1">
                                <table className="w-full text-left border-collapse min-w-max">
                                    <thead>
                                        <tr>
                                            {def.final_column_mappings.map(m => (
                                                <th key={m.target} className="border bg-emerald-50/50 dark:bg-emerald-900/20 text-emerald-800 dark:text-emerald-300 font-bold text-[10px] px-2 py-1.5 whitespace-nowrap">
                                                    {m.target || '(이름없음)'}
                                                </th>
                                            ))}
                                            {def.pivot_tables && def.pivot_tables.length > 0 && (
                                                <th className="border bg-amber-50/50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 font-bold text-[10px] px-2 py-1.5 whitespace-nowrap italic">
                                                    + (피벗으로 펼쳐지는 열들...)
                                                </th>
                                            )}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        <tr>
                                            {def.final_column_mappings.map((m, i) => (
                                                <td key={i} className="border text-[9px] px-2 py-1.5 text-muted-foreground font-mono bg-slate-50/50 dark:bg-slate-800/50 whitespace-nowrap">
                                                    {m.source ? `[${m.source}]` : '...'}
                                                </td>
                                            ))}
                                            {def.pivot_tables && def.pivot_tables.length > 0 && (
                                                <td className="border text-[9px] px-2 py-1.5 text-muted-foreground font-mono bg-slate-50/50 dark:bg-slate-800/50">
                                                    ...
                                                </td>
                                            )}
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {/* Advanced Options Toggle */}
                    <div className="border-t border-dashed mt-6 pt-4">
                        <Button 
                            variant="ghost" 
                            size="sm" 
                            className="text-xs text-muted-foreground hover:text-foreground w-full flex justify-between px-2"
                            onClick={() => setShowAdvanced(!showAdvanced)}
                        >
                            <span className="flex items-center gap-1.5"><Layers className="w-3.5 h-3.5" /> 고급 옵션 (다중 중복 데이터 그룹핑 처리)</span>
                            {showAdvanced ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                        </Button>
                        
                        {showAdvanced && (
                            <div className="mt-4 bg-background/80 p-3 rounded-lg border border-emerald-100 dark:border-emerald-800/50 shadow-sm animate-in slide-in-from-top-2">
                                <div className="grid grid-cols-2 gap-4">
                                    <MultiKeySelector
                                        label="데이터 중복 그룹핑 키"
                                        tooltip="Group By Keys"
                                        values={def.group_by_keys || []}
                                        options={availableKeyOptions}
                                        placeholder="+ 그룹 식별 기준 키 추가..."
                                        onChange={(vals) => updateDef({ group_by_keys: vals })}
                                    />
                                    <div>
                                        <div className="flex items-center gap-1 mb-1">
                                            <label className="text-xs font-bold text-muted-foreground block">중복된 항목이 있을 때 처리 방법</label>
                                            <span className="text-[9px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded-full">Aggregation</span>
                                        </div>
                                        <select
                                            value={def.aggregation_strategy}
                                            onChange={e => updateDef({ aggregation_strategy: e.target.value })}
                                            className="w-full text-sm px-2 py-1.5 rounded border bg-background shadow-sm mt-[38px]"
                                        >
                                            <option value="first_non_empty">최초 비어있지 않은 값 채택 (Coalesce)</option>
                                            <option value="concat">글자들을 이어 붙이기 (콤마 구분)</option>
                                            <option value="sum">합계 (숫자인 경우만 연산)</option>
                                        </select>
                                    </div>
                                    <div className="col-span-2 flex items-center gap-2 mt-1">
                                        <Switch
                                            checked={def.inject_metadata}
                                            onCheckedChange={(checked) => updateDef({ inject_metadata: checked })}
                                            id="inject-meta"
                                        />
                                        <label htmlFor="inject-meta" className="text-xs font-medium cursor-pointer text-muted-foreground hover:text-foreground">
                                            앱 외부에서 들어온 파일명이나 ID(메타데이터)를 결과 행 가장 첫 열에 함께 삽입합니다.
                                        </label>
                                    </div>
                                    <div className="col-span-2 mt-2 pt-3 border-t border-emerald-100 dark:border-emerald-800/50">
                                        <label className="text-xs font-bold text-muted-foreground flex items-center gap-1.5 mb-1.5">
                                            <Share2 className="w-3.5 h-3.5" /> 자동화 시스템에 결과 통보 (선택)
                                        </label>
                                        <input
                                            type="text"
                                            value={config.webhook_url || ''}
                                            onChange={e => updateConfig({ webhook_url: e.target.value })}
                                            className="w-full text-[11.5px] px-2 py-1.5 rounded border bg-background shadow-sm font-mono text-muted-foreground"
                                            placeholder="https://prod-10.koreacentral.logic.azure.com:443/workflows/..."
                                        />
                                        <p className="text-[9px] text-muted-foreground mt-1 ml-1 opacity-70">Power Automate URL 등을 등록하시면, 엑셀 병합 처리가 완료된 즉시 결과(JSON)를 쏩니다.</p>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    )
}
