import { useState, useRef, useEffect, useMemo } from 'react'
import { ChevronDown, ChevronRight, Edit2 } from 'lucide-react'
import { clsx } from 'clsx'
import { deepFlattenData, getAllKeys, extractValue } from '@/lib/deep-pivot'

export interface DeepTableProps {
    data: any[]
    onUpdate?: (newData: any[]) => void
    isExpanded?: boolean
    onToggleExpand?: () => void
    className?: string
}

export function ConfidenceBadge({ confidence }: { confidence: number | null }) {
    if (confidence === null) return null

    const percentage = Math.round(confidence * 100)
    const colorClass =
        confidence >= 0.9 ? 'bg-chart-2/10 text-chart-2' :
            confidence >= 0.7 ? 'bg-chart-4/10 text-chart-4' :
                'bg-destructive/10 text-destructive font-semibold'

    return (
        <span className={clsx('ml-2 px-1.5 py-0.5 rounded text-xs', colorClass)}>
            {percentage}%
        </span>
    )
}

function renderValue(value: any): string {
    if (value === null || value === undefined) return ''
    const unwrapped = extractValue(value)
    if (typeof unwrapped === 'object') return JSON.stringify(unwrapped, null, 2)
    return String(unwrapped)
}

/**
 * Enhanced Nested Table with Column Resizing, Path Tracking & Deep Flattening
 */
