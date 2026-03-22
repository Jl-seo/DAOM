import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Plus, Trash2, ChevronDown, ChevronUp, Share2, Layers, Key, CopyPlus } from 'lucide-react'
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

    return (
        <div className="bg-emerald-50/50 p-3 rounded-lg border border-emerald-100 dark:bg-emerald-900/10 dark:border-emerald-800 mt-4">
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
                                className="w-full text-sm px-2 py-1.5 rounded border bg-background"
                            >
                                <option value="">선택</option>
                                {tableFields.map(f => <option key={f} value={f}>{f}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="text-xs font-bold text-muted-foreground block mb-1">병합/조인 기준 키 (Merge Keys, 콤마 구분)</label>
                            <input
                                type="text"
                                value={def.merge_keys?.join(', ')}
                                onChange={e => updateDef({ merge_keys: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
                                className="w-full text-sm px-2 py-1.5 rounded border bg-background"
                                placeholder="예: charge_code, container"
                            />
                        </div>
                    </div>

                    {/* Metadata & Grouping */}
                    <div className="bg-background/50 p-3 rounded-lg border border-emerald-100 dark:border-emerald-800/50">
           <h4 className="text-xs font-bold mb-3 flex items-center gap-1.5">
               <Layers className="w-3.5 h-3.5" /> 행 병합 & 메타데이터 (Row Grouping & Injection)
           </h4>
           <div className="grid grid-cols-2 gap-4">
               <div>
                   <label className="text-xs font-medium text-muted-foreground flex items-center justify-between mb-1">
                       <span>데이터 병합 키 (Group By Keys, 콤마 구분)</span>
                   </label>
                   <input
                       type="text"
                       value={def.group_by_keys?.join(', ')}
                       onChange={e => updateDef({ group_by_keys: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
                       className="w-full text-sm px-2 py-1.5 rounded border bg-background"
                       placeholder="예: POL_NAME, POD_NAME 등 기준 열"
                   />
               </div>
               <div>
                   <label className="text-xs font-medium text-muted-foreground block mb-1">
                       중복 병합 전략 (Aggregation)
                   </label>
                   <select
                       value={def.aggregation_strategy}
                       onChange={e => updateDef({ aggregation_strategy: e.target.value })}
                       className="w-full text-sm px-2 py-1.5 rounded border bg-background"
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
                    <label htmlFor="inject-meta" className="text-xs font-medium cursor-pointer">
                        Power Automate로 유입된 입력 메타데이터(파일명/ID 등)를 결과 행(Row)에 컬럼으로 자동 삽입
                    </label>
               </div>
           </div>
       </div>

                    {/* Pivot Tables */}
                    <div>
                        <div className="flex items-center justify-between mb-2">
                            <h4 className="text-xs font-bold flex items-center gap-1.5">
                                <CopyPlus className="w-3.5 h-3.5" /> 세로 행 → 가로 열 피벗 정책 (Pivot Tables)
                            </h4>
                            <Button size="sm" variant="outline" className="h-6 text-[10px] px-2" onClick={() => {
                                updateDef({ pivot_tables: [...(def.pivot_tables || []), { table: '', category_field: '', subcategory_field: '', value_field: '', column_naming: '{charge_code}_{container}' }] })
                                setExpandedPivotIdx(def.pivot_tables ? def.pivot_tables.length : 0)
                            }}>
                                <Plus className="w-3 h-3 mr-1" /> 피벗 추가
                            </Button>
                        </div>
                        
                        <div className="space-y-2">
                            {def.pivot_tables?.map((pivot, idx) => (
                                <div key={idx} className="border rounded-md bg-background">
                                    <div 
                                        className="flex items-center justify-between p-2 cursor-pointer hover:bg-muted/50"
                                        onClick={() => setExpandedPivotIdx(expandedPivotIdx === idx ? null : idx)}
                                    >
                                        <div className="flex items-center gap-2">
                                            {expandedPivotIdx === idx ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                                            <span className="text-xs font-medium text-emerald-800 dark:text-emerald-400">
                                                {pivot.table || `피벗 규칙 ${idx + 1}`}
                                            </span>
                                        </div>
                                        <Button size="sm" variant="ghost" className="h-5 w-5 p-0 text-destructive" onClick={(e) => {
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
                                                <label className="text-[10px] text-muted-foreground block mb-1">대상 테이블</label>
                                                <select
                                                    value={pivot.table}
                                                    onChange={e => {
                                                        const p = [...def.pivot_tables]; p[idx].table = e.target.value; updateDef({ pivot_tables: p })
                                                    }}
                                                    className="w-full text-xs px-2 py-1 rounded border bg-background"
                                                >
                                                    <option value="">선택</option>
                                                    {tableFields.map(f => <option key={f} value={f}>{f}</option>)}
                                                </select>
                                            </div>
                                            <div>
                                                <label className="text-[10px] text-muted-foreground block mb-1">이름 명명 규칙 패턴</label>
                                                <input
                                                    type="text"
                                                    value={pivot.column_naming}
                                                    onChange={e => {
                                                        const p = [...def.pivot_tables]; p[idx].column_naming = e.target.value; updateDef({ pivot_tables: p })
                                                    }}
                                                    className="w-full text-xs px-2 py-1 rounded border bg-background"
                                                    placeholder="{charge_code}_{container}"
                                                />
                                            </div>
                                            <div>
                                                <label className="text-[10px] text-muted-foreground block mb-1">Category 필드 (예: charge_code)</label>
                                                <input
                                                    type="text"
                                                    value={pivot.category_field}
                                                    onChange={e => {
                                                        const p = [...def.pivot_tables]; p[idx].category_field = e.target.value; updateDef({ pivot_tables: p })
                                                    }}
                                                    className="w-full text-xs px-2 py-1 rounded border bg-background"
                                                />
                                            </div>
                                            <div>
                                                <label className="text-[10px] text-muted-foreground block mb-1">Subcategory 필드 (예: container)</label>
                                                <input
                                                    type="text"
                                                    value={pivot.subcategory_field}
                                                    onChange={e => {
                                                        const p = [...def.pivot_tables]; p[idx].subcategory_field = e.target.value; updateDef({ pivot_tables: p })
                                                    }}
                                                    className="w-full text-xs px-2 py-1 rounded border bg-background"
                                                />
                                            </div>
                                            <div className="col-span-2">
                                                <label className="text-[10px] text-muted-foreground block mb-1">Value 추출 필드 (예: amount)</label>
                                                <input
                                                    type="text"
                                                    value={pivot.value_field}
                                                    onChange={e => {
                                                        const p = [...def.pivot_tables]; p[idx].value_field = e.target.value; updateDef({ pivot_tables: p })
                                                    }}
                                                    className="w-full text-xs px-2 py-1 rounded border bg-background"
                                                />
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
                    <div>
                        <div className="flex items-center justify-between mb-2">
                            <h4 className="text-xs font-bold flex items-center gap-1.5">
                                <Key className="w-3.5 h-3.5" /> 최종 결과 스키마 매핑 (Column Mappings)
                            </h4>
                            <Button size="sm" variant="outline" className="h-6 text-[10px] px-2" onClick={() => handleMappingChange('', `Target_Col_${Object.keys(def.final_column_mappings || {}).length + 1}`, 'Source_Col')}>
                                <Plus className="w-3 h-3 mr-1" /> 열 추가
                            </Button>
                        </div>
                        <div className="bg-background rounded-lg border p-2 space-y-2">
                            <div className="grid grid-cols-[1fr_auto_1fr_auto] gap-2 px-1 mb-1">
                                <span className="text-[10px] font-semibold text-muted-foreground text-center">원본 추출 컬럼명 (Source)</span>
                                <span className="w-4"></span>
                                <span className="text-[10px] font-semibold text-muted-foreground text-center">원하는 대상 컬럼명 (Target)</span>
                                <span className="w-6"></span>
                            </div>
                            {Object.entries(def.final_column_mappings || {}).map(([targetCol, sourceCol], idx) => (
                                <div key={idx} className="grid grid-cols-[1fr_auto_1fr_auto] gap-2 items-center">
                                    <input
                                        type="text"
                                        value={sourceCol}
                                        onChange={e => handleMappingChange(targetCol, targetCol, e.target.value)}
                                        className="text-xs px-2 py-1 rounded border w-full bg-muted/20"
                                        placeholder="예: Basic_Rate_List > charge_code"
                                    />
                                    <span className="text-xs text-muted-foreground">→</span>
                                    <input
                                        type="text"
                                        value={targetCol}
                                        onChange={e => handleMappingChange(targetCol, e.target.value, sourceCol)}
                                        className="text-xs px-2 py-1 rounded border w-full font-medium"
                                        placeholder="최종 컬럼명"
                                    />
                                    <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-destructive bg-red-50 hover:bg-red-100" onClick={() => removeMapping(targetCol)}>
                                        <Trash2 className="w-3 h-3" />
                                    </Button>
                                </div>
                            ))}
                            {Object.keys(def.final_column_mappings || {}).length === 0 && (
                                <p className="text-[10px] text-muted-foreground text-center py-4">
                                    매핑이 없습니다. 소스 컬럼을 타겟 이름으로 연결하세요.<br/>
                                    (이곳에 선언된 컬럼만 최종 추출 결과물에 포함됩니다.)
                                </p>
                            )}
                        </div>
                    </div>

                    <div className="pt-2">
                        <label className="text-xs font-medium text-muted-foreground block mb-1">선택: 변환 완료 후 알림 전송 웹훅 (Webhook URL)</label>
                        <input
                            type="text"
                            value={config.webhook_url || ''}
                            onChange={e => updateConfig({ webhook_url: e.target.value })}
                            className="w-full text-sm px-2 py-1.5 rounded border bg-background"
                            placeholder="https://prod-10.koreacentral.logic.azure.com:443/workflows/..."
                        />
                    </div>
                </div>
            )}
        </div>
    )
}
