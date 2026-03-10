import { X, GripVertical } from 'lucide-react'
import { useRef } from 'react'
import { FIELD_TYPES } from '../../constants'
import type { Field } from '../../types/model'
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

interface FieldEditorTableProps {
    fields: Field[]
    modelDictionaries: string[]  // <--- NEW: Passed from ModelStudio
    onChange: (fields: Field[]) => void
    disabled?: boolean
}

interface SortableRowProps {
    field: Field
    index: number
    id: string
    modelDictionaries: string[]
    updateField: (index: number, key: keyof Field, value: any) => void
    removeField: (index: number) => void
    disabled: boolean
}

function SortableRow({ field, index, id, modelDictionaries, updateField, removeField, disabled }: SortableRowProps) {
    const {
        attributes,
        listeners,
        setNodeRef,
        transform,
        transition,
        isDragging
    } = useSortable({ id, disabled })

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
                {!disabled && (
                    <button
                        {...attributes}
                        {...listeners}
                        className="p-1 text-muted-foreground/40 hover:text-muted-foreground cursor-grab active:cursor-grabbing rounded transition-colors"
                    >
                        <GripVertical className="w-3.5 h-3.5" />
                    </button>
                )}
            </td>
            <td className="py-1.5 pl-2">
                <input
                    type="text"
                    value={field.key}
                    onChange={(e) => updateField(index, 'key', e.target.value)}
                    disabled={disabled}
                    className="w-full bg-transparent font-bold text-sm text-foreground placeholder:text-muted-foreground/50 outline-none focus:text-primary disabled:cursor-not-allowed disabled:opacity-60"
                    placeholder="key"
                />
            </td>
            <td className="py-2 pl-2 align-top">
                <textarea
                    value={field.description || ''}
                    onChange={(e) => updateField(index, 'description', e.target.value)}
                    disabled={disabled}
                    rows={1}
                    className="w-full bg-transparent text-sm text-muted-foreground placeholder:text-muted-foreground/50 outline-none disabled:cursor-not-allowed disabled:opacity-60 resize-y min-h-[2.5rem] py-1"
                    placeholder="설명"
                    title={field.description || ''}
                />
            </td>
            <td className="py-2 pl-2 align-top">
                <div className="flex flex-col gap-1.5">
                    <select
                        value={field.type}
                        onChange={(e) => updateField(index, 'type', e.target.value)}
                        disabled={disabled}
                        className="text-xs font-medium text-muted-foreground bg-transparent outline-none cursor-pointer hover:text-primary w-full disabled:cursor-not-allowed disabled:opacity-60"
                        title="필드 타입"
                    >
                        {FIELD_TYPES.map(type => (
                            <option key={type.value} value={type.value}>
                                {type.label}
                            </option>
                        ))}
                    </select>

                    <select
                        value={field.dictionary || ''}
                        onChange={(e) => updateField(index, 'dictionary', e.target.value)}
                        disabled={disabled}
                        className="text-[10px] text-blue-600/80 dark:text-blue-400/80 bg-transparent outline-none cursor-pointer hover:text-blue-700 w-full disabled:cursor-not-allowed disabled:opacity-60 border-t border-border/30 pt-1"
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
            </td>
            <td className="py-2 pl-2 align-top">
                <input
                    type="text"
                    value={field.rules || ''}
                    onChange={(e) => updateField(index, 'rules', e.target.value)}
                    disabled={disabled}
                    className="w-full bg-transparent text-muted-foreground text-xs font-mono placeholder:text-muted-foreground/30 outline-none disabled:cursor-not-allowed disabled:opacity-60"
                    placeholder="없음"
                />
            </td>
            <td className="py-2 px-2 align-top text-right min-w-[120px]">
                <div className="flex flex-col items-end gap-1.5 w-full">
                    {/* Required Toggle */}
                    <label className={clsx(
                        "flex items-center gap-1.5 text-[10px] cursor-pointer transition-colors w-full justify-end",
                        disabled ? "opacity-60 cursor-not-allowed" : "hover:text-foreground",
                        field.required ? "text-primary font-bold" : "text-muted-foreground"
                    )}>
                        <input
                            type="checkbox"
                            checked={field.required || false}
                            onChange={(e) => updateField(index, 'required', e.target.checked)}
                            disabled={disabled}
                            className="rounded border-border/50 bg-transparent w-3 h-3"
                        />
                        필수 항목 (Required)
                    </label>

                    {/* PII Toggle */}
                    <label className={clsx(
                        "flex items-center gap-1.5 text-[10px] cursor-pointer transition-colors w-full justify-end",
                        disabled ? "opacity-60 cursor-not-allowed" : "hover:text-foreground",
                        field.is_pii ? "text-red-500 font-bold" : "text-muted-foreground"
                    )}>
                        <input
                            type="checkbox"
                            checked={field.is_pii || false}
                            onChange={(e) => updateField(index, 'is_pii', e.target.checked)}
                            disabled={disabled}
                            className="rounded border-border/50 bg-transparent w-3 h-3 accent-red-500"
                        />
                        개인정보 (PII Masking)
                    </label>

                    {/* Validation Regex */}
                    <div className="flex items-center gap-1 border border-border/50 rounded px-1.5 py-0.5 focus-within:border-primary/50 overflow-hidden w-full max-w-[140px]">
                        <span className="text-[9px] text-muted-foreground/50 tracking-tighter">/^</span>
                        <input
                            type="text"
                            value={field.validation_regex || ''}
                            onChange={(e) => updateField(index, 'validation_regex', e.target.value)}
                            disabled={disabled}
                            className="w-full bg-transparent text-[10px] outline-none font-mono text-muted-foreground placeholder:text-muted-foreground/30"
                            placeholder="Regex"
                            title="Validation Regex Pattern"
                        />
                    </div>

                    {/* Sub-Field Editor Trigger (Only for collection types) */}
                    {['list', 'table', 'array'].includes(field.type) && (
                        <button
                            onClick={(e) => {
                                e.preventDefault();
                                // We dispatch a custom event to ModelStudio to open the modal
                                const event = new CustomEvent('open-subfield-modal', { detail: { index, field } });
                                window.dispatchEvent(event);
                            }}
                            disabled={disabled}
                            className={clsx(
                                "w-full text-[10px] py-1 px-2 rounded font-medium mt-1 leading-tight flex items-center justify-center gap-1 transition-all border",
                                field.sub_fields && field.sub_fields.length > 0
                                    ? "bg-primary/10 text-primary border-primary/20 hover:bg-primary/20"
                                    : "bg-transparent text-muted-foreground border-border/50 hover:bg-accent hover:text-foreground"
                            )}
                        >
                            <span className="text-[12px]">⚙️</span>
                            {field.sub_fields?.length ? `${field.sub_fields.length}개 서브컬럼` : '상세 스키마 설정'}
                        </button>
                    )}
                </div>
            </td>
            <td className="py-1.5 pr-1 text-right">
                {!disabled && (
                    <button
                        onClick={() => removeField(index)}
                        className="p-1 mt-1 text-muted-foreground/50 hover:text-destructive hover:bg-destructive/10 rounded transition-all"
                    >
                        <X className="w-4 h-4" />
                    </button>
                )}
            </td>
        </tr>
    )
}

