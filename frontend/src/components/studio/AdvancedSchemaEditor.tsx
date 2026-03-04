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
                "group relative flex items-start gap-4 p-4 mb-2 bg-card rounded-xl border border-border/50 transition-all",
                isDragging ? "shadow-xl ring-2 ring-primary/20 opacity-90" : "hover:border-primary/30 hover:shadow-sm"
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
            <div className="flex-1 flex flex-col gap-2 min-w-[200px]">
                <input
                    type="text"
                    value={field.key}
                    onChange={(e) => updateField(index, 'key', e.target.value)}
                    disabled={disabled}
                    className="font-mono text-sm font-bold bg-transparent border-b border-transparent hover:border-border focus:border-primary outline-none transition-colors w-full disabled:cursor-not-allowed"
                    placeholder="필드명 (예: invoice_no)"
                />
                <input
                    type="text"
                    value={field.description || ''}
                    onChange={(e) => updateField(index, 'description', e.target.value)}
                    disabled={disabled}
                    className="text-xs text-muted-foreground bg-transparent border-b border-transparent hover:border-border focus:border-primary outline-none transition-colors w-full disabled:cursor-not-allowed"
                    placeholder="필드 설명 또는 추출 가이드 (선택사항)"
                />
            </div>

            {/* 3. Type & Dictionary Section */}
            <div className="w-[280px] flex flex-col gap-3 shrink-0 px-4 border-l border-border/50">
                {/* Data Type */}
                <div className="flex items-center gap-2">
                    <Network className="w-4 h-4 text-muted-foreground" />
                    <select
                        value={field.type}
                        onChange={(e) => updateField(index, 'type', e.target.value)}
                        disabled={disabled}
                        className="flex-1 text-sm font-medium bg-secondary/50 hover:bg-secondary border border-transparent hover:border-border rounded-md px-2 py-1.5 outline-none cursor-pointer disabled:cursor-not-allowed transition-all"
                    >
                        {FIELD_TYPES.map(type => (
                            <option key={type.value} value={type.value}>
                                {type.label}
                            </option>
                        ))}
                    </select>
                </div>

                {/* Sub-fields / Rules Trigger */}
                <div className="flex flex-col gap-2">
                    {['list', 'table', 'array'].includes(field.type) ? (
                        <button
                            onClick={(e) => {
                                e.preventDefault()
                                const event = new CustomEvent('open-subfield-modal', { detail: { index, field } })
                                window.dispatchEvent(event)
                            }}
                            disabled={disabled}
                            className={clsx(
                                "flex items-center justify-between px-3 py-1.5 rounded-md text-xs font-medium transition-all border",
                                field.sub_fields && field.sub_fields.length > 0
                                    ? "bg-primary/10 text-primary border-primary/20 hover:bg-primary/20"
                                    : "bg-background text-muted-foreground border-border hover:bg-accent"
                            )}
                        >
                            <span className="flex items-center gap-1.5">
                                <Settings2 className="w-3.5 h-3.5" />
                                서브 필드 설정
                            </span>
                            {field.sub_fields?.length && (
                                <span className="text-[10px] bg-background px-1.5 py-0.5 rounded shadow-sm border border-border/50">
                                    {field.sub_fields.length}개 컬럼
                                </span>
                            )}
                        </button>
                    ) : (
                        <input
                            type="text"
                            value={field.rules || ''}
                            onChange={(e) => updateField(index, 'rules', e.target.value)}
                            disabled={disabled}
                            className="w-full text-xs font-mono bg-background border border-border/50 rounded-md px-3 py-1.5 placeholder:text-muted-foreground/30 focus:border-primary outline-none transition-all disabled:cursor-not-allowed"
                            placeholder="변환 규칙, 예외 처리 등"
                        />
                    )}

                    <select
                        value={field.dictionary || ''}
                        onChange={(e) => updateField(index, 'dictionary', e.target.value)}
                        disabled={disabled}
                        className="w-full text-xs text-blue-600 dark:text-blue-400 bg-blue-50/50 dark:bg-blue-900/10 hover:bg-blue-50 dark:hover:bg-blue-900/20 border border-blue-100 dark:border-blue-800/50 rounded-md px-2 py-1.5 outline-none cursor-pointer transition-all disabled:cursor-not-allowed"
                    >
                        <option value="">📖 딕셔너리 매핑 없음</option>
                        {modelDictionaries.map(dict => (
                            <option key={dict} value={dict}>
                                📖 {dict}
                            </option>
                        ))}
                    </select>
                </div>
            </div>

            {/* 4. Validation & Actions */}
            <div className="w-[160px] flex flex-col justify-between shrink-0 pl-4 border-l border-border/50 h-full min-h-[80px]">
                <div className="flex flex-col gap-2">
                    <label className={clsx(
                        "flex items-center gap-2 text-sm cursor-pointer transition-colors group/req",
                        disabled ? "opacity-60 cursor-not-allowed" : "hover:text-foreground",
                        field.required ? "text-primary font-bold" : "text-muted-foreground"
                    )}>
                        <input
                            type="checkbox"
                            checked={field.required || false}
                            onChange={(e) => updateField(index, 'required', e.target.checked)}
                            disabled={disabled}
                            className="w-4 h-4 rounded border-border text-primary focus:ring-primary focus:ring-offset-background"
                        />
                        필수 값 (Required)
                    </label>

                    <div className="flex items-center gap-1 border border-border/50 rounded bg-background px-2 py-1 focus-within:border-primary/50 transition-colors">
                        <span className="text-[10px] text-muted-foreground/50 tracking-tighter">/^</span>
                        <input
                            type="text"
                            value={field.validation_regex || ''}
                            onChange={(e) => updateField(index, 'validation_regex', e.target.value)}
                            disabled={disabled}
                            className="w-full bg-transparent text-[11px] font-mono outline-none disabled:cursor-not-allowed text-foreground"
                            placeholder="정규식 검증 (Regex)"
                        />
                        <span className="text-[10px] text-muted-foreground/50 tracking-tighter">$/</span>
                    </div>
                </div>

                {!disabled && (
                    <button
                        onClick={() => removeField(index)}
                        className="self-end p-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg transition-all"
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
        <div className="w-full bg-secondary/20 p-4 rounded-xl border border-border/50">
            {/* Headers */}
            <div className="flex items-center gap-4 px-4 pb-2 text-xs font-bold text-muted-foreground uppercase tracking-wider">
                <div className="w-5 shrink-0"></div>
                <div className="flex-1 min-w-[200px]">필드 및 설명 (추출 가이드)</div>
                <div className="w-[280px] shrink-0 pl-4 border-l border-transparent">타입 및 규칙 (Transformation)</div>
                <div className="w-[160px] shrink-0 pl-4 border-l border-transparent">추가 옵션</div>
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
