/* eslint-disable @typescript-eslint/no-explicit-any */
'use client'

import { useState, useEffect, useRef, useMemo, forwardRef, useImperativeHandle } from 'react'
import { FileSpreadsheet } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Highlight } from '../types'

// Virtual OCR constants (must match backend ExcelMapper)
const VIRTUAL_WIDTH = 1000
const CELL_HEIGHT = 50

interface ExcelGridViewerProps {
    fileUrl: string
    highlights: Highlight[]
    activeFieldKey?: string
    onHighlightClick?: (key: string) => void
}

interface SheetData {
    name: string
    rows: string[][]
    rowCount: number
    colCount: number
}

export interface ExcelGridViewerHandle {
    scrollToHighlight: (fieldKey: string) => void
}

/**
 * Convert bbox polygon to row/col indices.
 * Backend ExcelMapper uses: x = col * (1000 / col_count), y = row * 50
 */
function bboxToCell(bbox: number[], colCount: number): { row: number; col: number } | null {
    if (!bbox || bbox.length < 4) return null

    // bbox is [x1, y1, x2, y2] or polygon [x1,y1,x2,y1,x2,y2,x1,y2]
    const x1 = bbox[0]
    const y1 = bbox[1]

    const cellWidth = VIRTUAL_WIDTH / colCount
    const col = Math.floor(x1 / cellWidth)
    const row = Math.floor(y1 / CELL_HEIGHT)

    return { row, col }
}

