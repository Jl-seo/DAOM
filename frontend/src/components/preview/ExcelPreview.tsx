/* eslint-disable @typescript-eslint/no-explicit-any */
import type { Field } from '../../types/model'

interface ExcelPreviewProps {
    data: Record<string, any>[]
    fields: Field[]
}

export function ExcelPreview({ data, fields }: ExcelPreviewProps) {
    if (fields.length === 0) {
        return (
            <div className="text-muted-foreground text-xs text-center py-8">
                필드를 추가하면 미리보기가 표시됩니다
            </div>
        )
    }

    return (
        <div className="overflow-auto max-h-[500px] bg-card rounded-lg shadow-inner border border-border">
            <table className="w-full border-collapse text-xs min-w-max">
                <thead className="sticky top-0 z-10">
                    <tr className="bg-gradient-to-r from-chart-2 to-chart-2/80">
                        <th className="border-r border-chart-2/60 px-1 py-1.5 text-center font-bold text-white text-[10px] w-8">
                            #
                        </th>
                        {fields.map((field, idx) => (
                            <th
                                key={idx}
                                className="border-r border-chart-2/60 last:border-r-0 px-3 py-1.5 text-left font-bold text-white min-w-[100px]"
                            >
                                <div className="truncate">{field.label || field.key}</div>
                                <div className="text-[9px] font-normal text-white/80">
                                    {field.type}
                                </div>
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {data.map((row, rowIdx) => (
                        <tr
                            key={rowIdx}
                            className={rowIdx % 2 === 0 ? "bg-card" : "bg-muted"}
                        >
                            <td className="border border-border px-1 py-1.5 text-center text-muted-foreground font-mono text-[10px] bg-muted">
                                {rowIdx + 1}
                            </td>
                            {fields.map((field, cellIdx) => (
                                <td
                                    key={cellIdx}
                                    className="border border-border px-2 py-1.5 text-foreground"
                                >
                                    <div className="truncate max-w-[150px]" title={String(row[field.key] || '')}>
                                        {Array.isArray(row[field.key])
                                            ? row[field.key].join(', ')
                                            : String(row[field.key] || '-')}
                                    </div>
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>

            {/* Footer */}
            <div className="sticky bottom-0 bg-muted border-t border-border px-3 py-1.5 flex items-center justify-between text-[10px] text-muted-foreground">
                <span>{data.length} rows × {fields.length} columns</span>
                <span className="text-chart-2 font-medium">Excel Preview</span>
            </div>
        </div>
    )
}
