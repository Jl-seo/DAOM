import { useState, useEffect, useRef } from 'react'
import { Check, ChevronDown, ChevronUp, ChevronRight, Sparkles, Database, Plus, Edit2, Save } from 'lucide-react'
import { clsx } from 'clsx'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'

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
    // First unwrap if it's a rich object with .value
    const unwrapped = extractValue(value)
    if (typeof unwrapped === 'object') return JSON.stringify(unwrapped, null, 2)
    return String(unwrapped)
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
    const [columnWidths, setColumnWidths] = useState<Record<string, number>>({})
    const [resizingColumn, setResizingColumn] = useState<string | null>(null)
    const tableRef = useRef<HTMLDivElement>(null)

    if (!Array.isArray(data) || data.length === 0) {
        return <span className="text-muted-foreground italic text-xs">빈 배열</span>
    }

    const allKeys = Array.from(new Set(data.flatMap(item =>
        typeof item === 'object' && item !== null ? Object.keys(item) : []
    )))

    // Initialize column widths - only runs once when data changes and widths are empty
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
    }, [data.length, columnWidths]) // Use data.length instead of allKeys array

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

    // Collapsed view: show summary
    if (!isExpanded) {
        return (
            <button
                onClick={onToggleExpand}
                className="flex items-center gap-2 px-3 py-2 bg-muted/50 hover:bg-muted rounded-lg text-sm text-muted-foreground hover:text-foreground transition-colors w-full text-left"
            >
                <ChevronRight className="w-4 h-4" />
                <span className="font-medium">테이블 ({data.length}행 × {allKeys.length}열)</span>
                <span className="text-xs">클릭하여 펼치기</span>
            </button>
        )
    }

    return (
        <div ref={tableRef} className="border border-border rounded-lg overflow-hidden">
            {/* Collapse button */}
            {onToggleExpand && (
                <button
                    onClick={onToggleExpand}
                    className="w-full flex items-center gap-2 px-3 py-1.5 bg-muted/50 hover:bg-muted text-xs text-muted-foreground hover:text-foreground transition-colors border-b border-border"
                >
                    <ChevronDown className="w-3 h-3" />
                    <span>테이블 접기 ({data.length}행)</span>
                </button>
            )}

            {/* Scrollable table container */}
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
                                    <div className="px-3 py-2 truncate">{key}</div>
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
                    <tbody className="divide-y divide-border">
                        {data.map((row, rowIdx) => (
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
                                        {onUpdate ? (
                                            <input
                                                type="text"
                                                className="w-full bg-transparent border-b border-transparent hover:border-border focus:border-primary outline-none px-3 py-2"
                                                value={renderValue(row?.[key] ?? '')}
                                                onChange={(e) => {
                                                    const newData = [...data]
                                                    if (typeof newData[rowIdx] === 'object') {
                                                        newData[rowIdx] = { ...newData[rowIdx], [key]: e.target.value }
                                                    }
                                                    onUpdate(newData)
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
        return (
            <div className="space-y-1">
                <pre className="text-xs bg-muted p-2 rounded overflow-auto max-h-32">
                    {JSON.stringify(parsedValue, null, 2)}
                </pre>
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
    const [editedGuideData, setEditedGuideData] = useState<Record<string, any>>(() => ({ ...guideExtracted }))
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
    const filledFieldCount = Object.values(editedGuideData).filter(v => v !== null && v !== '' && v !== undefined).length

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
                            process.env.NODE_ENV === 'development' && console.log('[SaveButton] Clicked')
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
                            참고정보 기반 추출 ({filledFieldCount}개 값)
                        </span>
                    </div>
                    <table className="w-full text-sm table-fixed">
                        <thead>
                            <tr className="bg-muted text-xs uppercase text-muted-foreground">
                                <th className="px-6 py-3 text-left font-semibold w-[200px]">필드명</th>
                                <th className="px-6 py-3 text-left font-semibold">추출값 (편집 가능)</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                            {modelFields.map(field => {
                                const rawData = editedGuideData[field.key]
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