export function DeepTable({
    data,
    onUpdate,
    isExpanded = true,
    onToggleExpand,
    className
}: DeepTableProps) {
    const [columnWidths, setColumnWidths] = useState<Record<string, number>>({})
    const [resizingColumn, setResizingColumn] = useState<string | null>(null)
    const [isEditMode, setIsEditMode] = useState(true)
    const tableRef = useRef<HTMLDivElement>(null)

    if (!Array.isArray(data) || data.length === 0) {
        return <span className="text-muted-foreground italic text-xs">빈 배열</span>
    }

    // Deep Flattening applied with Path Tracking
    const { normalizedData: flattenedData, paths: pathMap } = useMemo(() => deepFlattenData(data), [data])

    // 원본 데이터를 보여줄지, 플래트닝된 데이터를 보여줄지 (Edit Mode에서는 Pivot된 데이터를 보여줌)
    const displayData = isEditMode ? flattenedData : data

    // Helper to update original data using path
    const handleCellUpdate = (rowIndex: number, columnKey: string, newValue: any) => {
        if (!onUpdate) return
        if (!isEditMode) return // Should not happen

        // 1. Clone original data DEEPLY to avoid mutations
        const newData = JSON.parse(JSON.stringify(data))

        // 2. Find path
        const rowPaths = pathMap.get(rowIndex)
        const path = rowPaths?.[columnKey]

        if (path && path.length > 0) {
            // 3. Traverse and update
            let current = newData

            // Traverse path
            for (let i = 0; i < path.length - 1; i++) {
                const key = path[i]
                if (current[key] === undefined) {
                    const nextKey = path[i + 1]
                    current[key] = typeof nextKey === 'number' ? [] : {}
                }
                current = current[key]
            }

            const lastKey = path[path.length - 1]

            // Handle Value Metadata
            if (current[lastKey] && typeof current[lastKey] === 'object' && 'value' in current[lastKey]) {
                current[lastKey].value = newValue
            } else {
                current[lastKey] = newValue
            }

            onUpdate(newData)
        } else {
            console.warn('Could not find path for update', rowIndex, columnKey)
        }
    }

    // 키 컬럼을 맨 앞에 배치하기 위해 컬럼 순서 조정
    const allKeysRaw = getAllKeys(displayData)

    // bbox, confidence, page_number 제외 및 키 컬럼 맨 앞에 배치
    const hiddenColumns = ['bbox', 'confidence', 'page_number', 'row_id']
    const allKeys = allKeysRaw
        .filter(k => !hiddenColumns.includes(k))
        .sort()

    // Initialize column widths
    useEffect(() => {
        if (allKeys.length > 0 && Object.keys(columnWidths).length === 0) {
            const initialWidths: Record<string, number> = {}
            const defaultWidth = Math.max(100, Math.floor(800 / allKeys.length))
            allKeys.forEach(key => {
                initialWidths[key] = defaultWidth
            })
            setColumnWidths(initialWidths)
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [data.length, columnWidths])

    // Handle column resize
    const handleResizeStart = (e: React.MouseEvent, columnKey: string) => {
        e.preventDefault()
        e.stopPropagation()
        setResizingColumn(columnKey)

        const startX = e.clientX
        const startWidth = columnWidths[columnKey] || 100

        const handleMouseMove = (moveEvent: MouseEvent) => {
            const diff = moveEvent.clientX - startX
            const newWidth = Math.max(60, startWidth + diff)
            setColumnWidths(prev => ({ ...prev, [columnKey]: newWidth }))
        }

        const handleMouseUp = () => {
            setResizingColumn(null)
            document.removeEventListener('mousemove', handleMouseMove)
            document.removeEventListener('mouseup', handleMouseUp)
            document.body.style.cursor = ''
            document.body.style.userSelect = ''
        }

        document.addEventListener('mousemove', handleMouseMove)
        document.addEventListener('mouseup', handleMouseUp)
        document.body.style.cursor = 'col-resize'
        document.body.style.userSelect = 'none'
    }

    if (allKeys.length === 0) {
        return (
            <div className="space-y-1">
                {data.map((item, idx) => (
                    <div key={idx} className="px-2 py-1 bg-muted rounded text-xs">
                        {renderValue(item)}
                    </div>
                ))}
            </div>
        )
    }

    if (!isExpanded) {
        return (
            <button
                onClick={onToggleExpand}
                className={clsx(
                    "flex items-center gap-2 px-3 py-2 bg-muted/50 hover:bg-muted rounded-lg text-sm text-muted-foreground hover:text-foreground transition-colors w-full text-left",
                    className
                )}
            >
                <ChevronRight className="w-4 h-4" />
                <span className="font-medium">테이블 ({displayData.length}행 × {allKeys.length}열)</span>
                <span className="text-xs">클릭하여 펼치기</span>
            </button>
        )
    }

    return (
        <div ref={tableRef} className={clsx("border border-border rounded-lg overflow-hidden", className)}>
            <div className="flex items-center justify-between px-3 py-1.5 bg-muted/50 border-b border-border">
                <div className="flex items-center gap-2">
                    {onToggleExpand && (
                        <button
                            onClick={onToggleExpand}
                            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                        >
                            <ChevronDown className="w-3 h-3" />
                            <span>테이블 접기 ({displayData.length}행)</span>
                        </button>
                    )}
                </div>
                {onUpdate && (
                    <button
                        onClick={() => setIsEditMode(!isEditMode)}
                        className={clsx(
                            "flex items-center gap-1 px-2 py-1 text-xs rounded transition-colors",
                            isEditMode
                                ? "bg-primary text-primary-foreground"
                                : "bg-muted hover:bg-accent text-muted-foreground hover:text-foreground"
                        )}
                    >
                        <Edit2 className="w-3 h-3" />
                        <span>{isEditMode ? '보기 모드' : '편집 모드'}</span>
                    </button>
                )}
            </div>

            <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
                <table className="text-sm" style={{ minWidth: '100%' }}>
                    <thead className="sticky top-0 z-10">
                        <tr className="bg-muted">
                            {allKeys.map((key, idx) => (
                                <th
                                    key={key}
                                    className="text-left font-medium text-muted-foreground border-b border-border relative group"
                                    style={{
                                        width: columnWidths[key] || 100,
                                        minWidth: 60,
                                        maxWidth: columnWidths[key] || 100
                                    }}
                                >
                                    <div className="px-3 py-2 truncate">
                                        {key === '_container_type' ? '컨테이너' : key}
                                    </div>
                                    {idx < allKeys.length - 1 && (
                                        <div
                                            onMouseDown={(e) => handleResizeStart(e, key)}
                                            className={clsx(
                                                "absolute right-0 top-0 h-full w-1 cursor-col-resize",
                                                "hover:bg-primary/50 transition-colors",
                                                resizingColumn === key && "bg-primary"
                                            )}
                                        />
                                    )}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                        {displayData.map((row, rowIdx) => (
                            <tr key={rowIdx} className="hover:bg-accent/50">
                                {allKeys.map(key => (
                                    <td
                                        key={key}
                                        className="text-muted-foreground"
                                        style={{
                                            width: columnWidths[key] || 100,
                                            minWidth: 60,
                                            maxWidth: columnWidths[key] || 100
                                        }}
                                    >
                                        {isEditMode && onUpdate ? (
                                            <input
                                                type="text"
                                                className="w-full bg-transparent border-b border-transparent hover:border-border focus:border-primary outline-none px-3 py-2"
                                                value={renderValue(row?.[key] ?? '')}
                                                onChange={(e) => {
                                                    if (isEditMode) {
                                                        handleCellUpdate(rowIdx, key, e.target.value)
                                                    } else {
                                                        const newData = [...data]
                                                        if (typeof newData[rowIdx] === 'object') {
                                                            newData[rowIdx] = { ...newData[rowIdx], [key]: e.target.value }
                                                        }
                                                        onUpdate(newData)
                                                    }
                                                }}
                                            />
                                        ) : (
                                            <div className="px-3 py-2 truncate">
                                                {renderValue(row?.[key])}
                                            </div>
                                        )}
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    )
}

function NestedArrayTable({ data, onUpdate }: { data: any[], onUpdate?: (newData: any[]) => void }) {
    const [isExpanded, setIsExpanded] = useState(true)
    return (
        <DeepTable
            data={data}
            onUpdate={onUpdate}
            isExpanded={isExpanded}
            onToggleExpand={() => setIsExpanded(!isExpanded)}
        />
    )
}

export function EditableValueCell({
    value,
    onChange
}: {
    value: any
    onChange: (newValue: any) => void
}) {
    let parsedValue = value

    if (typeof value === 'string') {
        const cleanValue = value.trim()
        if (cleanValue.startsWith('[') || cleanValue.startsWith('{')) {
            try {
                parsedValue = JSON.parse(cleanValue)
            } catch (e) { }
        }
    }

    const isArray = Array.isArray(parsedValue)
    const isObject = typeof parsedValue === 'object' && parsedValue !== null && !isArray
    const hasValue = value !== null && value !== undefined && value !== ''

    if (isArray) {
        return (
            <div className="w-full overflow-hidden">
                <NestedArrayTable data={parsedValue} onUpdate={onChange} />
                <div className="text-[10px] text-muted-foreground mt-1 text-right">
                    * 테이블 모드로 자동 변환됨
                </div>
            </div>
        )
    }

    if (isObject) {
        return (
            <div className="w-full overflow-hidden">
                <NestedArrayTable
                    data={[parsedValue]}
                    onUpdate={(newData) => onChange(newData[0] || {})}
                />
                <div className="text-[10px] text-muted-foreground mt-1 text-right">
                    * 단일 객체를 테이블로 표시
                </div>
            </div>
        )
    }

    return hasValue ? (
        <textarea
            className="w-full bg-card border border-input rounded-md px-2 py-1 shadow-sm hover:border-primary/50 focus:border-primary focus:ring-1 focus:ring-primary outline-none text-foreground min-h-[32px] resize-y text-sm block transition-all"
            style={{ fieldSizing: 'content' } as any}
            value={renderValue(value)}
            onChange={(e) => onChange(e.target.value)}
            placeholder="값 입력..."
            rows={1}
        />
    ) : (
        <input
            type="text"
            className="w-full bg-chart-4/10 border-b border-chart-4/30 focus:border-primary focus:bg-card outline-none text-foreground py-0.5 placeholder-chart-4"
            value=""
            onChange={(e) => onChange(e.target.value)}
            placeholder="값을 찾지 못함 - 직접 입력"
        />
    )
}
