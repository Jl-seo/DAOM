/* eslint-disable @typescript-eslint/no-explicit-any */
import type { TemplateConfig } from '../../types/template'
import { Card } from '@/components/ui/card'

interface TemplatePreviewProps {
    config: Partial<TemplateConfig>
    sampleData?: Record<string, any>[]
}

export function TemplatePreview({ config, sampleData = [] }: TemplatePreviewProps) {
    const data = sampleData.length > 0 ? sampleData : generateSampleData(config)

    return (
        <Card className="h-full overflow-hidden flex flex-col">
            {/* Preview Header */}
            <div className="px-4 py-2 bg-muted border-b border-border flex items-center justify-between">
                <span className="text-xs font-semibold text-muted-foreground">👁️ 미리보기</span>
                <span className="text-[10px] text-muted-foreground/60">실시간 반영</span>
            </div>

            {/* Preview Content */}
            <div className="flex-1 overflow-auto p-6">
                {/* Header Section */}
                {config.header && (
                    <div
                        className="mb-6 pb-4 border-b-2"
                        style={{ borderColor: config.style?.primaryColor || 'oklch(0.6 0.2 250)' }}
                    >
                        {config.header.logo && (
                            <div className="w-12 h-12 bg-muted rounded-lg mb-2 flex items-center justify-center text-muted-foreground text-xs">
                                로고
                            </div>
                        )}
                        {config.header.title && (
                            <h1
                                className="font-bold text-foreground"
                                style={{ fontSize: (config.style?.fontSize || 14) + 4 }}
                            >
                                {config.header.title}
                            </h1>
                        )}
                        {config.header.subtitle && (
                            <p className="text-muted-foreground text-sm mt-1">{config.header.subtitle}</p>
                        )}
                    </div>
                )}

                {/* Table Layout */}
                {config.layout === 'table' && config.columns && config.columns.length > 0 && (
                    <div className="overflow-x-auto">
                        <table className="w-full border-collapse" style={{ fontSize: config.style?.fontSize || 14 }}>
                            <thead>
                                <tr
                                    className="text-primary-foreground text-left"
                                    style={{ backgroundColor: config.style?.primaryColor || 'oklch(0.6 0.2 250)' }}
                                >
                                    {config.columns.map((col, idx) => (
                                        <th
                                            key={idx}
                                            className="px-4 py-3 font-semibold"
                                            style={{
                                                textAlign: col.align || 'left',
                                                width: col.width
                                            }}
                                        >
                                            {col.label || col.field}
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {data.map((row, rowIdx) => (
                                    <tr key={rowIdx} className="border-b border-border hover:bg-accent">
                                        {config.columns!.map((col, colIdx) => (
                                            <td
                                                key={colIdx}
                                                className="px-4 py-3"
                                                style={{
                                                    textAlign: col.align || 'left',
                                                    color: col.style?.color,
                                                    fontWeight: col.style?.bold ? 'bold' : 'normal'
                                                }}
                                            >
                                                {formatValue(row[col.field], col.format)}
                                            </td>
                                        ))}
                                    </tr>
                                ))}
                            </tbody>
                            {config.aggregation?.showTotal && (
                                <tfoot>
                                    <tr className="bg-muted font-bold">
                                        {config.columns.map((col, idx) => (
                                            <td
                                                key={idx}
                                                className="px-4 py-3"
                                                style={{ textAlign: col.align || 'left' }}
                                            >
                                                {idx === 0 ? '합계' :
                                                    col.format === 'number' || col.format === 'currency'
                                                        ? formatValue(calculateSum(data, col.field), col.format)
                                                        : ''
                                                }
                                            </td>
                                        ))}
                                    </tr>
                                </tfoot>
                            )}
                        </table>
                    </div>
                )}

                {/* Card Layout */}
                {config.layout === 'card' && (
                    <div className="grid grid-cols-2 gap-4">
                        {data.slice(0, 4).map((row, idx) => (
                            <div
                                key={idx}
                                className="p-4 rounded-lg border border-border bg-card shadow-sm"
                            >
                                {config.columns?.map((col, colIdx) => (
                                    <div key={colIdx} className="flex justify-between py-1">
                                        <span className="text-muted-foreground text-sm">{col.label}</span>
                                        <span className="font-medium">{formatValue(row[col.field], col.format)}</span>
                                    </div>
                                ))}
                            </div>
                        ))}
                    </div>
                )}

                {/* Empty State */}
                {(!config.columns || config.columns.length === 0) && (
                    <div className="flex items-center justify-center h-64 text-muted-foreground">
                        <div className="text-center">
                            <div className="text-4xl mb-2">📊</div>
                            <p className="font-medium">템플릿을 디자인해보세요</p>
                            <p className="text-sm">AI에게 "테이블로 만들어줘"라고 말해보세요</p>
                        </div>
                    </div>
                )}

                {/* Footer */}
                {config.footer && (
                    <div className="mt-6 pt-4 border-t border-border text-xs text-muted-foreground flex justify-between">
                        {config.footer.showDate && (
                            <span>생성일: {new Date().toLocaleDateString('ko-KR')}</span>
                        )}
                        {config.footer.customText && (
                            <span>{config.footer.customText}</span>
                        )}
                        {config.footer.pageNumbers && <span>1 / 1</span>}
                    </div>
                )}
            </div>
        </Card>
    )
}

function formatValue(value: any, format?: string): string {
    if (value === undefined || value === null) return '-'

    switch (format) {
        case 'currency':
            return `₩${Number(value).toLocaleString()}`
        case 'number':
            return Number(value).toLocaleString()
        case 'date':
            return new Date(value).toLocaleDateString('ko-KR')
        case 'percent':
            return `${value}%`
        default:
            return String(value)
    }
}

function calculateSum(data: Record<string, any>[], field: string): number {
    return data.reduce((sum, row) => sum + (Number(row[field]) || 0), 0)
}

function generateSampleData(config: Partial<TemplateConfig>): Record<string, any>[] {
    if (!config.columns || config.columns.length === 0) return []

    const sampleRows = 3
    const data: Record<string, any>[] = []

    for (let i = 0; i < sampleRows; i++) {
        const row: Record<string, any> = {}
        config.columns.forEach(col => {
            switch (col.format) {
                case 'number':
                case 'currency':
                    row[col.field] = Math.floor(Math.random() * 10000) + 1000
                    break
                case 'date':
                    row[col.field] = new Date(2024, i, i + 1).toISOString()
                    break
                default:
                    row[col.field] = `샘플 ${i + 1}`
            }
        })
        data.push(row)
    }

    return data
}
