/**
 * SortableDataTable - Reusable sortable data table using TanStack Table
 * 
 * Features:
 * - Column sorting (click header to sort)
 * - Optional search filtering
 * - Customizable columns
 */
import { useState } from 'react'
import {
    useReactTable,
    getCoreRowModel,
    getSortedRowModel,
    getFilteredRowModel,
    flexRender,
    type ColumnDef,
    type SortingState,
} from '@tanstack/react-table'
import { ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'

interface SortableDataTableProps<TData> {
    data: TData[]
    columns: ColumnDef<TData>[]
    searchValue?: string
    onRowClick?: (row: TData) => void
    className?: string
    emptyMessage?: string
}

export function SortableDataTable<TData>({
    data,
    columns,
    searchValue,
    onRowClick,
    className,
    emptyMessage = 'No data available',
}: SortableDataTableProps<TData>) {
    const [sorting, setSorting] = useState<SortingState>([])

    const table = useReactTable({
        data,
        columns,
        getCoreRowModel: getCoreRowModel(),
        getSortedRowModel: getSortedRowModel(),
        getFilteredRowModel: getFilteredRowModel(),
        state: {
            sorting,
            globalFilter: searchValue,
        },
        onSortingChange: setSorting,
    })

    return (
        <div className={cn('rounded-md border', className)}>
            <Table>
                <TableHeader>
                    {table.getHeaderGroups().map((headerGroup) => (
                        <TableRow key={headerGroup.id}>
                            {headerGroup.headers.map((header) => (
                                <TableHead key={header.id}>
                                    {header.isPlaceholder ? null : (
                                        <button
                                            className="flex items-center gap-1 hover:text-foreground transition-colors"
                                            onClick={header.column.getToggleSortingHandler()}
                                        >
                                            {flexRender(header.column.columnDef.header, header.getContext())}
                                            {{
                                                asc: <ArrowUp className="h-4 w-4" />,
                                                desc: <ArrowDown className="h-4 w-4" />,
                                            }[header.column.getIsSorted() as string] ?? (
                                                    <ArrowUpDown className="h-4 w-4 opacity-50" />
                                                )}
                                        </button>
                                    )}
                                </TableHead>
                            ))}
                        </TableRow>
                    ))}
                </TableHeader>
                <TableBody>
                    {table.getRowModel().rows?.length ? (
                        table.getRowModel().rows.map((row) => (
                            <TableRow
                                key={row.id}
                                onClick={() => onRowClick?.(row.original)}
                                className={onRowClick ? 'cursor-pointer hover:bg-muted/50' : ''}
                            >
                                {row.getVisibleCells().map((cell) => (
                                    <TableCell key={cell.id}>
                                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                                    </TableCell>
                                ))}
                            </TableRow>
                        ))
                    ) : (
                        <TableRow>
                            <TableCell colSpan={columns.length} className="h-24 text-center">
                                {emptyMessage}
                            </TableCell>
                        </TableRow>
                    )}
                </TableBody>
            </Table>
        </div>
    )
}

// Helper to create simple text columns with sorting
export function createSortableColumn<TData>(
    accessorKey: keyof TData & string,
    header: string
): ColumnDef<TData> {
    return {
        accessorKey,
        header,
    }
}
