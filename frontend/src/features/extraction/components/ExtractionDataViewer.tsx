/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from 'react'
import { ChevronDown, ChevronUp, Sparkles } from 'lucide-react'
import { Card } from '@/components/ui/card'

interface ExtractionDataViewerProps {
    data: Record<string, any>
    title?: string
}

// Nested table component for array values (readonly)
function NestedArrayTable({ data }: { data: any[] }) {
    if (!Array.isArray(data) || data.length === 0) {
        return <span className="text-muted-foreground italic text-xs">빈 배열</span>
    }

    // Get all unique keys from array items
    const allKeys = Array.from(new Set(data.flatMap(item =>
        typeof item === 'object' && item !== null ? Object.keys(item) : []
    )))

    if (allKeys.length === 0) {
        // Simple array of primitives
        return (
            <div className="space-y-1">
                {data.map((item, idx) => (
                    <div key={idx} className="px-2 py-1 bg-muted rounded text-xs">
                        {typeof item === 'object' ? JSON.stringify(item) : String(item)}
                    </div>
                ))}
            </div>
        )
    }

    // Array of objects - render as table
    return (
        <div className="border border-border rounded-lg overflow-hidden mt-1">
            <table className="w-full text-xs">
                <thead>
                    <tr className="bg-muted">
                        {allKeys.map(key => (
                            <th key={key} className="px-2 py-1.5 text-left font-medium text-muted-foreground border-b border-border">
                                {key}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody className="divide-y divide-border">
                    {data.map((row, rowIdx) => (
                        <tr key={rowIdx} className="hover:bg-accent">
                            {allKeys.map(key => (
                                <td key={key} className="px-2 py-1.5 text-muted-foreground">
                                    {typeof row?.[key] === 'object'
                                        ? JSON.stringify(row[key])
                                        : String(row?.[key] ?? '')}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    )
}

// Render value with proper handling for different types
function ValueDisplay({ value }: { value: any }) {
    if (value === null || value === undefined || value === '') {
        return <span className="text-muted-foreground italic text-xs">없음</span>
    }

    // Handle extraction field format: { value, confidence, bbox }
    if (typeof value === 'object' && !Array.isArray(value) && 'value' in value) {
        const extractedValue = value.value
        const confidence = value.confidence

        return (
            <div className="flex items-center gap-2">
                <span className="text-foreground">
                    {extractedValue === null || extractedValue === undefined || extractedValue === ''
                        ? <span className="text-muted-foreground italic text-xs">없음</span>
                        : String(extractedValue)}
                </span>
                {confidence !== null && confidence !== undefined && (
                    <span
                        className={`px-2 py-0.5 text-xs rounded-full ${confidence >= 0.8
                                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                                : 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400'
                            }`}
                    >
                        {(confidence * 100).toFixed(0)}%
                    </span>
                )}
            </div>
        )
    }

    if (Array.isArray(value)) {
        return <NestedArrayTable data={value} />
    }

    if (typeof value === 'object') {
        return (
            <pre className="text-xs bg-muted p-2 rounded overflow-auto max-h-32 text-muted-foreground">
                {JSON.stringify(value, null, 2)}
            </pre>
        )
    }

    return <span className="text-foreground">{String(value)}</span>
}

export function ExtractionDataViewer({ data, title = "추출 데이터" }: ExtractionDataViewerProps) {
    const [showAllData, setShowAllData] = useState(true)

    if (!data || Object.keys(data).length === 0) {
        return (
            <div className="text-center py-8 text-muted-foreground">
                데이터가 없습니다
            </div>
        )
    }

    const entries = Object.entries(data)

    return (
        <Card className="overflow-hidden">
            {/* Header */}
            <button
                onClick={() => setShowAllData(!showAllData)}
                className="w-full px-4 py-3 bg-gradient-to-r from-primary/10 to-chart-5/10 flex items-center justify-between border-b border-border"
            >
                <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-primary" />
                    <span className="text-sm font-bold text-foreground">{title}</span>
                    <span className="px-2 py-0.5 bg-primary/10 text-primary text-xs rounded-full">
                        {entries.length}개 필드
                    </span>
                </div>
                {showAllData ? (
                    <ChevronUp className="w-4 h-4 text-muted-foreground" />
                ) : (
                    <ChevronDown className="w-4 h-4 text-muted-foreground" />
                )}
            </button>

            {/* Content */}
            {showAllData && (
                <table className="w-full text-sm">
                    <thead>
                        <tr className="bg-muted text-xs uppercase text-muted-foreground">
                            <th className="px-4 py-2 text-left font-semibold w-1/3">필드명</th>
                            <th className="px-4 py-2 text-left font-semibold">값</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                        {entries.map(([key, value]) => (
                            <tr key={key} className="hover:bg-accent">
                                <td className="px-4 py-2.5 align-top">
                                    <div className="font-medium text-foreground">{key}</div>
                                </td>
                                <td className="px-4 py-2.5">
                                    <ValueDisplay value={value} />
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </Card>
    )
}
