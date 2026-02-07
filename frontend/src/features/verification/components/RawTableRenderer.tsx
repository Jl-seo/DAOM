import { FileText } from 'lucide-react'

interface RawTableRendererProps {
    rawTables: any[]
}

/**
 * Get a cell property supporting both snake_case (backend) and camelCase formats.
 * Uses nullish coalescing to pick the first defined value.
 */
function cellProp(cell: any, camel: string, snake: string, fallback: number = 0): number {
    return cell[camel] ?? cell[snake] ?? fallback
}

/**
 * Shared raw table renderer component.
 * Renders Document Intelligence table data with snake_case/camelCase compatibility.
 * Used by PDFViewer (tables tab) and DocumentPreviewPanel (image/excel tables tab).
 */
export function RawTableRenderer({ rawTables }: RawTableRendererProps) {
    if (!rawTables || rawTables.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground p-8 text-center">
                <FileText className="w-12 h-12 mb-4 opacity-20" />
                <p>추출된 표가 없습니다.</p>
            </div>
        )
    }

    return (
        <div className="space-y-8 max-w-6xl mx-auto p-6">
            {rawTables.map((table: any, tableIndex: number) => {
                const tableRowCount = table.rowCount ?? table.row_count ?? 0
                const tableColCount = table.columnCount ?? table.column_count ?? 0
                const cells = table.cells

                // Calculate dimensions from cells if table-level counts are missing
                const maxRow = cells?.length > 0
                    ? cells.reduce((max: number, c: any) =>
                        Math.max(max, cellProp(c, 'rowIndex', 'row_index') + cellProp(c, 'rowSpan', 'row_span', 1)), 0)
                    : 0
                const maxCol = cells?.length > 0
                    ? cells.reduce((max: number, c: any) =>
                        Math.max(max, cellProp(c, 'columnIndex', 'column_index') + cellProp(c, 'columnSpan', 'column_span', 1)), 0)
                    : 0

                const rowCount = tableRowCount || maxRow
                const colCount = tableColCount || maxCol

                return (
                    <div key={tableIndex} className="border rounded-lg overflow-hidden">
                        <div className="bg-muted/50 px-4 py-2 text-sm font-medium border-b">
                            표 {tableIndex + 1}
                            {rowCount > 0 && colCount > 0 && (
                                <span className="text-muted-foreground ml-2">
                                    ({rowCount}행 × {colCount}열)
                                </span>
                            )}
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <tbody>
                                    {cells && rowCount > 0 && colCount > 0 && (() => {
                                        // Build grid
                                        const grid: any[][] = Array(rowCount)
                                            .fill(null)
                                            .map(() => Array(colCount).fill(null))

                                        cells.forEach((cell: any) => {
                                            const r = cellProp(cell, 'rowIndex', 'row_index')
                                            const c = cellProp(cell, 'columnIndex', 'column_index')
                                            if (r < rowCount && c < colCount) {
                                                grid[r][c] = cell
                                                // Mark spanned cells
                                                const rSpan = cellProp(cell, 'rowSpan', 'row_span', 1)
                                                const cSpan = cellProp(cell, 'columnSpan', 'column_span', 1)
                                                for (let i = 0; i < rSpan; i++) {
                                                    for (let j = 0; j < cSpan; j++) {
                                                        if (i === 0 && j === 0) continue
                                                        if (r + i < rowCount && c + j < colCount) {
                                                            grid[r + i][c + j] = { spanned: true }
                                                        }
                                                    }
                                                }
                                            }
                                        })

                                        return grid.map((row, rowIdx) => (
                                            <tr key={rowIdx} className={rowIdx === 0 ? 'bg-muted/30 font-medium' : 'border-t'}>
                                                {row.map((cell, colIdx) => {
                                                    if (!cell) return <td key={colIdx} className="border-r last:border-r-0 p-2"></td>
                                                    if (cell.spanned) return null
                                                    return (
                                                        <td
                                                            key={colIdx}
                                                            className="px-3 py-2 border-r last:border-r-0 align-top"
                                                            colSpan={cellProp(cell, 'columnSpan', 'column_span', 1)}
                                                            rowSpan={cellProp(cell, 'rowSpan', 'row_span', 1)}
                                                        >
                                                            {cell.content || ''}
                                                        </td>
                                                    )
                                                })}
                                            </tr>
                                        ))
                                    })()}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )
            })}
        </div>
    )
}
