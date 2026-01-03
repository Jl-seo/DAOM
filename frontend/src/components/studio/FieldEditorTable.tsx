import { X } from 'lucide-react'
import { FIELD_TYPES } from '../../constants'
import type { Field } from '../../types/model'

interface FieldEditorTableProps {
    fields: Field[]
    onChange: (fields: Field[]) => void
    disabled?: boolean
}

export function FieldEditorTable({ fields, onChange, disabled = false }: FieldEditorTableProps) {
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

    if (fields.length === 0) {
        return (
            <div className="py-4 text-center text-muted-foreground text-[10px] italic">
                필드 없음
            </div>
        )
    }

    return (
        <div className="overflow-x-auto -mx-3 px-3">
            <table className="w-full text-left border-collapse">
                <thead>
                    <tr className="text-[10px] font-bold uppercase text-muted-foreground border-b border-border">
                        <th className="py-1 pl-4 w-[20%]">Key</th>
                        <th className="py-1 pl-2 w-[35%]">Prompt</th>
                        <th className="py-1 pl-2 w-[15%]">Type</th>
                        <th className="py-1 pl-2 w-[25%]">Rules</th>
                        <th className="py-1 pr-1 w-[5%]"></th>
                    </tr>
                </thead>
                <tbody className="text-xs">
                    {fields.map((field, idx) => (
                        <tr key={idx} className="group border-b border-border/30 hover:bg-accent/50">
                            <td className="py-1.5 pl-4">
                                <input
                                    type="text"
                                    value={field.key}
                                    onChange={(e) => updateField(idx, 'key', e.target.value)}
                                    disabled={disabled}
                                    className="w-full bg-transparent font-bold text-sm text-foreground placeholder:text-muted-foreground/50 outline-none focus:text-primary disabled:cursor-not-allowed disabled:opacity-60"
                                    placeholder="key"
                                />
                            </td>
                            <td className="py-2 pl-2 align-top">
                                <textarea
                                    value={field.description || ''}
                                    onChange={(e) => updateField(idx, 'description', e.target.value)}
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
                                        onChange={(e) => updateField(idx, 'type', e.target.value)}
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
                                    onChange={(e) => updateField(idx, 'rules', e.target.value)}
                                    disabled={disabled}
                                    className="w-full bg-transparent text-muted-foreground text-xs font-mono placeholder:text-muted-foreground/30 outline-none disabled:cursor-not-allowed disabled:opacity-60"
                                    placeholder="없음"
                                />
                            </td>
                            <td className="py-1.5 pr-1 text-right">
                                {!disabled && (
                                    <button
                                        onClick={() => removeField(idx)}
                                        className="p-1 text-muted-foreground/50 hover:text-destructive hover:bg-destructive/10 rounded transition-all"
                                    >
                                        <X className="w-3 h-3" />
                                    </button>
                                )}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    )
}
