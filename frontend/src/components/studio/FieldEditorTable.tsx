import { X, GripVertical } from 'lucide-react'
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
    onChange: (fields: Field[]) => void
    disabled?: boolean
}

interface SortableRowProps {
    field: Field
    index: number
    id: string
    updateField: (index: number, key: keyof Field, value: string) => void
    removeField: (index: number) => void
    disabled: boolean
}

function SortableRow({ field, index, id, updateField, removeField, disabled }: SortableRowProps) {
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
                <div className="flex items-center gap-1">
                    <select
                        value={field.type}
                        onChange={(e) => updateField(index, 'type', e.target.value)}
                        disabled={disabled}
                        className="text-xs font-medium text-muted-foreground bg-transparent outline-none cursor-pointer hover:text-primary w-full disabled:cursor-not-allowed disabled:opacity-60"
                    >
                        {FIELD_TYPES.map(type => (
                            <option key={type.value} value={type.value}>
                                {type.label}
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
            <td className="py-1.5 pr-1 text-right">
                {!disabled && (
                    <button
                        onClick={() => removeField(index)}
                        className="p-1 text-muted-foreground/50 hover:text-destructive hover:bg-destructive/10 rounded transition-all"
                    >
                        <X className="w-3 h-3" />
                    </button>
                )}
            </td>
        </tr>
    )
}

export function FieldEditorTable({ fields, onChange, disabled = false }: FieldEditorTableProps) {
    // Keep IDs in sync with fields length
    const ids = fields.map((field, idx) => field.key || `field-${idx}`)

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

    const updateField = (index: number, key: keyof Field, value: string) => {
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
