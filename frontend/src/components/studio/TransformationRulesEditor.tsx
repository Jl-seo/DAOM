/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Transform Rules Editor — Model Studio sub-component
 * Manage row expansion rules for post-extraction processing.
 */
import { useState, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Plus, Trash2, Edit2, ArrowRightLeft, Sparkles, X, CornerDownRight } from 'lucide-react'
import type { Model, PostProcessRule } from '@/types/model'
import { PostProcessAction } from '@/types/model'
import { clsx } from 'clsx'
import { ExportMappingEditor } from './ExportMappingEditor'

interface TransformRule {
    name: string
    target_field: string
    match_field: string
    match_value: string
    expand_field: string
    expand_values: string[]
    expand_codes?: string[]
    code_field?: string
}

interface TransformationRulesEditorProps {
    model: Model
    onUpdate: (model: Model) => void
}

const EMPTY_RULE: TransformRule = {
    name: '새 분할 규칙',
    target_field: '',
    match_field: '',
    match_value: '',
    expand_field: '',
    expand_values: [],
    expand_codes: [],
    code_field: ''
}

function RuleEditorModal({
    initialRule,
    allFields,
    onSave,
    onCancel
}: {
    initialRule: TransformRule,
    allFields: {key: string, display: string}[],
    onSave: (rule: TransformRule) => void,
    onCancel: () => void
}) {
    const [rule, setRule] = useState<TransformRule>(initialRule)
    const [valuesText, setValuesText] = useState((initialRule.expand_values || []).join('\n'))
    const [codesText, setCodesText] = useState((initialRule.expand_codes || []).join('\n'))

    const values = valuesText.split('\n').map(v => v.trim()).filter(Boolean)
    const codes = codesText.split('\n').map(v => v.trim()).filter(Boolean)

    const previewValues = values.length > 0 ? values.slice(0, 4) : ['(예시 항구 1)', '(예시 항구 2)']

    const handleSave = () => {
        onSave({
            ...rule,
            expand_values: values,
            expand_codes: codes.length > 0 ? codes : undefined
        })
    }

    return (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4 animate-in fade-in" onClick={onCancel}>
            <div className="bg-background w-full max-w-5xl h-[85vh] rounded-xl shadow-2xl flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>
                {/* Header */}
                <div className="px-6 py-4 border-b flex items-center justify-between bg-muted/30">
                    <div>
                        <h2 className="text-lg font-bold text-foreground">그룹 분할(Row Expansion) 마법사</h2>
                        <p className="text-sm text-muted-foreground mt-1">하나의 행(Row)을 여러 개의 새로운 행으로 자동 복사하여 쪼개는 규칙을 만듭니다.</p>
                    </div>
                    <Button variant="ghost" size="icon" onClick={onCancel}>
                        <X className="w-5 h-5" />
                    </Button>
                </div>
                
                {/* Body - Split Pane */}
                <div className="flex-1 flex overflow-hidden">
                    {/* Left: Input Form / Mad Libs */}
                    <div className="flex-1 w-1/2 p-6 overflow-y-auto border-r bg-background">
                        <div className="space-y-6">
                            {/* Rule Name */}
                            <div>
                                <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2 block">규칙 이름</label>
                                <input 
                                    className="w-full border rounded-md px-3 py-2 text-sm bg-background font-medium focus:outline-none focus:ring-2 focus:ring-blue-500"
                                    value={rule.name}
                                    placeholder="예: 아시아 항구 그룹 통합 분리 매크로"
                                    onChange={e => setRule({...rule, name: e.target.value})}
                                />
                            </div>

                            <div className="p-5 bg-blue-50/40 rounded-xl border border-blue-100 space-y-6 text-sm leading-relaxed text-slate-700 dark:bg-blue-950/20 dark:border-blue-900/50 dark:text-slate-300">
                                <div className="flex items-center gap-2">
                                    <span className="font-bold flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300 text-xs shrink-0">1</span>
                                    <span>만약</span>
                                    <select 
                                        className="border-b-2 border-blue-300 bg-transparent px-1 font-semibold text-blue-700 dark:text-blue-300 focus:outline-none focus:border-blue-500 max-w-[200px] truncate"
                                        value={rule.target_field}
                                        onChange={e => setRule({...rule, target_field: e.target.value})}
                                    >
                                        <option value="">[추출 표(배열) 선택]</option>
                                        {allFields.map(f => <option key={f.key} value={f.key}>{f.display}</option>)}
                                    </select>
                                    <span>안에서,</span>
                                </div>

                                <div className="flex items-center gap-2 flex-wrap">
                                    <span className="font-bold flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300 text-xs shrink-0">2</span>
                                    <input 
                                        className="w-28 border-b-2 border-blue-300 bg-transparent px-1 text-center font-semibold text-blue-700 dark:text-blue-300 focus:outline-none focus:border-blue-500 placeholder:text-blue-300"
                                        placeholder="매칭 컬럼 (예: POL)"
                                        value={rule.match_field}
                                        onChange={e => setRule({...rule, match_field: e.target.value})}
                                    />
                                    <span>열의 값이</span>
                                    <input 
                                        className="w-28 border-b-2 border-blue-300 bg-transparent px-1 text-center font-semibold text-blue-700 dark:text-blue-300 focus:outline-none focus:border-blue-500 placeholder:text-blue-300"
                                        placeholder="값 입력 (예: AS1)"
                                        value={rule.match_value}
                                        onChange={e => setRule({...rule, match_value: e.target.value})}
                                    />
                                    <span>과 일치할 때,</span>
                                </div>

                                <div className="flex items-start gap-2 flex-col">
                                    <div className="flex items-center gap-2">
                                        <span className="font-bold flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300 text-xs shrink-0">3</span>
                                        <span>해당 줄을 지우고, 다음 <strong className="text-blue-600 dark:text-blue-400">{values.length || 'N'}</strong>개의 새로운 줄로 뻥튀기하여 생성합니다.</span>
                                    </div>
                                    <div className="ml-8 w-full pr-4 text-xs text-muted-foreground mb-1">
                                        새로 만들어지는 줄들의 
                                        <input 
                                            className="w-28 border-b-2 border-dashed border-slate-400 mx-1 bg-transparent px-1 text-center font-medium text-foreground focus:outline-none focus:border-slate-600"
                                            placeholder="덮어쓸 컬럼 (예: POL)"
                                            value={rule.expand_field}
                                            onChange={e => setRule({...rule, expand_field: e.target.value})}
                                        />
                                        값을 아래 목록대로 각각 덮어씁니다:
                                    </div>
                                    <div className="ml-8 w-full pr-8 grid grid-cols-2 gap-4 mt-2">
                                        <div>
                                            <div className="flex items-center justify-between mb-1">
                                                <label className="text-[10px] font-bold text-slate-500 uppercase block">분할될 값 목록 (엔터로 구분)</label>
                                            </div>
                                            <textarea 
                                                className="w-full h-40 border rounded-lg bg-white dark:bg-slate-900 p-3 text-xs font-mono resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 shadow-sm"
                                                placeholder="Shanghai&#10;Ningbo&#10;Qingdao"
                                                value={valuesText}
                                                onChange={e => setValuesText(e.target.value)}
                                            />
                                        </div>
                                        <div>
                                            <div className="flex items-center justify-between mb-1">
                                                <label className="text-[10px] font-bold text-slate-500 uppercase block">코드 열 매핑 (선택)</label>
                                                <input 
                                                    className="w-16 border-b border-dashed border-slate-400 bg-transparent text-[10px] text-right focus:outline-none font-medium"
                                                    placeholder="코드 컬럼"
                                                    value={rule.code_field || ''}
                                                    onChange={e => setRule({...rule, code_field: e.target.value})}
                                                />
                                            </div>
                                            <textarea 
                                                className="w-full h-40 border rounded-lg bg-white dark:bg-slate-900 p-3 text-xs font-mono resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 shadow-sm"
                                                placeholder="CNSHA&#10;CNNBO&#10;CNTAO"
                                                value={codesText}
                                                onChange={e => setCodesText(e.target.value)}
                                            />
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Right: Visual Preview */}
                    <div className="w-1/2 bg-slate-50 dark:bg-slate-900/40 p-6 flex flex-col relative border-l">
                        <div className="absolute top-5 left-5 flex items-center gap-2">
                            <Sparkles className="w-4 h-4 text-purple-500" />
                            <span className="text-xs font-bold text-slate-500 uppercase tracking-widest">실시간 프리뷰 연결도</span>
                        </div>
                        
                        <div className="flex-1 flex items-center justify-center pt-8">
                            <div className="flex items-center justify-between w-full max-w-md">
                                {/* Before Block */}
                                <div className="w-44 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-md p-4 relative z-10 transition-all">
                                    <div className="text-[10px] font-bold text-slate-400 mb-3 uppercase text-center border-b pb-1.5 flex items-center justify-center gap-1">
                                        원본 행 (1줄)
                                    </div>
                                    <div className="text-xs text-slate-500 mb-2 truncate" title={rule.target_field}>
                                        표: <strong className="text-slate-700 dark:text-slate-300">{rule.target_field || '선택 안됨'}</strong>
                                    </div>
                                    <div className="flex flex-col bg-slate-50 dark:bg-slate-900 rounded p-2 border border-slate-100 dark:border-slate-700 shadow-inner">
                                        <span className="text-[10px] text-slate-400 truncate mb-0.5">{rule.match_field || '(컬럼 지정을 해주세요)'}</span>
                                        <span className="text-sm font-bold text-slate-700 dark:text-slate-200 truncate">{rule.match_value || '(매칭값)'}</span>
                                    </div>
                                </div>
                                
                                {/* Arrows Center */}
                                <div className="flex-1 flex flex-col items-center justify-center min-w-[60px] relative h-full">
                                    <div className="w-full h-0.5 bg-blue-200 dark:bg-blue-800/50 absolute z-0 rounded-full hidden sm:block"></div>
                                    {previewValues.map((_, i) => {
                                        const total = previewValues.length;
                                        const offset = (i - (total - 1) / 2) * 60;
                                        return (
                                            <div key={`arrow-${i}`} className="w-full absolute flex justify-end items-center pointer-events-none" style={{
                                                transform: `translateY(${offset}px)`
                                            }}>
                                                <svg className="w-[120%] h-16 text-blue-400 dark:text-blue-600 drop-shadow-sm -translate-x-[10%]" preserveAspectRatio="none" viewBox="0 0 100 24">
                                                    <path d={`M -5,12 C 40,12 60,${12 + (i - (total-1)/2)*8} 95,${12 + (i - (total-1)/2)*8}`} fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 2" />
                                                    <polygon points={`94,${12 + (i - (total-1)/2)*8 - 3} 101,${12 + (i - (total-1)/2)*8} 94,${12 + (i - (total-1)/2)*8 + 3}`} fill="currentColor"/>
                                                </svg>
                                            </div>
                                        )
                                    })}
                                </div>

                                {/* After Block */}
                                <div className="w-48 flex flex-col gap-3 relative z-10">
                                    {previewValues.map((v, i) => (
                                        <div key={i} className="bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 rounded-xl shadow-md p-3 transition-all hover:-translate-y-0.5 hover:shadow-lg">
                                            <div className="text-[10px] font-bold text-blue-500 mb-1 flex items-center gap-1.5">
                                                <CornerDownRight className="w-3 h-3 text-blue-400" /> 복제된 행 #{i+1}
                                            </div>
                                            <div className="flex flex-col bg-white dark:bg-slate-800 rounded p-1.5 pb-2">
                                                <div className="text-[10px] text-blue-400/80 truncate mb-[1px]">{rule.expand_field || '(선택안됨)'}:</div>
                                                <div className="text-[13px] font-bold text-blue-800 dark:text-blue-300 truncate">{v}</div>
                                            </div>
                                            {rule.code_field && codes[i] && (
                                                <div className="mt-2 pt-1 border-t border-blue-100 dark:border-blue-800/50 flex flex-col px-1">
                                                    <div className="text-[9px] text-blue-500/80 truncate">{rule.code_field}</div>
                                                    <div className="text-[11px] font-semibold text-blue-700 dark:text-blue-400 truncate">{codes[i]}</div>
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                    {values.length > 4 && (
                                        <div className="text-center text-[10px] font-bold text-purple-500 bg-purple-50 dark:bg-purple-900/20 py-1.5 rounded-full border border-purple-100 dark:border-purple-800/50 shadow-sm mt-1 animate-pulse">
                                            + {values.length - 4}개의 시트 추가됨
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Footer */}
                <div className="px-6 py-4 border-t flex justify-end gap-3 bg-muted/10">
                    <Button variant="outline" onClick={onCancel}>나가기</Button>
                    <Button onClick={handleSave} className="bg-blue-600 hover:bg-blue-700 text-white min-w-[140px] shadow-md shadow-blue-500/20">저장 및 메뉴 닫기</Button>
                </div>
            </div>
        </div>
    )
}

export function TransformationRulesEditor({ model, onUpdate }: TransformationRulesEditorProps) {
    const rules: TransformRule[] = (model.transform_rules || []) as TransformRule[]
    // null=closed, 'NEW'=creating, number=editing index
    const [editingIdx, setEditingIdx] = useState<number | 'NEW' | null>(null)

    const allFields = useMemo(() => {
        return model.fields.reduce((acc, f) => {
            acc.push({ key: f.key, display: f.key })
            if (f.sub_fields && Array.isArray(f.sub_fields)) {
                f.sub_fields.forEach((sf: any) => {
                    if (sf.key) {
                        acc.push({ key: sf.key, display: `${f.key} > ${sf.key}` })
                    }
                })
            }
            return acc
        }, [] as { key: string, display: string }[])
    }, [model.fields])

    const postProcessRules: PostProcessRule[] = (model.post_process_rules || [])

    const updateRules = (newRules: TransformRule[]) => {
        onUpdate({
            ...model,
            transform_rules: newRules as any[]
        })
    }

    const updatePostProcessRules = (newRules: PostProcessRule[]) => {
        onUpdate({
            ...model,
            post_process_rules: newRules
        })
    }

    const togglePostProcessRule = (target_field: string, action: PostProcessAction) => {
        if (!target_field) return;
        const isCurrentlyActive = postProcessRules.some(r => r.target_field === target_field && r.action === action)
        if (isCurrentlyActive) {
            updatePostProcessRules(postProcessRules.filter(r => !(r.target_field === target_field && r.action === action)))
        } else {
            updatePostProcessRules([...postProcessRules, { action, target_field }])
        }
    }

    const handleSaveRule = (savedRule: TransformRule) => {
        if (editingIdx === 'NEW') {
            updateRules([...rules, savedRule])
        } else if (typeof editingIdx === 'number') {
            const newRules = [...rules]
            newRules[editingIdx] = savedRule
            updateRules(newRules)
        }
        setEditingIdx(null)
    }

    const removeRule = (idx: number) => {
        updateRules(rules.filter((_, i) => i !== idx))
    }

    return (
        <div className="flex flex-col h-full p-1 space-y-4 overflow-y-auto pr-2">
            {/* Post-Processing Actions Section */}
            <div className="bg-indigo-50/50 p-3 rounded-lg border border-indigo-100 dark:bg-indigo-900/10 dark:border-indigo-800">
                <h3 className="text-sm font-semibold mb-3 text-indigo-800 dark:text-indigo-300 flex items-center gap-2">
                    <Sparkles className="w-4 h-4" />
                    간편 텍스트 정제 규칙 (Actions)
                </h3>
                <div className="space-y-3">
                    {allFields.length === 0 ? (
                        <p className="text-xs text-muted-foreground italic">스키마에 필드가 없습니다.</p>
                    ) : (
                        allFields.map(field => {
                            const fieldKey = field.key
                            const fieldRules = postProcessRules.filter(r => r.target_field === fieldKey)
                            if (!fieldKey) return null;
                            return (
                                <div key={fieldKey} className="flex flex-col sm:flex-row sm:items-center justify-between p-2 rounded bg-background/50 border border-indigo-100/50 dark:border-indigo-800/50">
                                    <span className="text-xs font-bold text-foreground w-1/3 truncate pr-2" title={fieldKey}>
                                        {field.display}
                                    </span>
                                    <div className="flex flex-wrap gap-1.5 flex-1 justify-end">
                                        {[
                                            { action: PostProcessAction.SPLIT_CURRENCY, label: '통화 분리' },
                                            { action: PostProcessAction.EXTRACT_DIGITS, label: '숫자 추출' },
                                            { action: PostProcessAction.UPPERCASE, label: '대문자' },
                                            { action: PostProcessAction.DATE_FORMAT_ISO, label: '날짜 ISO' },
                                            { action: PostProcessAction.SPLIT_DELIMITER, label: '고유행 분리' }
                                        ].map(opt => {
                                            const isActive = fieldRules.some(r => r.action === opt.action)
                                            return (
                                                <button
                                                    key={opt.action}
                                                    type="button"
                                                    onClick={() => togglePostProcessRule(fieldKey, opt.action)}
                                                    className={clsx(
                                                        "px-2 py-1 text-[10px] rounded border transition-colors shadow-sm",
                                                        isActive
                                                            ? "bg-indigo-600 text-white border-indigo-600 font-semibold"
                                                            : "bg-background text-muted-foreground border-border hover:border-indigo-300 hover:text-indigo-700"
                                                    )}
                                                >
                                                    {opt.label}
                                                </button>
                                            )
                                        })}
                                    </div>
                                </div>
                            )
                        })
                    )}
                </div>
            </div>

            {/* Row Expansion Rules Summary Section */}
            <div className="mt-4 pt-4 border-t border-border/60">
               <div className="flex items-center justify-between mb-3 bg-blue-50/50 p-2 px-3 rounded-lg border border-blue-100 dark:bg-blue-950/20 dark:border-blue-900/50">
                   <div>
                       <h3 className="text-sm font-semibold flex items-center gap-2 text-blue-800 dark:text-blue-300">
                           <ArrowRightLeft className="w-4 h-4 text-blue-500" />
                           그룹 분할 규칙 (Row Expansion)
                       </h3>
                       <p className="text-[10px] text-blue-600/70 dark:text-blue-400/60 mt-0.5">1행을 N행으로 복사하여 늘립니다.</p>
                   </div>
                   <Button size="sm" variant="outline" className="h-8 text-xs font-bold text-blue-600 border-blue-200 hover:bg-blue-100 bg-white" onClick={() => setEditingIdx('NEW')}>
                       <Plus className="w-3 h-3 mr-1" /> 위저드 마법사 열기
                   </Button>
               </div>
               
               <div className="space-y-2 px-1">
                   {rules.length === 0 ? (
                       <div className="text-center py-10 text-muted-foreground border rounded-xl bg-slate-50/50 dark:bg-slate-900/10 border-dashed">
                           <ArrowRightLeft className="w-8 h-8 mx-auto mb-3 opacity-20 text-blue-500" />
                           <p className="text-xs font-semibold">설정된 분할 규칙이 없습니다.</p>
                           <p className="text-[10px] mt-1.5 opacity-60">우측 상단의 버튼을 눌러 시각화 마법사를 실행해보세요.</p>
                       </div>
                   ) : (
                       rules.map((rule, idx) => (
                           <div key={idx} className="flex flex-col p-3.5 border rounded-xl bg-white dark:bg-slate-900 shadow-sm transition-all hover:border-blue-300 hover:shadow-md group">
                               <div className="flex items-center justify-between mb-2">
                                   <div className="font-bold text-sm text-slate-800 dark:text-slate-200 flex items-center gap-2">
                                       <span className="w-1.5 h-4 bg-blue-500 rounded-full"></span>
                                       {rule.name || `분할 규칙 #${idx+1}`}
                                       <Badge variant="secondary" className="text-[9px] px-1.5 h-4 w-fit bg-blue-50 text-blue-600 border border-blue-100">{rule.expand_values.length}개로 분할됨</Badge>
                                   </div>
                                    <div className="flex gap-1 opacity-60 group-hover:opacity-100 transition-opacity">
                                        <Button size="icon" variant="ghost" className="h-7 w-7 bg-slate-50 hover:bg-blue-100 hover:text-blue-700 rounded-lg" onClick={() => setEditingIdx(idx)}>
                                            <Edit2 className="w-3.5 h-3.5" />
                                        </Button>
                                        <Button size="icon" variant="ghost" className="h-7 w-7 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg" onClick={() => removeRule(idx)}>
                                            <Trash2 className="w-3.5 h-3.5" />
                                        </Button>
                                    </div>
                               </div>
                               <div className="text-[11px] text-muted-foreground pl-3 border-l-2 border-slate-100 dark:border-slate-800 py-0.5 ml-0.5">
                                   만약 <span className="font-semibold text-slate-600 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 px-1 rounded">{rule.match_field || '?'}</span> 값이 
                                   <span className="font-semibold text-blue-600 bg-blue-50 dark:bg-blue-900/40 px-1 rounded mx-1">'{rule.match_value || '*'}'</span> 일 때 
                                   <ArrowRightLeft className="inline w-3 h-3 mx-1 text-slate-300"/> 
                                   <span className="font-semibold text-slate-600 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 px-1 rounded">{rule.expand_field || '?'}</span> 덮어쓰기
                               </div>
                           </div>
                       ))
                   )}
               </div>
            </div>

            {/* Export Mapping Engine */}
            <div className="mt-4 pt-4 border-t border-border/60">
                <ExportMappingEditor model={model} onUpdate={onUpdate} />
            </div>

            {/* Fullscreen Rules Editor Modal */}
            {editingIdx !== null && (
               <RuleEditorModal 
                  initialRule={editingIdx === 'NEW' ? EMPTY_RULE : rules[editingIdx as number]}
                  allFields={allFields}
                  onSave={handleSaveRule}
                  onCancel={() => setEditingIdx(null)}
               />
            )}
        </div>
    )
}
