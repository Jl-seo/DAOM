import { GripVertical, X, Settings2, Network } from 'lucide-react'
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

interface AdvancedSchemaEditorProps {
    fields: Field[]
    modelDictionaries: string[]
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
        zIndex: isDragging ? 50 : 1,
    }

    return (
        <div
            ref={setNodeRef}
            style={style}
            className={clsx(
                "group relative flex items-start gap-4 p-5 mb-4 bg-white dark:bg-card rounded-2xl border border-border/80 transition-all shadow-sm",
                isDragging ? "shadow-2xl ring-2 ring-primary/30 opacity-95" : "hover:border-primary/40 hover:shadow-md"
            )}
        >
            {/* 1. Drag Handle */}
            <div
                {...attributes}
                {...listeners}
                className={clsx(
                    "flex-shrink-0 mt-2 p-1.5 rounded-md text-muted-foreground/30",
                    !disabled && "cursor-grab active:cursor-grabbing hover:bg-accent hover:text-foreground transition-colors"
                )}
            >
                <GripVertical className="w-5 h-5" />
            </div>

            {/* 2. Key & Description Section */}
            <div className="flex-1 flex flex-col gap-3 min-w-[200px]">
                <input
                    type="text"
                    value={field.key}
                    onChange={(e) => updateField(index, 'key', e.target.value)}
                    disabled={disabled}
                    className="font-mono text-base font-bold text-foreground bg-transparent border-b border-transparent hover:border-border focus:border-primary outline-none transition-colors w-full disabled:cursor-not-allowed px-1 py-0.5"
                    placeholder="필드명 (예: invoice_no)"
                />
                <textarea
                    value={field.description || ''}
                    onChange={(e) => {
                        updateField(index, 'description', e.target.value)
                        // Trigger auto-resize (optional implementation, or just fixed min-height)
                        e.target.style.height = 'auto';
                        e.target.style.height = (e.target.scrollHeight) + 'px';
                    }}
                    disabled={disabled}
                    rows={field.description && field.description.length > 50 ? 2 : 1}
                    className="text-[13px] leading-relaxed text-muted-foreground bg-transparent border-b border-transparent hover:border-border focus:border-primary outline-none transition-colors w-full disabled:cursor-not-allowed px-1 py-0.5 resize-none overflow-hidden min-h-[28px]"
                    placeholder="필드 설명 또는 추출 가이드 (선택사항)"
                />
            </div>

            {/* 3. Type & Dictionary Section */}
            <div className="w-[300px] flex flex-col gap-3.5 shrink-0 px-5 border-l border-border/50">
                {/* Data Type */}
                <div className="flex items-center gap-2">
                    <div className="p-1.5 rounded-md bg-secondary text-muted-foreground border border-border/50">
                        <Network className="w-3.5 h-3.5" />
                    </div>
                    <select
                        value={field.type}
                        onChange={(e) => updateField(index, 'type', e.target.value)}
                        disabled={disabled}
                        className="flex-1 text-[13px] font-semibold text-foreground bg-secondary/30 hover:bg-secondary/80 border border-border/80 focus:border-primary rounded-md px-3 py-2 outline-none cursor-pointer disabled:cursor-not-allowed transition-all shadow-sm"
                    >
                        {FIELD_TYPES.map(type => (
                            <option key={type.value} value={type.value}>
                                {type.label}
                            </option>
                        ))}
                    </select>
                </div>

                {/* Sub-fields / Rules Trigger */}
                <div className="flex flex-col gap-2.5">
                    {['list', 'table', 'array'].includes(field.type) ? (
                        <button
                            onClick={(e) => {
                                e.preventDefault()
                                const event = new CustomEvent('open-subfield-modal', { detail: { index, field } })
                                window.dispatchEvent(event)
                            }}
                            disabled={disabled}
                            className={clsx(
                                "flex items-center justify-between px-3 py-2 rounded-md text-[13px] font-bold transition-all border shadow-sm",
                                field.sub_fields && field.sub_fields.length > 0
                                    ? "bg-primary/5 text-primary border-primary/30 hover:bg-primary/10 hover:border-primary/50"
                                    : "bg-white dark:bg-background text-foreground border-border hover:bg-accent hover:text-accent-foreground"
                            )}
                        >
                            <span className="flex items-center gap-2">
                                <Settings2 className="w-4 h-4" />
                                서브 필드 설정
                            </span>
                            {field.sub_fields?.length && (
                                <span className="text-[11px] bg-white dark:bg-background px-2 py-0.5 rounded-full shadow-sm border border-border/50 font-bold">
                                    {field.sub_fields.length}개 컬럼
                                </span>
                            )}
                        </button>
                    ) : (
                        <textarea
                            value={field.rules || ''}
                            onChange={(e) => {
                                updateField(index, 'rules', e.target.value)
                                e.target.style.height = 'auto';
                                e.target.style.height = (e.target.scrollHeight) + 'px';
                            }}
                            disabled={disabled}
                            rows={1}
                            className="w-full text-xs leading-relaxed text-foreground bg-white dark:bg-background border border-border/80 rounded-md px-3 py-2 placeholder:text-muted-foreground/40 focus:border-primary outline-none transition-all disabled:cursor-not-allowed shadow-sm resize-none overflow-hidden min-h-[34px]"
                            placeholder="변환 규칙, 예외 처리 등"
                        />
                    )}

                    <select
                        value={field.dictionary || ''}
                        onChange={(e) => updateField(index, 'dictionary', e.target.value)}
                        disabled={disabled}
                        className="w-full text-[13px] font-semibold text-blue-700 dark:text-blue-300 bg-blue-50/80 dark:bg-blue-900/20 hover:bg-blue-100/80 dark:hover:bg-blue-900/40 border border-blue-200 dark:border-blue-800 rounded-md px-3 py-2 outline-none cursor-pointer transition-all disabled:cursor-not-allowed shadow-sm"
                    >
                        <option value="">📖 딕셔너리 연동 없음</option>
                        {modelDictionaries.map(dict => (
                            <option key={dict} value={dict}>
                                📖 {dict}
                            </option>
                        ))}
                    </select>
                </div>
            </div>

            {/* 4. Validation & Actions */}
            <div className="w-[180px] flex flex-col justify-between shrink-0 pl-5 border-l border-border/50 h-full min-h-[100px]">
                <div className="flex flex-col gap-3">
                    <label className={clsx(
                        "flex items-center gap-2.5 text-[13px] font-bold cursor-pointer transition-colors group/req",
                        disabled ? "opacity-60 cursor-not-allowed" : "hover:text-foreground",
                        field.required ? "text-primary" : "text-muted-foreground"
                    )}>
                        <input
                            type="checkbox"
                            checked={field.required || false}
                            onChange={(e) => updateField(index, 'required', e.target.checked)}
                            disabled={disabled}
                            className="w-4 h-4 rounded border-border text-primary focus:ring-primary focus:ring-offset-background"
                        />
                        필수 수집 (Required)
                    </label>

                    <div className="flex flex-col gap-1.5">
                        <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-widest pl-1">검증 규칙 (Regex)</span>
                        <div className="flex items-center gap-1.5 border border-border/80 rounded-md bg-white dark:bg-background px-2.5 py-1.5 focus-within:border-primary/50 focus-within:ring-1 focus-within:ring-primary/20 transition-all shadow-sm">
                            <span className="text-[11px] text-muted-foreground/50 font-bold tracking-tighter">/^</span>
                            <input
                                type="text"
                                value={field.validation_regex || ''}
                                onChange={(e) => updateField(index, 'validation_regex', e.target.value)}
                                disabled={disabled}
                                className="w-full bg-transparent text-xs font-mono outline-none disabled:cursor-not-allowed text-foreground"
                                placeholder="..."
                            />
                            <span className="text-[11px] text-muted-foreground/50 font-bold tracking-tighter">$/</span>
                        </div>
                    </div>
                </div>

                {!disabled && (
                    <button
                        onClick={() => removeField(index)}
                        className="self-end mt-4 p-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg transition-all"
                        title="필드 삭제"
                    >
                        <X className="w-4 h-4" />
                    </button>
                )}
            </div>
        </div>
    )
}