export function FieldEditorTable({ fields, modelDictionaries, onChange, disabled = false }: FieldEditorTableProps) {
    // STABLE IDs: Use a ref-based counter so IDs never change when field content is edited.
    // This prevents React from unmounting/remounting rows on every keystroke.
    const idCounterRef = useRef(0)
    const stableIdsRef = useRef<string[]>([])

    // Sync stable IDs with fields length (add new IDs for new fields, trim for removed)
    while (stableIdsRef.current.length < fields.length) {
        stableIdsRef.current.push(`field-stable-${idCounterRef.current++}`)
    }
    if (stableIdsRef.current.length > fields.length) {
        stableIdsRef.current = stableIdsRef.current.slice(0, fields.length)
    }

    const ids = stableIdsRef.current

    const sensors = useSensors(
        useSensor(PointerSensor, {
            activationConstraint: {
                distance: 8,
            },
        }),
        useSensor(KeyboardSensor, {
            coordinateGetter: sortableKeyboardCoordinates,
        })
    )

    const updateField = (index: number, key: keyof Field, value: any) => {
        if (disabled) return
        const newFields = [...fields]
        newFields[index] = { ...newFields[index], [key]: value }
        onChange(newFields)
    }

    const removeField = (index: number) => {
        if (disabled) return
        const newFields = [...fields]
        newFields.splice(index, 1)
        onChange(newFields)
    }

    const handleDragEnd = (event: DragEndEvent) => {
        const { active, over } = event

        if (over && active.id !== over.id) {
            const oldIndex = ids.indexOf(active.id as string)
            const newIndex = ids.indexOf(over.id as string)

            if (oldIndex !== -1 && newIndex !== -1) {
                const newFields = arrayMove(fields, oldIndex, newIndex)
                onChange(newFields)
            }
        }
    }

    if (fields.length === 0) {
        return (
            <div className="py-4 text-center text-muted-foreground text-[10px] italic">
                필드 없음
            </div>
        )
    }

    return (
        <div className="overflow-x-auto -mx-3 px-3">
            <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragEnd={handleDragEnd}
            >
                <table className="w-full text-left border-collapse">
                    <thead>
                        <tr className="text-[10px] font-bold uppercase text-muted-foreground border-b border-border">
                            <th className="py-1 pl-2 w-8"></th>
                            <th className="py-1 pl-2 w-[18%]">Key</th>
                            <th className="py-1 pl-2 w-[35%]">Prompt</th>
                            <th className="py-1 pl-2 w-[15%]">Type</th>
                            <th className="py-1 pl-2 w-[25%]">Rules</th>
                            <th className="py-1 pr-1 w-[5%]"></th>
                        </tr>
                    </thead>
                    <SortableContext items={ids} strategy={verticalListSortingStrategy}>
                        <tbody className="text-xs">
                            {fields.map((field, idx) => (
                                <SortableRow
                                    key={ids[idx]}
                                    id={ids[idx]}
                                    field={field}
                                    index={idx}
                                    modelDictionaries={modelDictionaries}
                                    updateField={updateField}
                                    removeField={removeField}
                                    disabled={disabled}
                                />
                            ))}
                        </tbody>
                    </SortableContext>
                </table>
            </DndContext>
            {!disabled && (
                <p className="mt-2 text-[10px] text-muted-foreground">
                    💡 드래그하여 필드 순서를 변경할 수 있습니다
                </p>
            )}
        </div>
    )
}
