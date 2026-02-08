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

interface ExtractionPreviewProps {
    guideExtracted: Record<string, any>
    otherData: Array<{ column: string; value: any; confidence?: number; bbox?: number[] }>
    modelFields: Array<{ key: string; label: string }>

    onFieldSelect?: (fieldKey: string | null) => void
    onDataChange?: (data: { guide: Record<string, any>, other: any[] }) => void
    onSave?: (guide: Record<string, any>, other: any[]) => void

    selectedField?: string | null // Controlled selection prop
    readOnly?: boolean
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

// Enhanced Nested Table with Column Resizing
function ResizableNestedTable({
    data,
    onUpdate,
    isExpanded = true,
    onToggleExpand
}: {
    data: any[]
    onUpdate?: (newData: any[]) => void
    isExpanded?: boolean
    onToggleExpand?: () => void
}) {
    // Import useVirtualizer dynamically if possible, or assume it's imported at top
    // Since this is a replacement, I need to add the import at the top of the file separately.
    // For now, I'll assume the import is added.

    // NOTE: Requires `import { useVirtualizer } from '@tanstack/react-virtual'` at top of file

    const [columnWidths, setColumnWidths] = useState<Record<string, number>>({})
    const [resizingColumn, setResizingColumn] = useState<string | null>(null)
    const [isEditMode, setIsEditMode] = useState(false) // 편집 모드 토글
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

    if (!Array.isArray(data) || data.length === 0) {
        return <span className="text-muted-foreground italic text-xs">빈 배열</span>
    }

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

    // 중첩 데이터를 풀어내기 (편집 모드가 아닐 때만)
    // Memoize to prevent recalculation on every render
    const { flattenedData, keyColumn } = useMemo(() => flattenNestedRows(normalizedData), [normalizedData])
    const displayData = isEditMode ? normalizedData : flattenedData
    const hasNestedData = keyColumn !== null // 플래터닝이 적용되었는지

    // 키 컬럼을 맨 앞에 배치하기 위해 컬럼 순서 조정
    const allKeysRaw = useMemo(() => Array.from(new Set(displayData.flatMap((item: any) =>
        typeof item === 'object' && item !== null ? Object.keys(item) : []
    ))), [displayData])

    // bbox, confidence, page_number 제외 및 키 컬럼 맨 앞에 배치
    const hiddenColumns = ['bbox', 'confidence', 'page_number']
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

    // Virtualizer setup
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
                newData[index] = { ...newData[index], [key]: value }
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
                {/* 편집 모드 토글 버튼 (중첩 데이터가 있을 때만 표시) */}
                {hasNestedData && onUpdate && (
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
                                        width: columnWidths[key] || 100,
                                        minWidth: 60,
                                        maxWidth: columnWidths[key] || 100
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
                            return (
                                <tr
                                    key={virtualRow.index}
                                    className="hover:bg-accent/50 absolute top-0 left-0 w-full flex"
                                    style={{
                                        height: `${virtualRow.size}px`,
                                        transform: `translateY(${virtualRow.start}px)`
                                    }}
                                >
                                    {allKeys.map((key: string) => (
                                        <td
                                            key={key}
                                            className={clsx(
                                                "text-muted-foreground border-b border-transparent shrink-0",
                                                key === keyColumn && "bg-muted/50 font-medium"
                                            )}
                                            style={{
                                                width: columnWidths[key] || 100,
                                                minWidth: 60,
                                                maxWidth: columnWidths[key] || 100,
                                                display: 'block', // Required for flex layout in absolute row
                                                height: '100%'
                                            }}
                                        >
                                            {isEditMode && onUpdate ? (
                                                <input
                                                    id={`table-cell-${virtualRow.index}-${key}`}
                                                    name={`table-cell-${virtualRow.index}-${key}`}
                                                    type="text"
                                                    className="w-full h-full bg-transparent border-none hover:bg-accent/30 focus:bg-accent focus:ring-1 focus:ring-primary outline-none px-3 text-sm"
                                                    value={renderValue(row != null ? row[key] : '')}
                                                    onChange={(e) => {
                                                        // Update local state immediately
                                                        handleLocalUpdate(virtualRow.index, key, e.target.value)
                                                    }}
                                                />
                                            ) : (
                                                <div className="px-3 py-2 truncate h-full flex items-center">
                                                    {renderValue(row != null ? row[key] : '')}
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
function NestedArrayTable({ data, onUpdate }: { data: any[], onUpdate?: (newData: any[]) => void }) {
    const [isExpanded, setIsExpanded] = useState(true)
    return (
        <ResizableNestedTable
            data={data}
            onUpdate={onUpdate}
            isExpanded={isExpanded}
            onToggleExpand={() => setIsExpanded(!isExpanded)}
        />
    )
}


function EditableValueCell({
    value,
    onChange
}: {
    value: any
    onChange: (newValue: any) => void
}) {
    // Try to parse JSON strings
    let parsedValue = value

    // Logic to handle potential JSON strings, including markdown blocks
    if (typeof value === 'string') {
        const cleanValue = value.trim()
        if (cleanValue.startsWith('[') || cleanValue.startsWith('{')) {
            try {
                parsedValue = JSON.parse(cleanValue)
            } catch (e) {
                // Ignore parse error
            }
        }
    }

    const isArray = Array.isArray(parsedValue)
    const isObject = typeof parsedValue === 'object' && parsedValue !== null && !isArray
    const hasValue = value !== null && value !== undefined && value !== ''

    if (isArray) {
        return (
            <div className="w-full overflow-hidden">
                <NestedArrayTable
                    data={parsedValue}
                    onUpdate={(newData) => {
                        onChange(newData)
                    }}
                />
                <div className="text-[10px] text-muted-foreground mt-1 text-right">
                    * 테이블 모드로 자동 변환됨
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
                />
                <div className="text-[10px] text-muted-foreground mt-1 text-right">
                    * 단일 객체를 테이블로 표시
                </div>
            </div>
        )
    }

    // Default Text Input (changed to Textarea for better visibility of long content)
    return hasValue ? (
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
    readOnly = false
}: ExtractionPreviewProps) {
    // -- Local State (Uncontrolled, initialized from props) --
    // We intentionally DO NOT sync this with useEffect to avoid infinite loops from parent updates.
    // The parent must force a re-mount (using key prop) to reset this component when switching documents.
    // TABLE MODE: state holds array; STANDARD MODE: state holds dict
    const isTableMode = Array.isArray(guideExtracted)
    const [editedGuideData, setEditedGuideData] = useState<Record<string, any> | any[]>(() =>
        isTableMode ? [...(guideExtracted as any[])] : { ...guideExtracted }
    )
    const [editedOtherData, setEditedOtherData] = useState<Array<{ column: any; value: any }>>(() => [...otherData])

    // Store callback in ref to prevent infinite loops
    const onDataChangeRef = useRef(onDataChange)
    onDataChangeRef.current = onDataChange

    // Track if initial sync is done to prevent triggering onDataChange during mount
    const isInitializedRef = useRef(false)

    const [selectedOtherColumns, setSelectedOtherColumns] = useState<Set<string>>(new Set())
    const [showOtherData, setShowOtherData] = useState(false)
    const [internalSelectedField, setInternalSelectedField] = useState<string | null>(null)

    // Derived state: Use controlled prop if available, otherwise internal
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
        // Skip the very first effect run to prevent loop during initial render
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

    const guideFieldCount = modelFields.length
    const filledFieldCount = isTableMode
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
                    </p>
                </div>
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

            {/* Content */}
            <div className="flex-1 overflow-auto">
                {/* Guide Extracted Section */}
                <div className="border-b border-border">
                    <div className="px-6 py-3 bg-primary/10 flex items-center gap-2">
                        <Sparkles className="w-4 h-4 text-primary" />
                        <span className="text-sm font-semibold text-foreground">
                            {Array.isArray(guideExtracted)
                                ? `테이블 추출 완료 (${(guideExtracted as any[]).length}행)`
                                : `참고정보 기반 추출 (${filledFieldCount}개 값)`
                            }
                        </span>
                    </div>

                    {/* TABLE MODE: render full editable table */}
                    {Array.isArray(guideExtracted) ? (
                        <div className="p-4">
                            <ResizableNestedTable
                                data={editedGuideData as any}
                                onUpdate={!readOnly ? (newData) => {
                                    setEditedGuideData(newData as any)
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
                                        const confidence = extractConfidence(rawData)
                                        const hasValue = value !== null && value !== '' && value !== undefined
                                        const isLowConfidence = confidence !== null && confidence < 0.9

                                        return (
                                            <tr
                                                key={field.key}
                                                className={clsx(
                                                    hasValue ? "bg-card" : "bg-chart-4/5",
                                                    isLowConfidence && "bg-chart-4/5",
                                                    selectedField === field.key && "ring-2 ring-primary bg-primary/5",
                                                    "cursor-pointer hover:bg-accent transition-colors"
                                                )}
                                                id={`field-row-${field.key}`}
                                                onClick={() => handleFieldClick(field.key)}
                                                onMouseEnter={() => {
                                                    if (controlledSelectedField === undefined) {
                                                        setInternalSelectedField(field.key)
                                                    }
                                                }}
                                            >
                                                <td className="px-6 py-4 align-top">
                                                    <div className="font-medium text-foreground">{field.label}</div>
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
                                                                        onChange={(newValue) => updateGuideField(field.key,
                                                                            rawData && typeof rawData === 'object' && 'confidence' in rawData
                                                                                ? { ...rawData, value: newValue }
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
                </div>

                {/* Other Data Section */}
                {otherData.length > 0 && (
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
                )}
            </div>
        </Card >
    )
}