export function AdvancedSchemaEditor({ fields, modelDictionaries, onChange, disabled = false }: AdvancedSchemaEditorProps) {
    const idCounterRef = useRef(0)
    const stableIdsRef = useRef<string[]>([])

    while (stableIdsRef.current.length < fields.length) {
        stableIdsRef.current.push(`field-adv-${idCounterRef.current++}`)
    }
    if (stableIdsRef.current.length > fields.length) {
        stableIdsRef.current = stableIdsRef.current.slice(0, fields.length)
    }

    const ids = stableIdsRef.current

    const sensors = useSensors(
        useSensor(PointerSensor, {
            activationConstraint: { distance: 8 },
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

            // Move stable IDs
            const newIds = [...stableIdsRef.current]
            const [movedId] = newIds.splice(oldIndex, 1)
            newIds.splice(newIndex, 0, movedId)
            stableIdsRef.current = newIds

            onChange(arrayMove(fields, oldIndex, newIndex))
        }
    }

    // List is empty
    if (fields.length === 0) {
        return (
            <div className="w-full p-8 border-2 border-dashed border-border rounded-xl flex flex-col items-center justify-center text-center bg-card/50">
                <Settings2 className="w-8 h-8 text-muted-foreground/30 mb-3" />
                <p className="text-sm font-medium text-foreground mb-1">정의된 필드가 없습니다.</p>
                <p className="text-xs text-muted-foreground mb-4">하단의 버튼을 눌러 새 필드를 추가하거나 자연어 명령을 통해 필드를 자동 생성하세요.</p>
            </div>
        )
    }

    return (
        <div className="w-full bg-secondary/30 p-5 rounded-2xl border border-border/40 shadow-inner">
            {/* Headers */}
            <div className="flex items-center gap-4 px-4 pb-3 text-[11px] font-bold text-muted-foreground uppercase tracking-widest">
                <div className="w-5 shrink-0"></div>
                <div className="flex-1 min-w-[200px]">필드 및 설명 (추출 가이드)</div>
                <div className="w-[300px] shrink-0 pl-4 border-l border-transparent">타입 및 규칙 (Transformation)</div>
                <div className="w-[180px] shrink-0 pl-4 border-l border-transparent">추가 옵션</div>
            </div>

            <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragEnd={handleDragEnd}
            >
                <SortableContext
                    items={ids}
                    strategy={verticalListSortingStrategy}
                >
                    <div className="flex flex-col gap-1">
                        {fields.map((field, index) => (
                            <SortableRow
                                key={ids[index]}
                                id={ids[index]}
                                field={field}
                                index={index}
                                modelDictionaries={modelDictionaries}
                                updateField={updateField}
                                removeField={removeField}
                                disabled={disabled}
                            />
                        ))}
                    </div>
                </SortableContext>
            </DndContext>
        </div>
    )
}
