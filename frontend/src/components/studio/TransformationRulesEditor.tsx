/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Transform Rules Editor — Model Studio sub-component
 * Manage row expansion rules for post-extraction processing.
 * 
 * Rule format (TransformEngine expects):
 * {
 *   name: "AS1 Expansion",
 *   target_field: "shipping_rates_extracted",
 *   match_field: "POL_NAME",
 *   match_value: "AS1",           // or "*" for all rows
 *   expand_field: "POL_NAME",     // field to write expanded values
 *   expand_values: ["Ningbo", "Qingdao", "Shanghai", ...],
 *   expand_codes: ["CNNBO", "CNQND", "CNSHG", ...],  // optional
 *   code_field: "POL_CODE"        // optional
 * }
 */
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Plus, Trash2, ChevronDown, ChevronUp, Copy, ArrowRightLeft } from 'lucide-react'
import type { Model } from '@/types/model'

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
    name: '',
    target_field: '',
    match_field: '',
    match_value: '',
    expand_field: '',
    expand_values: [],
    expand_codes: [],
    code_field: ''
}

export function TransformationRulesEditor({ model, onUpdate }: TransformationRulesEditorProps) {
    const rules: TransformRule[] = (model.transform_rules || []) as TransformRule[]
    const [expandedIdx, setExpandedIdx] = useState<number | null>(null)
    const [editingValuesIdx, setEditingValuesIdx] = useState<number | null>(null)
    const [valuesText, setValuesText] = useState('')
    const [codesText, setCodesText] = useState('')

    // Get table fields from model
    const tableFields = model.fields
        .filter(f => f.type === 'table')
        .map(f => f.key)
    const allFieldKeys = model.fields.map(f => f.key)

    const updateRules = (newRules: TransformRule[]) => {
        onUpdate({
            ...model,
            transform_rules: newRules as any[]
        })
    }

    const addRule = () => {
        const newRule: TransformRule = {
            ...EMPTY_RULE,
            name: `규칙 ${rules.length + 1}`,
            target_field: tableFields[0] || ''
        }
        updateRules([...rules, newRule])
        setExpandedIdx(rules.length)
    }

    const removeRule = (idx: number) => {
        updateRules(rules.filter((_, i) => i !== idx))
        setExpandedIdx(null)
    }

    const duplicateRule = (idx: number) => {
        const copy = { ...rules[idx], name: `${rules[idx].name} (복사)` }
        const newRules = [...rules]
        newRules.splice(idx + 1, 0, copy)
        updateRules(newRules)
        setExpandedIdx(idx + 1)
    }

    const updateRule = (idx: number, updates: Partial<TransformRule>) => {
        const newRules = [...rules]
        newRules[idx] = { ...newRules[idx], ...updates }
        updateRules(newRules)
    }

    const openValuesEditor = (idx: number) => {
        const rule = rules[idx]
        setValuesText(rule.expand_values.join('\n'))
        setCodesText((rule.expand_codes || []).join('\n'))
        setEditingValuesIdx(idx)
    }

    const saveValues = () => {
        if (editingValuesIdx === null) return
        const values = valuesText.split('\n').map(v => v.trim()).filter(Boolean)
        const codes = codesText.split('\n').map(c => c.trim()).filter(Boolean)
        updateRule(editingValuesIdx, {
            expand_values: values,
            expand_codes: codes.length > 0 ? codes : undefined
        })
        setEditingValuesIdx(null)
    }

    return (
        <div className="flex flex-col h-full p-1 space-y-4">
            {/* Header */}
            <div className="bg-amber-50/50 p-3 rounded-lg border border-amber-100 dark:bg-amber-900/10 dark:border-amber-800">
                <h3 className="text-sm font-semibold mb-1 text-amber-800 dark:text-amber-300 flex items-center gap-2">
                    <ArrowRightLeft className="w-4 h-4" />
                    변환 규칙 (Row Expansion)
                </h3>
                <p className="text-xs text-amber-700/80 dark:text-amber-400/70">
                    그룹 코드 → 개별 값으로 행을 확장합니다. 예: AS1 → Ningbo, Qingdao, Shanghai, ...
                </p>
            </div>

            {/* Rules List */}
            <div className="flex-1 overflow-auto space-y-2">
                {rules.length === 0 ? (
                    <div className="text-center py-12 text-muted-foreground">
                        <ArrowRightLeft className="w-8 h-8 mx-auto mb-3 opacity-30" />
                        <p className="text-sm">변환 규칙이 없습니다</p>
                        <p className="text-xs mt-1">규칙을 추가하여 추출 결과의 행을 확장하세요</p>
                    </div>
                ) : (
                    rules.map((rule, idx) => (
                        <div key={idx} className="border rounded-lg bg-background">
                            {/* Rule Header */}
                            <div
                                className="flex items-center justify-between p-3 cursor-pointer hover:bg-muted/30"
                                onClick={() => setExpandedIdx(expandedIdx === idx ? null : idx)}
                            >
                                <div className="flex items-center gap-2">
                                    {expandedIdx === idx ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                                    <span className="font-medium text-sm">{rule.name || `규칙 ${idx + 1}`}</span>
                                    <Badge variant="secondary" className="text-[10px]">
                                        {rule.target_field || '미설정'}
                                    </Badge>
                                    <Badge variant="outline" className="text-[10px]">
                                        {rule.match_value || '*'} → {rule.expand_values.length}개 확장
                                    </Badge>
                                </div>
                                <div className="flex gap-1" onClick={e => e.stopPropagation()}>
                                    <Button size="sm" variant="ghost" onClick={() => duplicateRule(idx)} className="h-6 px-1">
                                        <Copy className="w-3 h-3" />
                                    </Button>
                                    <Button size="sm" variant="ghost" onClick={() => removeRule(idx)} className="h-6 px-1 text-destructive hover:text-destructive">
                                        <Trash2 className="w-3 h-3" />
                                    </Button>
                                </div>
                            </div>

                            {/* Rule Detail */}
                            {expandedIdx === idx && (
                                <div className="p-3 pt-0 space-y-3 border-t">
                                    {/* Name */}
                                    <div>
                                        <label htmlFor={`rule-name-${idx}`} className="text-xs font-medium text-muted-foreground">규칙 이름</label>
                                        <input
                                            id={`rule-name-${idx}`}
                                            name={`rule-name-${idx}`}
                                            type="text"
                                            value={rule.name}
                                            onChange={e => updateRule(idx, { name: e.target.value })}
                                            className="w-full mt-1 text-sm px-2 py-1.5 rounded border bg-background"
                                            placeholder="예: AS1 Port Group Expansion"
                                        />
                                    </div>

                                    <div className="grid grid-cols-2 gap-3">
                                        {/* Target Table */}
                                        <div>
                                            <label htmlFor={`rule-target-${idx}`} className="text-xs font-medium text-muted-foreground">대상 테이블 필드</label>
                                            <select
                                                id={`rule-target-${idx}`}
                                                name={`rule-target-${idx}`}
                                                value={rule.target_field}
                                                onChange={e => updateRule(idx, { target_field: e.target.value })}
                                                className="w-full mt-1 text-sm px-2 py-1.5 rounded border bg-background"
                                            >
                                                <option value="">선택</option>
                                                {allFieldKeys.map(k => (
                                                    <option key={k} value={k}>{k}</option>
                                                ))}
                                            </select>
                                        </div>

                                        {/* Match Field */}
                                        <div>
                                            <label htmlFor={`rule-match-field-${idx}`} className="text-xs font-medium text-muted-foreground">매칭 컬럼</label>
                                            <input
                                                id={`rule-match-field-${idx}`}
                                                name={`rule-match-field-${idx}`}
                                                type="text"
                                                value={rule.match_field}
                                                onChange={e => updateRule(idx, { match_field: e.target.value })}
                                                className="w-full mt-1 text-sm px-2 py-1.5 rounded border bg-background"
                                                placeholder="예: POL_NAME"
                                            />
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-2 gap-3">
                                        {/* Match Value */}
                                        <div>
                                            <label htmlFor={`rule-match-val-${idx}`} className="text-xs font-medium text-muted-foreground">매칭 값 (* = 전체)</label>
                                            <input
                                                id={`rule-match-val-${idx}`}
                                                name={`rule-match-val-${idx}`}
                                                type="text"
                                                value={rule.match_value}
                                                onChange={e => updateRule(idx, { match_value: e.target.value })}
                                                className="w-full mt-1 text-sm px-2 py-1.5 rounded border bg-background"
                                                placeholder="예: AS1"
                                            />
                                        </div>

                                        {/* Expand Field */}
                                        <div>
                                            <label htmlFor={`rule-expand-field-${idx}`} className="text-xs font-medium text-muted-foreground">확장할 컬럼</label>
                                            <input
                                                id={`rule-expand-field-${idx}`}
                                                name={`rule-expand-field-${idx}`}
                                                type="text"
                                                value={rule.expand_field}
                                                onChange={e => updateRule(idx, { expand_field: e.target.value })}
                                                className="w-full mt-1 text-sm px-2 py-1.5 rounded border bg-background"
                                                placeholder="예: POL_NAME"
                                            />
                                        </div>
                                    </div>

                                    {/* Code Field (optional) */}
                                    <div>
                                        <label htmlFor={`rule-code-field-${idx}`} className="text-xs font-medium text-muted-foreground">코드 컬럼 (선택)</label>
                                        <input
                                            id={`rule-code-field-${idx}`}
                                            name={`rule-code-field-${idx}`}
                                            type="text"
                                            value={rule.code_field || ''}
                                            onChange={e => updateRule(idx, { code_field: e.target.value || undefined })}
                                            className="w-full mt-1 text-sm px-2 py-1.5 rounded border bg-background"
                                            placeholder="예: POL_CODE (확장값에 대응하는 코드를 쓸 컬럼)"
                                        />
                                    </div>

                                    {/* Expand Values */}
                                    <div>
                                        <div className="flex items-center justify-between mb-1">
                                            <label className="text-xs font-medium text-muted-foreground">
                                                확장 값 ({rule.expand_values.length}개)
                                            </label>
                                            <Button size="sm" variant="outline" onClick={() => openValuesEditor(idx)} className="h-5 text-[10px] px-2">
                                                편집
                                            </Button>
                                        </div>
                                        <div className="flex flex-wrap gap-1">
                                            {rule.expand_values.slice(0, 10).map((v, vi) => (
                                                <Badge key={vi} variant="secondary" className="text-[10px]">
                                                    {v}
                                                    {rule.expand_codes?.[vi] && (
                                                        <span className="ml-1 text-muted-foreground">({rule.expand_codes[vi]})</span>
                                                    )}
                                                </Badge>
                                            ))}
                                            {rule.expand_values.length > 10 && (
                                                <Badge variant="outline" className="text-[10px]">+{rule.expand_values.length - 10}개 더</Badge>
                                            )}
                                            {rule.expand_values.length === 0 && (
                                                <span className="text-xs text-muted-foreground italic">편집 버튼을 눌러 값을 입력하세요 (줄바꿈으로 구분)</span>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    ))
                )}
            </div>

            {/* Values Editor Modal */}
            {editingValuesIdx !== null && (
                <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center" onClick={() => setEditingValuesIdx(null)}>
                    <div className="bg-background rounded-xl p-5 w-[600px] max-h-[80vh] overflow-auto shadow-2xl" onClick={e => e.stopPropagation()}>
                        <h3 className="font-semibold mb-3">확장 값 편집 — {rules[editingValuesIdx]?.name}</h3>
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label htmlFor="expand-values-editor" className="text-xs font-medium text-muted-foreground mb-1 block">
                                    값 (줄바꿈 구분)
                                </label>
                                <textarea
                                    id="expand-values-editor"
                                    name="expand-values-editor"
                                    value={valuesText}
                                    onChange={e => setValuesText(e.target.value)}
                                    className="w-full h-64 text-sm font-mono px-3 py-2 rounded border bg-background resize-none"
                                    placeholder={"Ningbo\nQingdao\nShanghai\nYantian\nHong Kong\nPusan\nKaohsiung"}
                                />
                                <p className="text-[10px] text-muted-foreground mt-1">{valuesText.split('\n').filter(Boolean).length}개 값</p>
                            </div>
                            <div>
                                <label htmlFor="expand-codes-editor" className="text-xs font-medium text-muted-foreground mb-1 block">
                                    코드 (선택, 같은 순서)
                                </label>
                                <textarea
                                    id="expand-codes-editor"
                                    name="expand-codes-editor"
                                    value={codesText}
                                    onChange={e => setCodesText(e.target.value)}
                                    className="w-full h-64 text-sm font-mono px-3 py-2 rounded border bg-background resize-none"
                                    placeholder={"CNNBO\nCNQND\nCNSHG\nCNYYT\nHKHKG\nKRPUS\nTWKSG"}
                                />
                                <p className="text-[10px] text-muted-foreground mt-1">{codesText.split('\n').filter(Boolean).length}개 코드</p>
                            </div>
                        </div>
                        <div className="flex justify-end gap-2 mt-4">
                            <Button variant="ghost" onClick={() => setEditingValuesIdx(null)}>취소</Button>
                            <Button onClick={saveValues}>저장</Button>
                        </div>
                    </div>
                </div>
            )}

            {/* Add Rule Button */}
            <Button variant="outline" onClick={addRule} className="w-full">
                <Plus className="w-4 h-4 mr-2" /> 변환 규칙 추가
            </Button>
        </div>
    )
}