export const ExcelGridViewer = forwardRef<ExcelGridViewerHandle, ExcelGridViewerProps>(({
    fileUrl,
    highlights,
    activeFieldKey,
    onHighlightClick
}, ref) => {
    const [sheets, setSheets] = useState<SheetData[]>([])
    const [activeSheetIndex, setActiveSheetIndex] = useState(0)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const tableRef = useRef<HTMLTableElement>(null)
    const cellRefs = useRef<Map<string, HTMLTableCellElement>>(new Map())

    // Fetch and parse Excel data
    useEffect(() => {
        if (!fileUrl) return

        const fetchExcelData = async () => {
            setLoading(true)
            setError(null)

            try {
                // For now, we'll parse Excel client-side using SheetJS
                // In production, this should come from backend API
                const response = await fetch(fileUrl)
                const arrayBuffer = await response.arrayBuffer()

                // Dynamic import of xlsx library
                const XLSX = await import('xlsx')
                const workbook = XLSX.read(arrayBuffer, { type: 'array' })

                const parsedSheets: SheetData[] = workbook.SheetNames.map((name) => {
                    const sheet = workbook.Sheets[name]
                    const jsonData = XLSX.utils.sheet_to_json<string[]>(sheet, { header: 1 })

                    const rows = jsonData.map(row =>
                        Array.isArray(row) ? row.map(cell => String(cell ?? '')) : []
                    )

                    const rowCount = rows.length
                    const colCount = Math.max(...rows.map(r => r.length), 0)

                    // Normalize row lengths
                    const normalizedRows = rows.map(row => {
                        const padded = [...row]
                        while (padded.length < colCount) padded.push('')
                        return padded
                    })

                    return { name, rows: normalizedRows, rowCount, colCount }
                })

                setSheets(parsedSheets)
            } catch (e: any) {
                console.error('[ExcelGridViewer] Failed to load Excel:', e)
                setError(e?.message || 'Failed to load Excel file')
            } finally {
                setLoading(false)
            }
        }

        fetchExcelData()
    }, [fileUrl])

    // Current sheet data
    const currentSheet = sheets[activeSheetIndex]

    // Compute highlighted cells for current sheet
    const highlightedCells = useMemo(() => {
        if (!currentSheet || !highlights.length) return new Map<string, Highlight>()

        const cellMap = new Map<string, Highlight>()

        highlights.forEach(h => {
            // Check if highlight belongs to this sheet (page)
            // pageIndex is 0-based, page_number from backend is 1-based
            if (h.pageIndex !== activeSheetIndex) return

            // Convert bbox to cell coordinates
            const bbox = h.position?.boundingRect
            if (bbox) {
                const cellCoords = bboxToCell(
                    [bbox.x1, bbox.y1, bbox.x2, bbox.y2],
                    currentSheet.colCount
                )
                if (cellCoords) {
                    const key = `${cellCoords.row}-${cellCoords.col}`
                    cellMap.set(key, h)
                }
            }
        })

        return cellMap
    }, [currentSheet, highlights, activeSheetIndex])

    // Expose scroll method
    useImperativeHandle(ref, () => ({
        scrollToHighlight: (fieldKey: string) => {
            const highlight = highlights.find(h => h.fieldKey === fieldKey)
            if (!highlight) return

            // Switch to correct sheet if needed
            if (highlight.pageIndex !== activeSheetIndex) {
                setActiveSheetIndex(highlight.pageIndex)
            }

            // Find cell ref and scroll
            const bbox = highlight.position?.boundingRect
            if (bbox && currentSheet) {
                const cellCoords = bboxToCell(
                    [bbox.x1, bbox.y1, bbox.x2, bbox.y2],
                    currentSheet.colCount
                )
                if (cellCoords) {
                    const cellKey = `${cellCoords.row}-${cellCoords.col}`
                    const cellEl = cellRefs.current.get(cellKey)
                    cellEl?.scrollIntoView({ behavior: 'smooth', block: 'center' })
                }
            }
        }
    }), [highlights, activeSheetIndex, currentSheet])

    // Auto-scroll when activeFieldKey changes
    useEffect(() => {
        if (activeFieldKey) {
            const highlight = highlights.find(h => h.fieldKey === activeFieldKey)
            if (highlight && highlight.pageIndex !== activeSheetIndex) {
                setActiveSheetIndex(highlight.pageIndex)
            }
        }
    }, [activeFieldKey, highlights, activeSheetIndex])

    if (loading) {
        return (
            <div className="h-full flex items-center justify-center bg-muted/20">
                <div className="text-center space-y-2">
                    <FileSpreadsheet className="w-10 h-10 mx-auto text-muted-foreground animate-pulse" />
                    <p className="text-sm text-muted-foreground">Loading Excel...</p>
                </div>
            </div>
        )
    }

    if (error || !sheets.length) {
        return (
            <div className="h-full flex items-center justify-center bg-muted/20">
                <div className="text-center space-y-2">
                    <FileSpreadsheet className="w-10 h-10 mx-auto text-destructive/50" />
                    <p className="text-sm text-destructive">{error || 'No data found'}</p>
                </div>
            </div>
        )
    }

    return (
        <div className="h-full flex flex-col overflow-hidden">
            {/* Sheet Tabs */}
            {sheets.length > 1 && (
                <div className="flex items-center gap-1 px-2 py-1 bg-muted/30 border-b overflow-x-auto shrink-0">
                    {sheets.map((sheet, idx) => (
                        <button
                            key={sheet.name}
                            onClick={() => setActiveSheetIndex(idx)}
                            className={cn(
                                "px-3 py-1 text-xs font-medium rounded-t transition-colors whitespace-nowrap",
                                idx === activeSheetIndex
                                    ? "bg-background text-primary border-b-2 border-primary"
                                    : "text-muted-foreground hover:bg-background/50"
                            )}
                        >
                            {sheet.name}
                        </button>
                    ))}
                </div>
            )}

            {/* Grid Table */}
            <div className="flex-1 overflow-auto">
                {currentSheet && (
                    <table
                        ref={tableRef}
                        className="w-full border-collapse text-xs"
                    >
                        <tbody>
                            {currentSheet.rows.map((row, rowIdx) => (
                                <tr key={rowIdx} className={rowIdx === 0 ? "bg-muted/50 font-medium" : ""}>
                                    {/* Row number */}
                                    <td className="px-2 py-1 border bg-muted/30 text-muted-foreground text-center w-10 sticky left-0">
                                        {rowIdx + 1}
                                    </td>
                                    {row.map((cell, colIdx) => {
                                        const cellKey = `${rowIdx}-${colIdx}`
                                        const highlight = highlightedCells.get(cellKey)
                                        const isActive = highlight?.fieldKey === activeFieldKey

                                        return (
                                            <td
                                                key={colIdx}
                                                ref={(el) => {
                                                    if (el) cellRefs.current.set(cellKey, el)
                                                }}
                                                onClick={() => highlight && onHighlightClick?.(highlight.fieldKey)}
                                                className={cn(
                                                    "px-2 py-1 border min-w-[80px] max-w-[200px] truncate transition-colors",
                                                    highlight && "bg-yellow-100 dark:bg-yellow-900/30 cursor-pointer hover:bg-yellow-200 dark:hover:bg-yellow-800/50",
                                                    isActive && "ring-2 ring-primary ring-inset bg-yellow-200 dark:bg-yellow-800/50"
                                                )}
                                                title={cell}
                                            >
                                                {cell}
                                            </td>
                                        )
                                    })}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            {/* Footer Info */}
            <div className="px-3 py-1 bg-muted/30 border-t text-xs text-muted-foreground flex justify-between shrink-0">
                <span>{currentSheet?.rowCount ?? 0} rows × {currentSheet?.colCount ?? 0} cols</span>
                <span>Sheet {activeSheetIndex + 1} of {sheets.length}</span>
            </div>
        </div>
    )
})

ExcelGridViewer.displayName = 'ExcelGridViewer'
