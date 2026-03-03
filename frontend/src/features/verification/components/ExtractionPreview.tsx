/* eslint-disable @typescript-eslint/no-explicit-any */
/* eslint-disable @typescript-eslint/no-unused-expressions */
/* eslint-disable @typescript-eslint/no-unused-vars */
/* eslint-disable react-hooks/exhaustive-deps */

/* eslint-disable react-hooks/rules-of-hooks */
import { useState, useEffect, useRef, useMemo } from 'react'
import { Check, ChevronDown, ChevronUp, ChevronRight, Sparkles, Database, Plus, Edit2, Save } from 'lucide-react'
import { clsx } from 'clsx'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { useVirtualizer } from '@tanstack/react-virtual'
import type { DexValidationData } from './DexValidationBanner'

interface ExtractionPreviewProps {
    guideExtracted: Record<string, any>
    otherData: Array<{ column: string; value: any; confidence?: number; bbox?: number[] }>
    modelFields: Array<{ key: string; label: string }>

    onFieldSelect?: (fieldKey: string | null) => void
    onDataChange?: (data: { guide: Record<string, any>, other: any[] }) => void
    onSave?: (guide: Record<string, any>, other: any[]) => void

    selectedField?: string | null // Controlled selection prop
    readOnly?: boolean
    dexValidation?: DexValidationData
}

function extractValue(data: any): any {
    // Handle null/undefined
    if (data === null || data === undefined) return data

    // If it's a primitive, return as-is
    if (typeof data !== 'object') return data

    // Case 1: Standard rich object { value: "xxx", confidence: 0.9, ... }
    if ('value' in data) {
        return data.value
    }

    // Case 1.5: Dictionary normalized object in arrays
    if (data && typeof data === 'object' && !Array.isArray(data) && 'raw_value' in data) {
        return data.raw_value
    }

    // Case 2: OpenAI sometimes returns arrays of rich objects - don't unwrap these
    if (Array.isArray(data)) {
        return data
    }

    // Case 3: Single-key object where the key might be a header OpenAI added
    // e.g., { "graduation_date": "2024" } - just return the whole object
    // We let renderValue handle stringification
    return data
}

function extractConfidence(data: any): number | null {
    if (data && typeof data === 'object' && 'confidence' in data) {
        return data.confidence
    }
    return null
}

function calculateTableAverage(data: any[]): number | null {
    if (!Array.isArray(data) || data.length === 0) return null
    let totalConf = 0
    let count = 0
    data.forEach(row => {
        if (!row || typeof row !== 'object') return
        Object.values(row).forEach(val => {
            const conf = extractConfidence(val)
            if (conf !== null) {
                totalConf += conf
                count++
            }
        })
    })
    return count > 0 ? totalConf / count : null
}

function ConfidenceBadge({ confidence }: { confidence: number | null }) {
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
    try {
        // First unwrap if it's a rich object with .value
        const unwrapped = extractValue(value)
        if (typeof unwrapped === 'object') {
            return JSON.stringify(unwrapped, null, 2) ?? ''
        }
        return String(unwrapped ?? '')
    } catch {
        // Fallback for circular references or other serialization errors
        return String(value ?? '')
    }
}

/**
 * 중첩 객체 데이터를 행으로 풀어내는 함수
 * 가장 깊은 레벨의 공통 키를 기반으로 행을 분리합니다.
 * 
 * 예시 입력:
 * [{ POD: "USCHS", "Approved Rate (USD)": { "20'DV": "1440", "40'DV": "1800" }, "Approved ADF (USD)": { "20'DV": "360", "40'DV": "450" } }]
 * 
 * 예시 출력:
 * [
 *   { POD: "USCHS", "_container_type": "20'DV", "Approved Rate (USD)": "1440", "Approved ADF (USD)": "360" },
 *   { POD: "USCHS", "_container_type": "40'DV", "Approved Rate (USD)": "1800", "Approved ADF (USD)": "450" }
 * ]
 */
