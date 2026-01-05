import React from 'react'
import {
    useReactTable,
    getCoreRowModel,
    getSortedRowModel,
    flexRender,
    type ColumnDef,
    type SortingState,
} from '@tanstack/react-table'
import {
    Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from "@/components/ui/table"
import { Checkbox } from "@/components/ui/checkbox"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
    MoreHorizontal, FileText, CheckCircle2, AlertCircle,
    Download, RefreshCw, Eye, ArrowUpDown, ArrowUp, ArrowDown
} from "lucide-react"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { format } from 'date-fns'
import { ko } from 'date-fns/locale'
import type { ExtractionLog } from '../../verification/types'
import { isSuccessStatus, isProcessingStatus } from '../../verification/constants/status'

interface ExtractionLogTableProps {
    logs: ExtractionLog[]
    showModelColumn?: boolean
    enableSelection?: boolean
    selectedIds?: Set<string>
    onSelect?: (id: string, selected: boolean) => void
    onSelectAll?: (selected: boolean) => void
    onView?: (log: ExtractionLog) => void
    onDownload?: (log: ExtractionLog) => void
    onRetry?: (log: ExtractionLog) => void
    onDelete?: (log: ExtractionLog) => void
    onCancel?: (log: ExtractionLog) => void
}

export function ExtractionLogTable({
    logs,
    showModelColumn = false,
    enableSelection = false,
    selectedIds = new Set(),
    onSelect,
    onSelectAll,
    onView,
    onDownload,
    onRetry,
    onDelete,
    onCancel
}: ExtractionLogTableProps) {
    const [sorting, setSorting] = React.useState<SortingState>([])

    const formatDate = (dateString: string) => {
        try {
            return format(new Date(dateString), 'yy.MM.dd HH:mm', { locale: ko })
        } catch (e) {
            return dateString
        }
    }

    const getUserDisplayName = (log: ExtractionLog) => {
        if (log.user_name) return log.user_name
        return log.user_id === 'unknown' ? '알 수 없음' : log.user_id.substring(0, 8)
    }

    const columns = React.useMemo<ColumnDef<ExtractionLog>[]>(() => {
        const cols: ColumnDef<ExtractionLog>[] = []

        // Selection Column
        if (enableSelection) {
            cols.push({
                id: 'select',
                header: ({ table }) => (
                    <Checkbox
                        checked={table.getIsAllPageRowsSelected()}
                        onCheckedChange={(checked) => onSelectAll?.(!!checked)}
                    />
                ),
                cell: ({ row }) => (
                    <div onClick={(e) => e.stopPropagation()}>
                        <Checkbox
                            checked={selectedIds.has(row.original.id)}
                            onCheckedChange={(checked) => onSelect?.(row.original.id, !!checked)}
                        />
                    </div>
                ),
                size: 40,
                enableSorting: false,
            })
        }

        // Status Column
        cols.push({
            accessorKey: 'status',
            header: '상태',
            meta: { align: 'center' },
            cell: ({ getValue }) => {
                const status = getValue() as string
                if (isSuccessStatus(status)) {
                    return (
                        <div className="flex items-center justify-center w-8 h-8 rounded-full bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400">
                            <CheckCircle2 className="w-4 h-4" />
                        </div>
                    )
                }
                if (isProcessingStatus(status)) {
                    return (
                        <div className="flex items-center justify-center w-8 h-8 rounded-full bg-chart-4/10 text-chart-4 dark:bg-chart-4/30">
                            <RefreshCw className="w-4 h-4 animate-spin" />
                        </div>
                    )
                }
                return (
                    <div className="flex items-center justify-center w-8 h-8 rounded-full bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400">
                        <AlertCircle className="w-4 h-4" />
                    </div>
                )
            },
            size: 50,
        })

        // Model Column
        if (showModelColumn) {
            cols.push({
                accessorKey: 'model_name', // fallback to model_id if needed in cell
                header: '모델',
                cell: ({ row }) => (
                    <Badge variant="outline" className="font-normal bg-background">
                        {row.original.model_name || row.original.model_id}
                    </Badge>
                ),
                size: 150,
            })
        }

        // Filename Column
        cols.push({
            accessorKey: 'filename',
            header: '파일명',
            cell: ({ row }) => (
                <div>
                    <div className="flex items-center gap-2">
                        <FileText className="w-4 h-4 text-muted-foreground" />
                        <span className="font-medium text-foreground truncate max-w-[300px]" title={row.original.filename}>
                            {row.original.filename}
                        </span>
                    </div>
                    {row.original.error && (
                        <p className="text-xs text-destructive mt-1 truncate max-w-[300px]">
                            {row.original.error}
                        </p>
                    )}
                </div>
            ),
        })

        // User Column
        cols.push({
            accessorKey: 'user_id',
            header: '담당자',
            cell: ({ row }) => (
                <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center text-[10px] font-bold text-primary">
                        {getUserDisplayName(row.original)[0]}
                    </div>
                    <span className="text-sm text-foreground">{getUserDisplayName(row.original)}</span>
                </div>
            ),
            size: 120,
        })

        // Created At
        cols.push({
            accessorKey: 'created_at',
            header: '생성일시',
            cell: ({ getValue }) => <span className="text-muted-foreground text-sm">{formatDate(getValue() as string)}</span>,
            size: 130,
        })

        // Updated At
        cols.push({
            accessorKey: 'updated_at',
            header: '수정일시',
            cell: ({ row }) => {
                const updated = row.original.updated_at
                const created = row.original.created_at
                return <span className="text-muted-foreground text-sm">
                    {updated && updated !== created ? formatDate(updated) : '-'}
                </span>
            },
            size: 130,
        })

        // Actions
        cols.push({
            id: 'actions',
            header: () => <div className="text-right">작업</div>,
            cell: ({ row }) => (
                <div className="text-right" onClick={(e) => e.stopPropagation()}>
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8 hover:bg-muted">
                                <MoreHorizontal className="w-4 h-4" />
                                <span className="sr-only">메뉴 열기</span>
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-[160px]">
                            <DropdownMenuLabel>작업</DropdownMenuLabel>
                            {isSuccessStatus(row.original.status) && onView && (
                                <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onView(row.original); }}>
                                    <Eye className="w-4 h-4 mr-2" />
                                    상세 보기
                                </DropdownMenuItem>
                            )}
                            {isSuccessStatus(row.original.status) && onDownload && (
                                <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onDownload(row.original); }}>
                                    <Download className="w-4 h-4 mr-2" />
                                    Excel 다운로드
                                </DropdownMenuItem>
                            )}
                            <DropdownMenuSeparator />
                            {onRetry && (
                                <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onRetry(row.original); }}>
                                    <RefreshCw className="w-4 h-4 mr-2" />
                                    다시 추출
                                </DropdownMenuItem>
                            )}
                            {/* Cancel Option for Processing Jobs */}
                            {isProcessingStatus(row.original.status) && onCancel && (
                                <DropdownMenuItem
                                    onClick={(e) => { e.stopPropagation(); onCancel(row.original); }}
                                    className="text-destructive focus:text-destructive"
                                >
                                    <AlertCircle className="w-4 h-4 mr-2" />
                                    작업 취소
                                </DropdownMenuItem>
                            )}
                            {/* Delete Option for Non-Processing Jobs */}
                            {!isProcessingStatus(row.original.status) && onDelete && (
                                <>
                                    <DropdownMenuSeparator />
                                    <DropdownMenuItem
                                        onClick={(e) => { e.stopPropagation(); onDelete(row.original); }}
                                        className="text-destructive focus:text-destructive"
                                    >
                                        <AlertCircle className="w-4 h-4 mr-2" />
                                        기록 삭제
                                    </DropdownMenuItem>
                                </>
                            )}
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>
            ),
            size: 80,
            enableSorting: false,
        })

        return cols
    }, [enableSelection, selectedIds, showModelColumn, onSelect, onSelectAll, onView, onDownload, onRetry, onDelete, onCancel])

    const table = useReactTable({
        data: logs,
        columns,
        getCoreRowModel: getCoreRowModel(),
        getSortedRowModel: getSortedRowModel(),
        onSortingChange: setSorting,
        state: {
            sorting,
        },
    })

    return (
        <div className="rounded-md border border-border">
            <Table>
                <TableHeader>
                    {table.getHeaderGroups().map(headerGroup => (
                        <TableRow key={headerGroup.id} className="bg-muted/50 hover:bg-muted/50">
                            {headerGroup.headers.map(header => (
                                <TableHead key={header.id} style={{ width: header.getSize() }} className="pl-6 pr-4">
                                    {header.isPlaceholder ? null : (
                                        <div
                                            className={`flex items-center gap-1 ${header.column.columnDef.meta?.align === 'center' ? 'justify-center' : ''} ${header.column.getCanSort() ? 'cursor-pointer select-none hover:text-foreground' : ''}`}
                                            onClick={header.column.getToggleSortingHandler()}
                                        >
                                            {flexRender(header.column.columnDef.header, header.getContext())}
                                            {{
                                                asc: <ArrowUp className="w-3 h-3 ml-1" />,
                                                desc: <ArrowDown className="w-3 h-3 ml-1" />,
                                            }[header.column.getIsSorted() as string] ?? (
                                                    header.column.getCanSort() ? <ArrowUpDown className="w-3 h-3.5 ml-1 opacity-0 group-hover:opacity-100" /> : null
                                                )}
                                        </div>
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
                                data-state={row.getIsSelected() && "selected"}
                                className={onView ? 'cursor-pointer hover:bg-muted/30' : ''}
                                onClick={() => onView && onView(row.original)}
                            >
                                {row.getVisibleCells().map((cell) => (
                                    <TableCell key={cell.id} className="pl-6 pr-4">
                                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                                    </TableCell>
                                ))}
                            </TableRow>
                        ))
                    ) : (
                        <TableRow>
                            <TableCell colSpan={columns.length} className="h-24 text-center text-muted-foreground">
                                추출 기록이 없습니다
                            </TableCell>
                        </TableRow>
                    )}
                </TableBody>
            </Table>
        </div>
    )
}
