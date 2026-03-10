import { useState, useEffect } from 'react'
import { X, GripVertical, Plus } from 'lucide-react'
import {
    DndContext,
    closestCenter,
    KeyboardSensor,
    PointerSensor,
    useSensor,
    useSensors,
    type DragEndEvent
} from '@dnd-kit/core'
import {
    arrayMove,
    SortableContext,
    sortableKeyboardCoordinates,
    useSortable,
    verticalListSortingStrategy
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { clsx } from 'clsx'
import type { Field } from '../../types/model'
import { FIELD_TYPES } from '../../constants'

interface SubFieldEditorModalProps {
    isOpen: boolean;
    onClose: () => void;
    parentField: Field | null; // The parent array/list field
    modelDictionaries: string[];
    onSave: (subFields: Record<string, any>[]) => void;
}

interface SortableSubRowProps {
    subField: Record<string, any>
    index: number
    id: string
    modelDictionaries: string[]
    updateSubField: (index: number, key: string, value: any) => void
    removeSubField: (index: number) => void
}

function SortableSubRow({ subField, index, id, modelDictionaries, updateSubField, removeSubField }: SortableSubRowProps) {
    const {
        attributes,
        listeners,
        setNodeRef,
        transform,
        transition,
        isDragging
    } = useSortable({ id })

    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
    }

    return (
        <tr
            ref={setNodeRef}
            style={style}
            className={clsx(
                "group border-b border-border/30 hover:bg-accent/50",
                isDragging && "bg-accent/80 shadow-lg z-10"
            )}
        >
            {/* Drag Handle */}
            <td className="py-1.5 pl-2 w-8">
                <button
                    {...attributes}
                    {...listeners}
                    className="p-1 text-muted-foreground/40 hover:text-muted-foreground cursor-grab active:cursor-grabbing rounded transition-colors"
                >
                    <GripVertical className="w-3.5 h-3.5" />
                </button>
            </td>
            {/* Key */}
            <td className="py-1.5 pl-2">
                <input
                    type="text"
                    value={subField.key || ''}
                    onChange={(e) => updateSubField(index, 'key', e.target.value)}
                    className="w-full bg-transparent font-bold text-sm text-foreground placeholder:text-muted-foreground/50 outline-none focus:text-primary"
                    placeholder="e.g. amount"
                />
            </td>
            {/* Description */}
            <td className="py-2 pl-2 align-top">
                <textarea
                    value={subField.description || ''}
                    onChange={(e) => updateSubField(index, 'description', e.target.value)}
                    rows={1}
                    className="w-full bg-transparent text-sm text-muted-foreground placeholder:text-muted-foreground/50 outline-none resize-y min-h-[2.5rem] py-1"
                    placeholder="항목 설명"
                    title={subField.description || ''}
                />
            </td>
            {/* Definition & Properties (Type, Dict, Required, Regex) */}
            <td className="py-2 pl-2 align-top">
                <div className="flex flex-col gap-1.5">
                    <div className="flex gap-2">
                        {/* Type */}
                        <select
                            value={subField.type || 'string'}
                            onChange={(e) => updateSubField(index, 'type', e.target.value)}
                            className="text-xs font-medium text-muted-foreground bg-transparent border border-border/50 rounded outline-none cursor-pointer hover:text-primary w-1/2 p-1"
                            title="데이터 타입"
                        >
                            {FIELD_TYPES.filter(t => !['list', 'table', 'array'].includes(t.value)).map(type => (
                                <option key={type.value} value={type.value}>
                                    {type.label}
                                </option>
                            ))}
                        </select>

                        {/* Dictionary */}
                        <select
                            value={subField.dictionary || ''}
                            onChange={(e) => updateSubField(index, 'dictionary', e.target.value)}
                            className="text-xs text-blue-600/80 dark:text-blue-400/80 bg-transparent border border-border/50 rounded outline-none cursor-pointer hover:text-blue-700 w-1/2 p-1"
                            title="정규화 딕셔너리 연결"
                        >
                            <option value="">딕셔너리 매핑 안함</option>
                            {modelDictionaries.map(dict => (
                                <option key={dict} value={dict}>
                                    📖 {dict}
                                </option>
                            ))}
                        </select>
                    </div>

                    <div className="flex gap-2 items-center mt-1">
                        {/* Required Toggle */}
                        <label className="flex items-center gap-1.5 text-[10px] text-muted-foreground cursor-pointer hover:text-foreground">
                            <input
                                type="checkbox"
                                checked={subField.required || false}
                                onChange={(e) => updateSubField(index, 'required', e.target.checked)}
                                className="rounded border-border/50 bg-transparent"
                            />
                            필수 항목 (Required)
                        </label>

                        {/* PII Toggle */}
                        <label className={clsx(
                            "flex items-center gap-1.5 text-[10px] cursor-pointer hover:text-foreground",
                            subField.is_pii ? "text-red-500 font-bold" : "text-muted-foreground"
                        )}>
                            <input
                                type="checkbox"
                                checked={subField.is_pii || false}
                                onChange={(e) => updateSubField(index, 'is_pii', e.target.checked)}
                                className="rounded border-border/50 bg-transparent accent-red-500"
                            />
                            개인정보
                        </label>

                        {/* Regex Input */}
                        <div className="flex-1 flex items-center border border-border/50 rounded px-1.5 overflow-hidden focus-within:border-primary/50 focus-within:ring-1 focus-within:ring-primary/20 transition-all">
                            <span className="text-[9px] text-muted-foreground/70 font-mono tracking-tighter mr-1 select-none">/^</span>
                            <input
                                type="text"
                                value={subField.validation_regex || ''}
                                onChange={(e) => updateSubField(index, 'validation_regex', e.target.value)}
                                className="w-full bg-transparent text-[10px] py-0.5 outline-none font-mono text-muted-foreground placeholder:text-muted-foreground/30"
                                placeholder="[A-Z]{3} (정규식)"
                                title="Validation Regex Pattern"
                            />
                        </div>
                    </div>
                </div>
            </td>
            {/* Rules */}
            <td className="py-2 pl-2 align-top">
                <input
                    type="text"
                    value={subField.rules || ''}
                    onChange={(e) => updateSubField(index, 'rules', e.target.value)}
                    className="w-full bg-transparent text-muted-foreground text-xs font-mono placeholder:text-muted-foreground/30 outline-none"
                    placeholder="커스텀 추출 룰"
                />
            </td>
            {/* Delete */}
            <td className="py-1.5 pr-1 text-right">
                <button
                    onClick={() => removeSubField(index)}
                    className="p-1 text-muted-foreground/50 hover:text-destructive hover:bg-destructive/10 rounded transition-all"
                >
                    <X className="w-3 h-3" />
                </button>
            </td>
        </tr>
    )
}