function flattenNestedRows(data: any[]): { flattenedData: any[], keyColumn: string | null } {
    if (!Array.isArray(data) || data.length === 0) {
        return { flattenedData: data, keyColumn: null }
    }

    // 1. 모든 행에서 중첩 객체 컬럼과 그 키를 분석
    const nestedColumns: Record<string, Set<string>> = {}
    const simpleColumns: Set<string> = new Set()

    data.forEach(row => {
        if (typeof row !== 'object' || row === null) return
        try {
            Object.entries(row).forEach(([key, rawValue]) => {
                // Skip metadata columns
                if (key === 'bbox' || key === 'confidence' || key === 'page_number') {
                    simpleColumns.add(key)
                    return
                }

                // 먼저 래핑된 값을 언래핑 (예: { value: {...}, confidence: 0.9 } → {...})
                const value = extractValue(rawValue)

                if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
                    // 중첩 객체 발견 (예: { "20'DV": "1440", "40'DV": "1800" })
                    const subKeys = Object.keys(value)
                    if (subKeys.length > 0) {
                        if (!nestedColumns[key]) {
                            nestedColumns[key] = new Set()
                        }
                        subKeys.forEach(sk => nestedColumns[key].add(sk))
                    }
                } else {
                    simpleColumns.add(key)
                }
            })
        } catch {
            // Skip malformed rows
        }
    })

    const nestedColumnKeys = Object.keys(nestedColumns)

    // 중첩 컬럼이 없으면 원본 반환
    if (nestedColumnKeys.length === 0) {
        return { flattenedData: data, keyColumn: null }
    }

    // 2. 모든 중첩 컬럼에서 공통된 서브키 찾기 (예: "20'DV", "40'DV", "40'HC")
    const allSubKeys: Set<string> = new Set()
    Object.values(nestedColumns).forEach(subKeySet => {
        subKeySet.forEach(sk => allSubKeys.add(sk))
    })

    const subKeysArray = Array.from(allSubKeys)
    if (subKeysArray.length === 0) {
        return { flattenedData: data, keyColumn: null }
    }

    // 3. 각 행을 서브키 기준으로 풀어내기
    const flattenedData: any[] = []
    const keyColumnName = '_container_type' // 키 컬럼 이름

    data.forEach(row => {
        if (typeof row !== 'object' || row === null) {
            flattenedData.push(row)
            return
        }

        // 이 행에 해당하는 서브키 수집
        const rowSubKeys: Set<string> = new Set()
        nestedColumnKeys.forEach(colKey => {
            const rawNested = row[colKey]
            const nested = extractValue(rawNested) // 언래핑
            if (typeof nested === 'object' && nested !== null && !Array.isArray(nested)) {
                Object.keys(nested).forEach(sk => rowSubKeys.add(sk))
            }
        })

        if (rowSubKeys.size === 0) {
            // 서브키가 없으면 원본 행 유지
            flattenedData.push(row)
            return
        }

        // 각 서브키에 대해 새 행 생성
        rowSubKeys.forEach(subKey => {
            const newRow: Record<string, any> = { [keyColumnName]: subKey }

            // 단순 컬럼 복사 (언래핑해서 값만 복사, 메타데이터 제외)
            const metadataColumns = ['bbox', 'confidence', 'page_number']
            simpleColumns.forEach(col => {
                if (col in row && !metadataColumns.includes(col)) {
                    newRow[col] = extractValue(row[col])
                }
            })

            // 중첩 컬럼에서 해당 서브키 값 추출
            nestedColumnKeys.forEach(colKey => {
                const rawNested = row[colKey]
                const nested = extractValue(rawNested) // 언래핑
                if (typeof nested === 'object' && nested !== null && !Array.isArray(nested)) {
                    newRow[colKey] = nested[subKey] ?? ''
                } else {
                    newRow[colKey] = nested
                }
            })

            flattenedData.push(newRow)
        })
    })

    return { flattenedData, keyColumn: keyColumnName }
}

