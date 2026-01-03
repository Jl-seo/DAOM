
import React from 'react'
import {
    useReactTable,
    getCoreRowModel,
    getSortedRowModel,
    flexRender,
    type ColumnDef,
    type SortingState,
} from '@tanstack/react-table'
import { Card } from '@/components/ui/card'
import { ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react'

// Example data structure for extracted fields
export interface ExtractedField {
    id: string
    field: string // e.g., "Invoice Number"
    value: string
    confidence: number
    status: 'review' | 'verified'
}

// Empty state will be shown in the table body when no data

interface ExtractionGridProps {
    data: any[] | Record<string, any>
    columns?: ColumnDef<any>[]
}

export function ExtractionGrid({ data: inputData, columns: externalColumns }: ExtractionGridProps) {
    const [sorting, setSorting] = React.useState<SortingState>([])

    // Map extracted JSON to table format
    const tableData = React.useMemo(() => {
        if (!inputData) return []

        // If array, use as is
        if (Array.isArray(inputData)) return inputData

        // Process rich format (Record)
        if (Object.values(inputData).some(v => typeof v === 'object' && v !== null && 'confidence' in v)) {
            return Object.entries(inputData).map(([key, item]: [string, any], index) => ({
                id: String(index),
                field: key,
                value: item.value || '',
                confidence: item.confidence,
                status: item.confidence > 0.8 ? 'verified' : 'review'
            }));
        }

        // Process legacy flat format (Record)
        return Object.entries(inputData).map(([key, value], index) => ({
            id: String(index),
            field: key,
            value: typeof value === 'object' ? JSON.stringify(value) : String(value),
            confidence: 0.95,
            status: 'review' as const
        }));
    }, [inputData]);

    // Update local state when prop changes
    const [gridData, setGridData] = React.useState(tableData);

    React.useEffect(() => {
        setGridData(tableData);
    }, [tableData]);


    const defaultColumns = React.useMemo<ColumnDef<ExtractedField>[]>(
        () => [
            {
                header: '컬럼명',
                accessorKey: 'field',
                cell: info => <span className="font-semibold text-foreground capitalize">{info.getValue() as string}</span>,
                enableSorting: true,
            },
            {
                header: '추출값',
                accessorKey: 'value',
                cell: ({ getValue, row }) => {
                    const initialValue = getValue() as string
                    const [value, setValue] = React.useState(initialValue)

                    React.useEffect(() => {
                        setValue(initialValue);
                    }, [initialValue]);

                    const onBlur = () => {
                        // In a real app, update data source here
                        console.log('Update', row.index, value)
                    }

                    return (
                        <input
                            value={value}
                            onChange={e => setValue(e.target.value)}
                            onBlur={onBlur}
                            className="w-full bg-transparent p-1 border-b border-transparent focus:border-primary focus:bg-card transition-colors outline-none"
                        />
                    )
                },
                enableSorting: true,
            },
            {
                header: '신뢰도',
                accessorKey: 'confidence',
                cell: info => {
                    const val = info.getValue() as number
                    const color = val > 0.9 ? 'text-chart-2' : val > 0.7 ? 'text-chart-4' : 'text-destructive'
                    return (
                        <div className="flex justify-center">
                            <span className={`text-xs font-mono ${color}`}>{(val * 100).toFixed(0)}%</span>
                        </div>
                    )
                },
                enableSorting: true,
                meta: {
                    align: 'center'
                }
            }
        ],
        []
    )

    const columns = externalColumns || defaultColumns as any

    const table = useReactTable({
        data: gridData,
        columns,
        getCoreRowModel: getCoreRowModel(),
        getSortedRowModel: getSortedRowModel(),
        onSortingChange: setSorting,
        columnResizeMode: 'onChange',
        state: {
            sorting,
        },
    } as any)

    return (
        <Card className="h-full flex flex-col overflow-hidden">
            <div className="px-4 py-3 border-b border-border bg-muted flex justify-between items-center">
                <h3 className="font-semibold text-foreground">추출 데이터</h3>
                <span className="text-xs px-2 py-1 bg-primary/10 text-primary rounded-full">{gridData.length}개 필드</span>
            </div>
            <div className="flex-1 overflow-auto">
                <table className="w-full text-sm text-left" style={{ width: table.getTotalSize() }}>
                    <thead className="text-xs uppercase bg-muted text-muted-foreground sticky top-0 z-10">
                        {table.getHeaderGroups().map(headerGroup => (
                            <tr key={headerGroup.id}>
                                {headerGroup.headers.map(header => (
                                    <th
                                        key={header.id}
                                        className="pl-6 pr-4 py-2 font-medium border-b border-border relative group select-none"
                                        style={{ width: header.getSize() }}
                                    >
                                        <div
                                            className={`flex items-center gap-1 ${header.column.columnDef.meta?.align === 'center' ? 'justify-center' : ''} ${header.column.getCanSort() ? 'cursor-pointer select-none hover:text-foreground' : ''}`}
                                            onClick={header.column.getToggleSortingHandler()}
                                        >
                                            {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                                            {{
                                                asc: <ArrowUp className="w-3 h-3 ml-1" />,
                                                desc: <ArrowDown className="w-3 h-3 ml-1" />,
                                            }[header.column.getIsSorted() as string] ?? (
                                                    header.column.getCanSort() ? <ArrowUpDown className="w-3 h-3 ml-1 opacity-0 group-hover:opacity-100 transition-opacity" /> : null
                                                )}
                                        </div>
                                        {/* Resize Handle */}
                                        <div
                                            onMouseDown={header.getResizeHandler()}
                                            onTouchStart={header.getResizeHandler()}
                                            className={`absolute right-0 top-0 h-full w-1 cursor-col-resize touch-none select-none bg-border/50 hover:bg-primary transition-colors ${header.column.getIsResizing() ? 'bg-primary w-1.5' : ''
                                                }`}
                                        />
                                    </th>
                                ))}
                            </tr>
                        ))}
                    </thead>
                    <tbody className="divide-y divide-border">
                        {table.getRowModel().rows.length === 0 ? (
                            <tr>
                                <td colSpan={columns.length} className="px-4 py-12 text-center">
                                    <div className="flex flex-col items-center justify-center text-muted-foreground">
                                        <div className="w-12 h-12 bg-muted rounded-full flex items-center justify-center mb-3">
                                            <svg className="w-6 h-6 text-muted-foreground/50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                            </svg>
                                        </div>
                                        <p className="font-medium text-foreground">추출된 데이터가 없습니다</p>
                                        <p className="text-sm">문서를 업로드하면 여기에 결과가 표시됩니다</p>
                                    </div>
                                </td>
                            </tr>
                        ) : (
                            table.getRowModel().rows.map(row => (
                                <tr key={row.id} className="hover:bg-accent transition-colors group">
                                    {row.getVisibleCells().map(cell => (
                                        <td key={cell.id} className="pl-6 pr-4 py-2 group-hover:text-foreground" style={{ width: cell.column.getSize() }}>
                                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                                        </td>
                                    ))}
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>
        </Card>
    )
}