export function SubFieldEditorModal({ isOpen, onClose, parentField, modelDictionaries, onSave }: SubFieldEditorModalProps) {
    const [localFields, setLocalFields] = useState<Record<string, any>[]>([])

    // Sync from parent field when modal opens
    useEffect(() => {
        if (isOpen && parentField) {
            const initial = parentField.sub_fields ? [...parentField.sub_fields] : []
            // Attach a stable internal ID to prevent DnD losing focus during edits
            setLocalFields(initial.map(f => ({ ...f, _id: crypto.randomUUID() })))
        }
    }, [isOpen, parentField])

    const sensors = useSensors(
        useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
        useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
    )

    if (!isOpen || !parentField) return null;

    const ids = localFields.map(f => f._id) // Stable robust ID

    const handleAddRow = () => {
        setLocalFields([
            ...localFields,
            { _id: crypto.randomUUID(), key: '', label: '', description: '', type: 'string', required: false }
        ])
    }

    const updateSubField = (index: number, key: string, value: any) => {
        const newFields = [...localFields]
        newFields[index] = { ...newFields[index], [key]: value }
        setLocalFields(newFields)
    }

    const removeSubField = (index: number) => {
        const newFields = [...localFields]
        newFields.splice(index, 1)
        setLocalFields(newFields)
    }

    const handleDragEnd = (event: DragEndEvent) => {
        const { active, over } = event
        if (over && active.id !== over.id) {
            const oldIndex = ids.indexOf(active.id as string)
            const newIndex = ids.indexOf(over.id as string)
            if (oldIndex !== -1 && newIndex !== -1) {
                setLocalFields(arrayMove(localFields, oldIndex, newIndex))
            }
        }
    }

    const handleSave = () => {
        // filter out completely empty rows and strip the internal _id
        const cleaned = localFields
            .filter(f => f.key && f.key.trim() !== '')
            .map(({ _id, ...rest }) => rest)
        onSave(cleaned)
        onClose()
    }

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm animate-in fade-in duration-200">
            <div className="w-full max-w-5xl bg-card border border-border rounded-xl shadow-2xl flex flex-col overflow-hidden max-h-[85vh] animate-in zoom-in-95 duration-200">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-muted/30">
                    <div>
                        <h2 className="text-lg font-bold">서브 필드(열) 스키마 전용 설정</h2>
                        <p className="text-xs text-muted-foreground mt-1">
                            테이블/배열 필드 <strong className="text-primary font-mono bg-primary/10 px-1 rounded">{parentField.key}</strong> 내부에 포함될 구체적인 컬럼(열) 요소들을 정의합니다.
                        </p>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-accent rounded-full text-muted-foreground hover:text-foreground transition-colors">
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {/* Body - Dnd Table */}
                <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
                    {localFields.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-16 text-center text-muted-foreground">
                            <div className="w-12 h-12 rounded-full bg-accent/50 flex items-center justify-center mb-3">
                                <Plus className="w-6 h-6 text-muted-foreground/50" />
                            </div>
                            <p className="text-sm">서브 필드가 아직 정의되지 않았습니다.</p>
                            <p className="text-xs text-muted-foreground/70 mt-1 max-w-sm">이대로 저장할 경우, LLM이 '항목 설명(Description)'에 기재된 내용을 바탕으로 스스로 컬럼 구조를 추론합니다.</p>
                        </div>
                    ) : (
                        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                            <table className="w-full text-left border-collapse">
                                <thead>
                                    <tr className="text-[10px] font-bold uppercase text-muted-foreground border-b border-border pb-2">
                                        <th className="py-2 pl-2 w-8"></th>
                                        <th className="py-2 pl-2 w-[18%]">Key (컬럼명)</th>
                                        <th className="py-2 pl-2 w-[25%]">Description (설명)</th>
                                        <th className="py-2 pl-2 w-[30%]">Properties (유저 타입, 딕셔너리, 필수여부, 정규식)</th>
                                        <th className="py-2 pl-2 w-[20%]">Rules (규칙)</th>
                                        <th className="py-2 pr-1 w-[5%]"></th>
                                    </tr>
                                </thead>
                                <SortableContext items={ids} strategy={verticalListSortingStrategy}>
                                    <tbody className="text-xs border-x border-border/20">
                                        {localFields.map((field, idx) => (
                                            <SortableSubRow
                                                key={field._id}
                                                id={field._id}
                                                subField={field}
                                                index={idx}
                                                modelDictionaries={modelDictionaries}
                                                updateSubField={updateSubField}
                                                removeSubField={removeSubField}
                                            />
                                        ))}
                                    </tbody>
                                </SortableContext>
                            </table>
                        </DndContext>
                    )}

                    <button
                        onClick={handleAddRow}
                        className="w-full mt-4 py-3 border border-dashed border-border text-muted-foreground hover:text-primary hover:border-primary/50 hover:bg-primary/5 rounded-lg flex items-center justify-center gap-2 text-sm transition-all"
                    >
                        <Plus className="w-4 h-4" />
                        컬럼(Column) 추가
                    </button>
                </div>

                {/* Footer */}
                <div className="px-6 py-4 border-t border-border bg-muted/10 flex justify-between items-center">
                    <p className="text-[10px] text-muted-foreground">💡 <strong>Key</strong> 값을 입력하지 않은 빈 로우(Row)는 저장 시 자동으로 삭제됩니다.</p>
                    <div className="flex gap-3">
                        <button onClick={onClose} className="px-4 py-2 text-sm font-medium hover:bg-accent rounded-md transition-colors">
                            취소
                        </button>
                        <button onClick={handleSave} className="px-5 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-md shadow hover:bg-primary/90 transition-colors">
                            저장 및 적용
                        </button>
                    </div>
                </div>
            </div>
        </div>
    )
}