function ResizableNestedTable({
    data,
    onUpdate,
    isExpanded = true,
    onToggleExpand,
    dexValidation
}: {
    data: any[]
    onUpdate?: (newData: any[]) => void
    isExpanded?: boolean
    onToggleExpand?: () => void
    dexValidation?: DexValidationData
}) {
    // Import useVirtualizer dynamically if possible, or assume it's imported at top
    // Since this is a replacement, I need to add the import at the top of the file separately.
    // For now, I'll assume the import is added.

    // NOTE: Requires `import { useVirtualizer } from '@tanstack/react-virtual'` at top of file

    const [columnWidths, setColumnWidths] = useState<Record<string, number>>({})
    const [resizingColumn, setResizingColumn] = useState<string | null>(null)
    const tableContainerRef = useRef<HTMLDivElement>(null)

    // Local state to buffer edits and prevent lag from parent re-renders
    const [localData, setLocalData] = useState<any[]>([])
    const isLocalUpdate = useRef(false)
    const updateTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

    // Sync local state with props when props change (and not from our own update)
    useEffect(() => {
        if (!isLocalUpdate.current && Array.isArray(data)) {
            setLocalData(data)
        }
        isLocalUpdate.current = false
    }, [data])



    // Normalize: parse stringified JSON objects within array
    const normalizedData = useMemo(() => localData.map((item: any) => {
        if (item === null || item === undefined) return item
        if (typeof item === 'string') {
            const trimmed = item.trim()
            if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
                try {
                    const parsed = JSON.parse(trimmed)
                    // Only use parsed result if it's an actual object/array
                    if (typeof parsed === 'object' && parsed !== null) return parsed
                } catch { /* keep as string */ }
            }
        }
        return item
    }), [localData])

    // 중첩 데이터를 풀어내기
    // Memoize to prevent recalculation on every render
    const { flattenedData, keyColumn } = useMemo(() => flattenNestedRows(normalizedData), [normalizedData])
    const displayData = flattenedData

    // 키 컬럼을 맨 앞에 배치하기 위해 컬럼 순서 조정
    const allKeysRaw = useMemo(() => Array.from(new Set(displayData.flatMap((item: any) =>
        typeof item === 'object' && item !== null ? Object.keys(item) : []
    ))), [displayData])

    // Hide bbox/ref metadata columns (confidence is intentionally kept visible)
    const hiddenColumns = ['bbox', 'page_number', 'ref_id', 'source_text', 'validation_status', 'ref']
    const allKeys = useMemo(() => allKeysRaw
        .filter((k: string) => !hiddenColumns.includes(k))
        .sort((a: string, b: string) => {
            if (a === keyColumn) return -1
            if (b === keyColumn) return 1
            return 0
        }), [allKeysRaw, keyColumn])


    // Initialize column widths - only runs once when data changes and widths are empty
    useEffect(() => {
        if (allKeys.length > 0 && Object.keys(columnWidths).length === 0) {
            const initialWidths: Record<string, number> = {}
            const defaultWidth = Math.max(100, Math.floor(800 / allKeys.length))
            allKeys.forEach((key: string) => {
                initialWidths[key] = defaultWidth
            })
            setColumnWidths(initialWidths)
        }

    }, [data.length, columnWidths]) // Use data.length instead of allKeys array

    // Virtualizer setup (MUST BE CALLED UNCONDITIONALLY)
    const virtualizer = useVirtualizer({
        count: displayData.length,
        getScrollElement: () => tableContainerRef.current,
        estimateSize: () => 40, // Row height
        overscan: 10,
    })


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

    // Handle Local Update
    const handleLocalUpdate = (index: number, key: string, value: string) => {
        setLocalData(prev => {
            const newData = [...prev]
            if (newData[index] != null && typeof newData[index] === 'object') {
                const existingCellData = newData[index][key]
                if (existingCellData && typeof existingCellData === 'object' && ('raw_value' in existingCellData || 'confidence' in existingCellData)) {
                    // Update the wrapper, explicitly clearing AI normalization since user manually edited it
                    newData[index] = {
                        ...newData[index],
                        [key]: {
                            ...existingCellData,
                            raw_value: value,
                            value: value, // for legacy fallback
                            normalized_code: null,
                            dict_score: null,
                            validation_status: null,
                            validation_msg: null
                        }
                    }
                } else {
                    // Simple string field
                    newData[index] = { ...newData[index], [key]: value }
                }
            }
            return newData
        })

        // Mark as local update to avoid immediate overwrite provided by prop effect
        isLocalUpdate.current = true
    }

    // Effect to sync to parent after debounce
    useEffect(() => {
        if (isLocalUpdate.current && onUpdate) {
            if (updateTimeoutRef.current) clearTimeout(updateTimeoutRef.current)
            updateTimeoutRef.current = setTimeout(() => {
                onUpdate(localData)
                // Keep isLocalUpdate true until prop actually changes back? 
                // No, we reset it in the prop effect.
            }, 800)
        }
        return () => {
            if (updateTimeoutRef.current) clearTimeout(updateTimeoutRef.current)
        }
    }, [localData, onUpdate])

    // --- RENDER CHECKS (AFTER ALL HOOKS) ---

    // Empty Data Check
    if (!Array.isArray(data) || data.length === 0 || allKeys.length === 0) {
        if (allKeys.length === 0 && Array.isArray(data) && data.length > 0) {
            // Case: Array of primitives?
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
        return <span className="text-muted-foreground italic text-xs">빈 배열</span>
    }



    // Collapsed view: show summary
    if (!isExpanded) {
        return (
            <button
                onClick={onToggleExpand}
                className="flex items-center gap-2 px-3 py-2 bg-muted/50 hover:bg-muted rounded-lg text-sm text-muted-foreground hover:text-foreground transition-colors w-full text-left"
            >
                <ChevronRight className="w-4 h-4" />
                <span className="font-medium">테이블 ({displayData.length}행 × {allKeys.length}열)</span>
                <span className="text-xs">클릭하여 펼치기</span>
            </button>
        )
    }



    return (
        <div className="border border-border rounded-lg overflow-hidden flex flex-col h-full max-h-[600px]">
            {/* Header with controls */}
            <div className="flex items-center justify-between px-3 py-1.5 bg-muted/50 border-b border-border shrink-0">
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

            </div>

            {/* Scrollable table container with Virtualization */}
            <div
                ref={tableContainerRef}
                className="overflow-auto relative bg-card flex-1"
                style={{ height: '100%' }}
            >
                <table className="text-sm w-full relative border-collapse" style={{ minWidth: '100%' }}>
                    <thead className="sticky top-0 z-10 bg-muted shadow-sm block w-full">
                        <tr className="flex w-full">
                            {allKeys.map((key: string, idx: number) => (
                                <th
                                    key={key}
                                    className="text-left font-medium text-muted-foreground border-b border-border relative group select-none shrink-0 block"
                                    style={{
                                        width: idx === allKeys.length - 1 ? undefined : (columnWidths[key] || 100),
                                        minWidth: 60,
                                        ...(idx === allKeys.length - 1 ? { flex: 1 } : {})
                                    }}
                                >
                                    <div className="px-3 py-2 truncate">
                                        {key === '_container_type' ? '컨테이너' : key}
                                    </div>
                                    {/* Resize handle */}
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
                    <tbody style={{ height: `${virtualizer.getTotalSize()}px`, position: 'relative', display: 'block' }}>
                        {virtualizer.getVirtualItems().map((virtualRow) => {
                            const row = displayData[virtualRow.index]
                            const isHighlightRow = !!dexValidation
                            const isDuplicateRow = !!row?._is_duplicate
                            const rowWarnings = row?._row_warnings as string[] | undefined

                            return (
                                <tr
                                    key={virtualRow.index}
                                    className={clsx(
                                        "absolute top-0 left-0 w-full flex",
                                        isDuplicateRow && "bg-orange-50/50 hover:bg-orange-100/50 border-l-4 border-l-orange-500",
                                        isHighlightRow
                                            ? (dexValidation.status === 'PASS'
                                                ? "bg-emerald-50/50 hover:bg-emerald-100/50 border-l-4 border-l-emerald-500"
                                                : "bg-destructive/10 hover:bg-destructive/20 border-l-4 border-l-destructive")
                                            : !isDuplicateRow && "hover:bg-accent/50"
                                    )}
                                    style={{
                                        height: `${virtualRow.size}px`,
                                        transform: `translateY(${virtualRow.start}px)`
                                    }}
                                >
                                    {allKeys.map((key: string, idx: number) => (
                                        <td
                                            key={key}
                                            className={clsx(
                                                "text-muted-foreground border-b border-transparent shrink-0",
                                                key === keyColumn && "bg-muted/50 font-medium"
                                            )}
                                            style={{
                                                width: idx === allKeys.length - 1 ? undefined : (columnWidths[key] || 100),
                                                minWidth: 60,
                                                display: 'block',
                                                height: '100%',
                                                ...(idx === allKeys.length - 1 ? { flex: 1 } : {})
                                            }}
                                        >
                                            {onUpdate ? (
                                                <input
                                                    id={`table-cell-${virtualRow.index}-${key}`}
                                                    name={`table-cell-${virtualRow.index}-${key}`}
                                                    type="text"
                                                    className="w-full h-full bg-transparent border-none hover:bg-accent/30 focus:bg-accent focus:ring-1 focus:ring-primary outline-none px-3 text-sm"
                                                    value={renderValue(row != null ? row[key] : '')}
                                                    onChange={(e) => {
                                                        handleLocalUpdate(virtualRow.index, key, e.target.value)
                                                    }}
                                                />
                                            ) : (
                                                <div className="px-3 py-2 truncate h-full flex flex-col justify-center">
                                                    <div>{renderValue(row != null ? row[key] : '')}</div>
                                                    {row?.[key] && typeof row[key] === 'object' && row[key].normalized_code && (
                                                        <div className="text-[9px] font-semibold px-1 rounded bg-blue-50/80 text-blue-700 w-fit mt-0.5 border border-blue-200">
                                                            정규화: {row[key].normalized_code}
                                                        </div>
                                                    )}
                                                    {isDuplicateRow && key === allKeys[0] && rowWarnings && (
                                                        <div className="text-[10px] items-center text-orange-700 font-semibold flex gap-1 mt-1">
                                                            ⚠️ 중복 감지
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </td>
                                    ))}
                                </tr>
                            )
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    )
}

// Legacy wrapper for backward compatibility
function NestedArrayTable({ data, onUpdate, dexValidation }: { data: any[], onUpdate?: (newData: any[]) => void, dexValidation?: DexValidationData }) {
    const [isExpanded, setIsExpanded] = useState(true)
    return (
        <ResizableNestedTable
            data={data}
            onUpdate={onUpdate}
            isExpanded={isExpanded}
            onToggleExpand={() => setIsExpanded(!isExpanded)}
            dexValidation={dexValidation}
        />
    )
}


function EditableValueCell({
    value,
    rawData,
    onChange,
    dexValidation
}: {
    value: any
    rawData?: any
    onChange: (newValue: any) => void
    dexValidation?: DexValidationData
}) {
    // Try to parse JSON strings
    let parsedValue = value

    // Logic to handle potential JSON strings, including markdown blocks
    if (typeof value === 'string') {
        const cleanValue = value.trim()
        if (cleanValue === "null") {
            parsedValue = null
        } else if (cleanValue.startsWith('[') || cleanValue.startsWith('{')) {
            try {
                parsedValue = JSON.parse(cleanValue)
            } catch (e) {
                // Ignore parse error
            }
        }
    }

    const isArray = Array.isArray(parsedValue)
    // Check if it's a rich object from the backend (i.e. just a value and confidence wrapper)
    const isRichScalar = typeof parsedValue === 'object' && parsedValue !== null && !isArray && Object.keys(parsedValue).length <= 5 && 'value' in parsedValue;
    const isObject = typeof parsedValue === 'object' && parsedValue !== null && !isArray && !isRichScalar;
    const hasValue = value !== null && value !== undefined && value !== ''

    if (isArray) {
        return (
            <div className="w-full overflow-hidden">
                <NestedArrayTable
                    data={parsedValue}
                    onUpdate={(newData) => {
                        onChange(newData)
                    }}
                    dexValidation={dexValidation}
                />
                <div className="flex justify-between flex-wrap items-center mt-1 gap-2">
                    <div className="text-[10px] text-muted-foreground">
                        * 테이블 모드로 자동 변환됨
                    </div>
                    {dexValidation && (
                        <div className="text-[11px] font-semibold px-2 py-0.5 rounded bg-amber-50 border border-amber-200 text-amber-800 flex items-center gap-1 shadow-sm">
                            <span className="opacity-70">바코드 정답:</span> {dexValidation.lis_expected_value}
                        </div>
                    )}
                </div>
            </div>
        )
    }

    if (isObject) {
        // Wrap single object in array to render as 1-row table
        return (
            <div className="w-full overflow-hidden">
                <NestedArrayTable
                    data={[parsedValue]}
                    onUpdate={(newData) => {
                        // Extract the single object back from array
                        onChange(newData[0] || {})
                    }}
                    dexValidation={dexValidation}
                />
                <div className="flex justify-between flex-wrap items-center mt-1 gap-2">
                    <div className="text-[10px] text-muted-foreground">
                        * 단일 객체를 테이블로 표시
                    </div>
                    {dexValidation && (
                        <div className="text-[11px] font-semibold px-2 py-0.5 rounded bg-amber-50 border border-amber-200 text-amber-800 flex items-center gap-1 shadow-sm">
                            <span className="opacity-70">바코드 정답:</span> {dexValidation.lis_expected_value}
                        </div>
                    )}
                </div>
            </div>
        )
    }

    // Default Text Input (changed to Textarea for better visibility of long content)
    return (
        <div className="w-full flex flex-col gap-1.5">
            {hasValue ? (
                <textarea
                    className="w-full bg-transparent border-b border-transparent hover:border-border focus:border-primary focus:bg-card outline-none text-foreground py-1 min-h-[24px] resize-y text-sm block"
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
            )}

            {rawData?.normalized_code && (
                <div className="flex justify-start w-full mt-0.5">
                    <div className="text-[11px] font-semibold px-2 py-0.5 rounded bg-blue-50 border border-blue-200 text-blue-800 flex items-center gap-1 shadow-sm" title={`정확도: ${Math.round((rawData.dict_score || 0) * 100)}%`}>
                        <span className="opacity-70">정규화:</span> {rawData.normalized_code}
                    </div>
                </div>
            )}
            {rawData?.validation_status === 'error' && (
                <div className="flex justify-start w-full mt-0.5">
                    <div className="text-[11px] font-semibold px-2 py-0.5 rounded bg-destructive/10 border border-destructive text-destructive flex items-center gap-1 shadow-sm">
                        <span className="opacity-70">경고:</span> {rawData?.validation_msg || "검증 실패"}
                    </div>
                </div>
            )}

            {dexValidation && (
                <div className="flex justify-end w-full">
                    <div className="text-[11px] font-semibold px-2 py-0.5 rounded bg-amber-50 border border-amber-200 text-amber-800 flex items-center gap-1 shadow-sm">
                        <span className="opacity-70">바코드 정답:</span> {dexValidation.lis_expected_value}
                    </div>
                </div>
            )}
        </div>
    )
}

export function ExtractionPreview({
    guideExtracted,
    otherData,
    modelFields,
    onFieldSelect,
    onDataChange,
    onSave,
    selectedField: controlledSelectedField,
    readOnly = false,
    dexValidation
}: ExtractionPreviewProps) {
    // -- Local State --
    // Legacy Array Check (Should be false for new backend, but kept for safety)
    const isLegacyArray = Array.isArray(guideExtracted)

    // Auto-detect Table Field in Dict Mode
    // Finds the first field that looks like a table (Array of Objects)
    const defaultTableKey = useMemo(() => {
        if (isLegacyArray) return null
        for (const [key, val] of Object.entries(guideExtracted)) {
            const rawVal = extractValue(val)
            if (Array.isArray(rawVal) && rawVal.length > 0 && typeof rawVal[0] === 'object') {
                return key
            }
        }
        return null
    }, [guideExtracted, isLegacyArray])

    // State for Active Table View (null = Form View, string = Field Key for Table View)
    // Default to Form View (null) as per user feedback (Table View hides other fields)
    const [activeTableKey, setActiveTableKey] = useState<string | null>(null)

    // Main Data State
    // If Legacy Array: state is Array. If Dict: state is Dict.
    const [editedGuideData, setEditedGuideData] = useState<Record<string, any> | any[]>(() =>
        isLegacyArray ? [...(guideExtracted as any[])] : { ...guideExtracted }
    )
    const [editedOtherData, setEditedOtherData] = useState<Array<{ column: any; value: any }>>(() => [...otherData])

    // Store callback in ref to prevent infinite loops
    const onDataChangeRef = useRef(onDataChange)
    onDataChangeRef.current = onDataChange

    // Track if initial sync is done to prevent triggering onDataChange during mount
    const isInitializedRef = useRef(false)

    const [selectedOtherColumns, setSelectedOtherColumns] = useState<Set<string>>(new Set())
    const [showOtherData, setShowOtherData] = useState(false)
    // -- Selection State --
    const [internalSelectedField, setInternalSelectedField] = useState<string | null>(null)
    const selectedField = controlledSelectedField !== undefined ? controlledSelectedField : internalSelectedField

    // Sync scroll when selectedField changes
    useEffect(() => {
        if (selectedField) {
            const el = document.getElementById(`field-row-${selectedField}`)
            if (el) {
                el.scrollIntoView({ behavior: 'smooth', block: 'center' })
            }
        }
    }, [selectedField])

    // Auto-propagate changes to parent (but skip initial mount)
    useEffect(() => {
        if (!isInitializedRef.current) {
            isInitializedRef.current = true
            return
        }

        if (!onDataChangeRef.current) return

        const selectedEditedOtherData = editedOtherData.filter(item => {
            const columnName = typeof item.column === 'object'
                ? JSON.stringify(item.column)
                : String(item.column ?? '')
            return selectedOtherColumns.has(columnName)
        })

        onDataChangeRef.current({
            guide: editedGuideData,
            other: selectedEditedOtherData
        })
    }, [editedGuideData, editedOtherData, selectedOtherColumns])

    const handleFieldClick = (key: string) => {
        const newSelection = selectedField === key ? null : key
        if (controlledSelectedField === undefined) {
            setInternalSelectedField(newSelection)
        }
        onFieldSelect?.(newSelection)
    }

    const updateGuideField = (key: string, value: any) => {
        setEditedGuideData(prev => ({ ...prev, [key]: value }))
    }

    const updateOtherDataItem = (idx: number, field: 'column' | 'value', newValue: any) => {
        setEditedOtherData(prev => {
            const updated = [...prev]
            if (updated[idx]) {
                updated[idx] = { ...updated[idx], [field]: newValue }
            }
            return updated
        })
    }

    const toggleOtherColumn = (columnName: string) => {
        const newSelection = new Set(selectedOtherColumns)
        if (newSelection.has(columnName)) {
            newSelection.delete(columnName)
        } else {
            newSelection.add(columnName)
        }
        setSelectedOtherColumns(newSelection)
    }

    // Identify Table Mode vs Form Mode
    // Show Table View if: Legacy Array OR Active Table Key is selected
    const showTableView = isLegacyArray || !!activeTableKey

    // Get Data for Table View
    const getTableData = () => {
        if (isLegacyArray) return editedGuideData as any[]
        if (activeTableKey) {
            const val = (editedGuideData as Record<string, any>)[activeTableKey]
            return extractValue(val) // Unwrap if needed
        }
        return []
    }

    const guideFieldCount = modelFields.length
    const filledFieldCount = isLegacyArray
        ? (editedGuideData as any[]).length
        : Object.values(editedGuideData).filter(v => v !== null && v !== '' && v !== undefined).length

    return (
        <Card className="flex flex-col h-full overflow-hidden">
            <div className="px-6 py-3 border-b border-border bg-gradient-to-r from-primary/10 to-chart-5/10 flex items-center justify-between flex-shrink-0">
                <div>
                    <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
                        <Sparkles className="w-4 h-4 text-primary" />
                        AI 가이드 추출 완료
                    </h3>
                    <p className="text-xs text-muted-foreground flex items-center gap-1">
                        <Edit2 className="w-3 h-3" />
                        {filledFieldCount}/{guideFieldCount}개 필드
                        {activeTableKey && (
                            <span className="ml-2 px-1.5 py-0.5 bg-primary/20 text-primary rounded text-[10px] font-semibold">
                                TABLE MODE ({activeTableKey})
                            </span>
                        )}
                    </p>
                </div>
                <div className="flex gap-2">
                    {/* Toggle View Mode Button (Only for Mixed Models) */}
                    {!isLegacyArray && defaultTableKey && (
                        <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setActiveTableKey(prev => prev ? null : defaultTableKey)}
                            className="gap-1 h-8"
                        >
                            {activeTableKey ? <Database className="w-3.5 h-3.5" /> : <Database className="w-3.5 h-3.5" />}
                            {activeTableKey ? '폼 뷰로 보기' : '테이블 뷰로 보기'}
                        </Button>
                    )}

                    {!readOnly && onSave && (
                        <Button
                            size="sm"
                            onClick={() => {
                                import.meta.env.DEV && console.log('[SaveButton] Clicked')
                                toast.info('저장 중...')
                                const selectedEditedOtherData = editedOtherData.filter(item => {
                                    const columnName = typeof item.column === 'object'
                                        ? JSON.stringify(item.column)
                                        : String(item.column ?? '')
                                    return selectedOtherColumns.has(columnName)
                                })
                                onSave(editedGuideData, selectedEditedOtherData)
                            }}
                            className="gap-1"
                        >
                            <Save className="w-4 h-4" />
                            저장
                        </Button>
                    )}
                </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto">
                {/* Guide Extracted Section */}
                <div className="border-b border-border">
                    <div className="px-6 py-3 bg-primary/10 flex items-center gap-2">
                        <Sparkles className="w-4 h-4 text-primary" />
                        <span className="text-sm font-semibold text-foreground">
                            {showTableView
                                ? `테이블 추출 완료 (${getTableData().length}행)`
                                : `참고정보 기반 추출 (${filledFieldCount}개 값)`
                            }
                        </span>
                    </div>

                    {/* TABLE MODE: render full editable table */}
                    {showTableView ? (
                        <div className="p-4">
                            <ResizableNestedTable
                                data={getTableData()}
                                onUpdate={!readOnly ? (newData) => {
                                    if (isLegacyArray) {
                                        setEditedGuideData(newData as any)
                                    } else if (activeTableKey) {
                                        // Update the specific field in the Dict
                                        updateGuideField(activeTableKey, newData)
                                    }
                                } : undefined}
                                isExpanded={true}
                            />
                        </div>
                    ) : (() => {
                        /* STANDARD MODE: field-by-field rendering */
                        const guideDataDict = editedGuideData as Record<string, any>;
                        return (
                            <table className="w-full text-sm table-fixed">
                                <thead>
                                    <tr className="bg-muted text-xs uppercase text-muted-foreground">
                                        <th className="px-6 py-3 text-left font-semibold w-[200px]">필드명</th>
                                        <th className="px-6 py-3 text-left font-semibold">추출값 (편집 가능)</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-border">
                                    {modelFields.map(field => {
                                        const rawData = guideDataDict[field.key]
                                        const value = extractValue(rawData)
                                        let confidence = extractConfidence(rawData)
                                        const hasValue = value !== null && value !== '' && value !== undefined

                                        // Highlight table fields that can be expanded
                                        const isTableField = Array.isArray(value) && value.length > 0 && typeof value[0] === 'object'

                                        // For table fields, show average confidence in the row badge
                                        if (isTableField) {
                                            const avg = calculateTableAverage(value)
                                            if (avg !== null) confidence = avg
                                        }

                                        const isLowConfidence = confidence !== null && confidence < 0.9

                                        const isDexValidationTarget = dexValidation?.target_field_key === field.key
                                        const hasDexFailed = isDexValidationTarget && dexValidation?.status === 'FAIL'
                                        const hasDexPassed = isDexValidationTarget && dexValidation?.status === 'PASS'

                                        return (
                                            <tr
                                                key={field.key}
                                                className={clsx(
                                                    hasDexFailed ? "bg-destructive/10 border-l-4 border-l-destructive" :
                                                        hasDexPassed ? "bg-emerald-50/50 border-l-4 border-l-emerald-500" :
                                                            hasValue ? "bg-card" : "bg-chart-4/5",
                                                    isLowConfidence && !hasDexFailed && "bg-chart-4/5",
                                                    selectedField === field.key && "ring-2 ring-primary bg-primary/5",
                                                    "cursor-pointer hover:bg-accent transition-colors relative"
                                                )}
                                                id={`field-row-${field.key}`}
                                                onClick={() => handleFieldClick(field.key)}
                                                onMouseEnter={() => {
                                                    if (selectedField === undefined) {
                                                        setInternalSelectedField(field.key)
                                                    }
                                                }}
                                            >
                                                <td className="px-6 py-4 align-top">
                                                    <div className="font-medium text-foreground flex items-center gap-2">
                                                        {field.label}
                                                        {isTableField && (
                                                            <button
                                                                onClick={(e) => {
                                                                    e.stopPropagation()
                                                                    setActiveTableKey(field.key)
                                                                }}
                                                                className="text-[10px] px-1.5 py-0.5 bg-primary/10 text-primary hover:bg-primary hover:text-primary-foreground rounded transition-colors"
                                                            >
                                                                테이블 보기
                                                            </button>
                                                        )}
                                                    </div>
                                                    <div className="text-xs text-muted-foreground">{field.key}</div>
                                                    {selectedField === field.key && (
                                                        <div className="text-xs text-primary mt-1">📍 PDF에서 보기</div>
                                                    )}
                                                </td>
                                                <td className="px-6 py-4">
                                                    <div className="flex items-center">
                                                        <div className="flex-1">
                                                            <div className="flex-1">
                                                                {readOnly ? (
                                                                    <div className="py-0.5 min-h-[24px] flex items-center">
                                                                        <span className="text-foreground break-all">{typeof value === 'object' ? JSON.stringify(value) : value}</span>
                                                                    </div>
                                                                ) : (
                                                                    <EditableValueCell
                                                                        value={value}
                                                                        rawData={rawData}
                                                                        dexValidation={dexValidation?.target_field_key === field.key ? dexValidation : undefined}
                                                                        onChange={(newValue) => updateGuideField(field.key,
                                                                            rawData && typeof rawData === 'object' && ('confidence' in rawData || 'raw_value' in rawData)
                                                                                ? {
                                                                                    ...rawData,
                                                                                    value: newValue,
                                                                                    raw_value: newValue,
                                                                                    normalized_code: null,
                                                                                    dict_score: null,
                                                                                    validation_status: null,
                                                                                    validation_msg: null
                                                                                }
                                                                                : newValue
                                                                        )}
                                                                    />
                                                                )}
                                                            </div>
                                                        </div>
                                                        <ConfidenceBadge confidence={confidence} />
                                                    </div>
                                                </td>
                                            </tr>
                                        )
                                    })}
                                </tbody>
                            </table>
                        );
                    })()}
                </div >

                {/* Other Data Section */}
                {
                    otherData.length > 0 && (
                        <div>
                            <button
                                onClick={() => setShowOtherData(!showOtherData)}
                                className="w-full px-4 py-2 bg-muted flex items-center justify-between sticky top-0 z-10 hover:bg-accent transition-colors"
                            >
                                <div className="flex items-center gap-2">
                                    <Database className="w-4 h-4 text-muted-foreground" />
                                    <span className="text-sm font-semibold text-foreground">
                                        그 외 추출 데이터 ({otherData.length}개)
                                    </span>
                                    {selectedOtherColumns.size > 0 && (
                                        <span className="px-2 py-0.5 bg-primary/10 text-primary text-xs rounded-full">
                                            +{selectedOtherColumns.size} 선택됨
                                        </span>
                                    )}
                                </div>
                                {showOtherData ? (
                                    <ChevronUp className="w-4 h-4 text-muted-foreground" />
                                ) : (
                                    <ChevronDown className="w-4 h-4 text-muted-foreground" />
                                )}
                            </button>
                            {showOtherData && (
                                <div className="divide-y divide-border">
                                    {editedOtherData.map((item, idx) => {
                                        if (!item) return null
                                        const columnName = typeof item.column === 'object'
                                            ? JSON.stringify(item.column)
                                            : String(item.column ?? '')
                                        const isSelected = selectedOtherColumns.has(columnName)
                                        const isArrayValue = Array.isArray(item.value)

                                        const key = typeof item.column === 'object' ? JSON.stringify(item.column) : String(item.column)
                                        return (
                                            <div
                                                key={idx}
                                                id={`field-row-${key}`}
                                                className={clsx(
                                                    "px-4 py-3 transition-colors cursor-pointer",
                                                    selectedField === key ? "ring-2 ring-primary bg-primary/5" : "hover:bg-accent",
                                                    isSelected && !selectedField && "bg-primary/5" // Keep selection bg if not focused
                                                )}
                                                onClick={() => handleFieldClick(key)}
                                            >
                                                <div className="flex items-start gap-3">
                                                    <div
                                                        className="pt-0.5 cursor-pointer"
                                                        onClick={() => toggleOtherColumn(columnName)}
                                                    >
                                                        {isSelected ? (
                                                            <Check className="w-4 h-4 text-primary" />
                                                        ) : (
                                                            <Plus className="w-4 h-4 text-muted-foreground" />
                                                        )}
                                                    </div>
                                                    <div className="flex-1 min-w-0 space-y-1">
                                                        <input
                                                            type="text"
                                                            className={clsx(
                                                                "w-full font-medium text-foreground text-sm bg-transparent border-b border-transparent outline-none",
                                                                !readOnly && "hover:border-border focus:border-primary"
                                                            )}
                                                            value={columnName}
                                                            onChange={(e) => !readOnly && updateOtherDataItem(idx, 'column', e.target.value)}
                                                            readOnly={readOnly}
                                                            placeholder="컬럼명 입력..."
                                                            onClick={(e) => e.stopPropagation()}
                                                        />
                                                        {isArrayValue ? (
                                                            <NestedArrayTable
                                                                data={item.value}
                                                                onUpdate={(newData) => !readOnly && updateOtherDataItem(idx, 'value', newData)}
                                                            />
                                                        ) : (
                                                            <input
                                                                type="text"
                                                                className={clsx(
                                                                    "w-full text-muted-foreground text-sm bg-transparent border-b border-transparent outline-none",
                                                                    !readOnly && "hover:border-border focus:border-primary"
                                                                )}
                                                                value={typeof item.value === 'object'
                                                                    ? JSON.stringify(item.value)
                                                                    : String(item.value ?? '')}
                                                                onChange={(e) => !readOnly && updateOtherDataItem(idx, 'value', e.target.value)}
                                                                readOnly={readOnly}
                                                                placeholder="값 입력..."
                                                                onClick={(e) => e.stopPropagation()}
                                                            />
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                        )
                                    })}
                                </div>
                            )}
                        </div>
                    )
                }
            </div >
        </Card >
    )
}
