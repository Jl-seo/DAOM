import { useState, useMemo } from 'react'
import { useExtraction } from '../../verification/context/ExtractionContext'
import { useAuth } from '@/auth'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
    CalendarRegular,
    ArrowDownloadRegular,
    CheckmarkCircleRegular,
    WarningRegular,
    ClockRegular,
    SearchRegular,
    DismissRegular,
    EyeRegular,
    DocumentSearchRegular,
    ArrowClockwiseRegular,
    DocumentRegular
} from '@fluentui/react-icons'
import { apiClient } from '../../../lib/api'
import { downloadAsExcel } from '../../../utils/excel'
import { toast } from 'sonner'
import { ExtractionDataViewer } from './ExtractionDataViewer'
import { ExtractionLogTable } from './ExtractionLogTable'
import type { ExtractionLog } from '../../verification/types'
import { StatsDashboard } from '@/components/StatsDashboard'
import { EmptyState } from '@/components/EmptyState'
import { DateRangePicker } from '@/components/DateRangePicker'
import { StatusFilter, type StatusFilterValue } from '@/components/StatusFilter'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { isSuccessStatus, isErrorStatus, isProcessingStatus, isReviewNeededStatus, STATUS_LABELS } from '../../verification/constants/status'

type DatePreset = 'all' | 'today' | 'week' | 'month'

interface ExtractionHistoryProps {
    modelId: string
    onSelectRecord?: (log: ExtractionLog, editMode: boolean) => void
    onNewExtraction?: () => void
    embedded?: boolean
}

export function ExtractionHistory({ modelId, onSelectRecord, onNewExtraction, embedded = false }: ExtractionHistoryProps) {
    const [searchTerm, setSearchTerm] = useState('')
    const [statusFilter, setStatusFilter] = useState<StatusFilterValue>('all')
    const [dateFilter, setDateFilter] = useState<DatePreset>('all')
    const [ownershipTab, setOwnershipTab] = useState<'my' | 'group'>('my')
    const [selectedLog, setSelectedLog] = useState<ExtractionLog | null>(null)
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

    const { resumeJob } = useExtraction()
    const { user } = useAuth()
    const queryClient = useQueryClient()

    const { data: logs = [], isLoading, error } = useQuery({
        queryKey: ['extraction-logs', modelId],
        queryFn: async () => {
            const res = await apiClient.get(`/extraction/logs`, {
                params: { model_id: modelId, limit: 100 }
            })
            return res.data as ExtractionLog[]
        },
        refetchInterval: (query) => {
            const data = query.state.data
            if (!data) return 5000
            // Poll frequently (3s) if there are active jobs, otherwise slowly (30s)
            const hasActiveJobs = data.some(log => isProcessingStatus(log.status))
            return hasActiveJobs ? 3000 : 30000
        },
        staleTime: 1000 // Keep data fresh but allow immediate refetch if needed
    })

    const isWithinDateRange = (dateStr: string): boolean => {
        if (dateFilter === 'all') return true

        const logDate = new Date(dateStr)
        const now = new Date()

        switch (dateFilter) {
            case 'today': {
                const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
                const logDay = new Date(logDate.getFullYear(), logDate.getMonth(), logDate.getDate())
                return logDay.getTime() === today.getTime()
            }
            case 'week': {
                const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
                return logDate >= weekAgo
            }
            case 'month': {
                const monthAgo = new Date(now.getFullYear(), now.getMonth() - 1, now.getDate())
                return logDate >= monthAgo
            }
            default:
                return true
        }
    }
    const filteredLogs = logs.filter(log => {
        const matchesSearch = log.filename.toLowerCase().includes(searchTerm.toLowerCase())

        // Status filter: Robust switch-based filtering
        let matchesStatus = false
        switch (statusFilter) {
            case 'all':
                matchesStatus = true
                break
            case 'success':
                matchesStatus = isSuccessStatus(log.status)
                break
            case 'processing':
                matchesStatus = isProcessingStatus(log.status) && !isReviewNeededStatus(log.status)
                break
            case 'draft':
                matchesStatus = isReviewNeededStatus(log.status)
                break
            case 'error':
                matchesStatus = isErrorStatus(log.status)
                break
            default:
                matchesStatus = true
        }

        const matchesDate = isWithinDateRange(log.created_at)

        // Ownership filter
        // If 'my', check if log.user_id matches current user's localAccountId or oid
        let matchesOwner = true
        if (ownershipTab === 'my' && user) {
            matchesOwner = log.user_id === user.localAccountId ||
                log.user_id === user.homeAccountId ||
                log.user_email === user.username
        }

        return matchesSearch && matchesStatus && matchesDate && matchesOwner
    })

    const stats = useMemo(() => {
        const today = new Date()
        today.setHours(0, 0, 0, 0)

        // Strict counting using new helpers
        return {
            total: filteredLogs.length,
            success: filteredLogs.filter(l => isSuccessStatus(l.status)).length,
            processing: filteredLogs.filter(l => isProcessingStatus(l.status)).length,
            error: filteredLogs.filter(l => isErrorStatus(l.status)).length,
            today: filteredLogs.filter(l => {
                const logDate = new Date(l.created_at)
                logDate.setHours(0, 0, 0, 0)
                return logDate.getTime() === today.getTime()
            }).length
        }
    }, [filteredLogs])

    const handleDownload = (log: ExtractionLog) => {
        if (!log.extracted_data) {
            toast.error('추출 데이터가 없습니다')
            return
        }
        downloadAsExcel(
            [{ filename: log.filename, ...log.extracted_data }],
            `${log.filename}_${new Date(log.created_at).toLocaleDateString()}`
        )
        toast.success('Excel 다운로드!')
    }

    const handleRetry = async (log: ExtractionLog) => {
        try {
            await apiClient.post(`/extraction/retry/${log.id}`)
            toast.success('재시도 작업이 시작되었습니다.')
            // Force immediate refetch from DB, not cache
            await queryClient.invalidateQueries({ queryKey: ['extraction-logs', modelId] })
        } catch {
            toast.error('재시도 요청 실패')
        }
    }

    const toggleSelect = (id: string) => {
        setSelectedIds(prev => {
            const newSet = new Set(prev)
            if (newSet.has(id)) {
                newSet.delete(id)
            } else {
                newSet.add(id)
            }
            return newSet
        })
    }

    const selectAll = () => {
        const allIds = filteredLogs.map(log => log.id)
        setSelectedIds(new Set(allIds))
    }

    const clearSelection = () => {
        setSelectedIds(new Set())
    }

    const handleBulkDownload = () => {
        const selectedLogs = filteredLogs.filter(log => selectedIds.has(log.id) && isSuccessStatus(log.status))
        if (selectedLogs.length === 0) {
            toast.error('다운로드할 성공 기록이 없습니다')
            return
        }

        const allData = selectedLogs.map(log => ({
            filename: log.filename,
            ...(log.extracted_data || {})
        }))

        downloadAsExcel(allData, `bulk_download_${new Date().toLocaleDateString()}`)
        toast.success(`${selectedLogs.length}개 파일 다운로드 완료!`)
        clearSelection()
    }

    const formatDate = (isoString: string) => {
        const date = new Date(isoString)
        return date.toLocaleString('ko-KR', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        })
    }

    const handleRowClick = async (log: ExtractionLog, editMode: boolean = false) => {
        if (isProcessingStatus(log.status)) {
            // Fetch the latest job for this log from the API
            try {
                const res = await apiClient.get(`/extraction/log/${log.id}/job`)
                const { job_id, file_url } = res.data
                resumeJob(job_id, file_url, log.status as any)
            } catch {
                toast.error('진행 중인 작업을 찾을 수 없습니다. 재시도 버튼을 사용해 주세요.')
            }
            return
        }

        if (onSelectRecord) {
            onSelectRecord(log, editMode)
        } else {
            setSelectedLog(log)
        }
    }

    // Embedded mode - compact table with filters
    if (embedded) {
        return (
            <div className="h-full flex flex-col">
                {/* Stats Dashboard */}
                <div className="p-4 bg-muted">
                    <StatsDashboard stats={stats} />
                </div>

                {/* Filter toolbar */}
                {/* Modern Filter Toolbar */}
                <div className="px-6 py-4 border-b border-border bg-card flex flex-col xl:flex-row items-start xl:items-center gap-4 justify-between sticky top-0 z-20 shadow-sm">
                    {/* Left: Search & Ownership */}
                    <div className="flex flex-1 items-center gap-3 w-full xl:w-auto">
                        <div className="relative flex-1 max-w-md">
                            <SearchRegular className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                            <Input
                                type="text"
                                placeholder="파일명으로 검색..."
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                                className="pl-10 bg-muted/50 border-transparent focus:bg-background focus:border-primary transition-all rounded-full"
                            />
                        </div>
                        <div className="h-8 w-px bg-border mx-2 hidden xl:block" />
                        <div className="flex bg-muted rounded-full p-1">
                            <button
                                onClick={() => setOwnershipTab('my')}
                                className={`px-4 py-1 rounded-full text-xs font-semibold transition-all ${ownershipTab === 'my' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
                            >
                                내 기록
                            </button>
                            <button
                                onClick={() => setOwnershipTab('group')}
                                className={`px-4 py-1 rounded-full text-xs font-semibold transition-all ${ownershipTab === 'group' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
                            >
                                팀 전체
                            </button>
                        </div>
                    </div>

                    {/* Right: Filters & Actions */}
                    <div className="flex items-center gap-3 w-full xl:w-auto justify-end">
                        <div className="flex items-center gap-2">
                            <StatusFilter value={statusFilter} onChange={setStatusFilter} />
                            <DateRangePicker value={dateFilter} onChange={setDateFilter} />
                        </div>


                    </div>
                </div>

                {/* Records count + New Extraction button */}


                {/* Table content */}
                <Card className="flex-1 overflow-auto mx-4 mb-4 border-none shadow-none bg-transparent">
                    {isLoading && (
                        <div className="flex items-center justify-center py-8">
                            <ClockRegular className="w-8 h-8 animate-pulse text-primary" />
                        </div>
                    )}
                    {error && (
                        <div className="flex items-center justify-center py-8 text-destructive">
                            <WarningRegular className="w-8 h-8 mr-2" />
                            <span>데이터를 불러올 수 없습니다</span>
                        </div>
                    )}
                    {!isLoading && !error && filteredLogs.length === 0 && (
                        <EmptyState
                            icon={DocumentSearchRegular}
                            title={searchTerm || statusFilter !== 'all' ? "검색 결과가 없습니다" : "아직 추출된 문서가 없습니다"}
                            description={searchTerm || statusFilter !== 'all' ? "다른 필터 조건을 시도해보세요" : "첫 문서를 업로드하여 추출을 시작해보세요"}
                            action={onNewExtraction ? {
                                label: "새 문서 추출하기",
                                onClick: onNewExtraction
                            } : undefined}
                        />
                    )}

                    {/* Bulk Action Toolbar */}
                    {selectedIds.size > 0 && (
                        <div className="flex items-center justify-between px-4 py-3 bg-primary/10 border-b border-primary/20 mb-2 rounded-lg">
                            <div className="flex items-center gap-3">
                                <span className="text-sm font-medium text-primary">
                                    {selectedIds.size}개 선택됨
                                </span>
                                <Button onClick={handleBulkDownload} size="sm" className="bg-chart-2 hover:bg-chart-2/90 h-8">
                                    <ArrowDownloadRegular className="w-4 h-4 mr-1.5" />
                                    일괄 다운로드
                                </Button>
                            </div>
                            <Button onClick={clearSelection} variant="ghost" size="sm" className="h-8">
                                선택 해제
                            </Button>
                        </div>
                    )}

                    {!isLoading && !error && filteredLogs.length > 0 && (
                        <ExtractionLogTable
                            logs={filteredLogs}
                            showModelColumn={false}
                            enableSelection={true}
                            selectedIds={selectedIds}
                            onSelect={(id) => toggleSelect(id)}
                            onSelectAll={(checked) => checked ? selectAll() : clearSelection()}
                            onView={(log) => handleRowClick(log, false)}
                            onDownload={handleDownload}
                            onRetry={handleRetry}
                        />
                    )}
                </Card>
            </div>
        )
    }

    // Full page mode
    return (
        <div className="flex-1 flex flex-col bg-muted" >
            {/* Header */}
            < Card className="mx-6 mt-6 rounded-b-none" >
                <div className="px-8 py-6">
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-3">
                            <div className="w-12 h-12 bg-chart-1/10 rounded-xl flex items-center justify-center">
                                <ClockRegular className="w-6 h-6 text-chart-1" />
                            </div>
                            <div>
                                <h1 className="text-2xl font-bold text-foreground">추출 기록</h1>
                                <p className="text-sm text-muted-foreground">총 {filteredLogs.length}개 기록</p>
                            </div>
                        </div>
                    </div>
                    {/* Filters */}
                    <div className="flex gap-4">
                        <div className="flex-1 relative">
                            <SearchRegular className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                            <Input
                                type="text"
                                placeholder="파일명 검색..."
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                                className="pl-10"
                            />
                        </div>
                        <div className="flex gap-2">
                            <Button
                                variant={statusFilter === 'all' ? 'default' : 'outline'}
                                onClick={() => setStatusFilter('all')}
                            >
                                전체
                            </Button>
                            <Button
                                variant={statusFilter === 'processing' ? 'default' : 'outline'}
                                onClick={() => setStatusFilter('processing')}
                                className={statusFilter === 'processing' ? 'bg-chart-4' : ''}
                            >
                                진행 중
                            </Button>

                            <Button
                                variant={statusFilter === 'success' ? 'default' : 'outline'}
                                onClick={() => setStatusFilter('success')}
                                className={statusFilter === 'success' ? 'bg-chart-2' : ''}
                            >
                                확정완료
                            </Button>
                            <Button
                                variant={statusFilter === 'error' ? 'default' : 'outline'}
                                onClick={() => setStatusFilter('error')}
                                className={statusFilter === 'error' ? 'bg-destructive' : ''}
                            >
                                실패
                            </Button>
                        </div>
                    </div>
                </div>
            </Card >

            {/* Content */}
            < div className="flex-1 overflow-auto px-6 pb-6" >
                <Card className="rounded-t-none border-t-0">
                    {isLoading && (
                        <div className="flex items-center justify-center py-12">
                            <div className="text-center">
                                <ClockRegular className="w-12 h-12 mx-auto mb-3 animate-pulse text-primary" />
                                <p className="text-muted-foreground">기록을 불러오는 중...</p>
                            </div>
                        </div>
                    )}

                    {error && (
                        <div className="flex items-center justify-center py-12">
                            <div className="text-center">
                                <WarningRegular className="w-12 h-12 mx-auto mb-3 text-destructive" />
                                <p className="text-foreground font-semibold">기록을 불러올 수 없습니다</p>
                                <p className="text-sm text-muted-foreground">잠시 후 다시 시도해주세요</p>
                            </div>
                        </div>
                    )}

                    {!isLoading && !error && filteredLogs.length === 0 && (
                        <div className="flex items-center justify-center py-12">
                            <div className="text-center text-muted-foreground">
                                <DocumentRegular className="w-16 h-16 mx-auto mb-4 text-muted-foreground/50" />
                                <p className="text-lg font-semibold text-foreground">추출 기록이 없습니다</p>
                                <p className="text-sm text-muted-foreground">
                                    {searchTerm || statusFilter !== 'all' ? '검색 조건에 맞는 기록이 없습니다' : '문서를 추출하면 여기에 기록이 표시됩니다'}
                                </p>
                            </div>
                        </div>
                    )}

                    {!isLoading && !error && filteredLogs.length > 0 && (
                        <div className="overflow-auto">
                            <table className="w-full">
                                <thead className="bg-muted sticky top-0 z-10">
                                    <tr>
                                        <th className="px-6 py-3 text-left text-xs font-semibold text-foreground uppercase border-b-2 border-border">상태</th>
                                        <th className="px-6 py-3 text-left text-xs font-semibold text-foreground uppercase border-b-2 border-border">파일명</th>
                                        <th className="px-6 py-3 text-left text-xs font-semibold text-foreground uppercase border-b-2 border-border">추출 시간</th>
                                        <th className="px-6 py-3 text-left text-xs font-semibold text-foreground uppercase border-b-2 border-border">결과</th>
                                        <th className="px-6 py-3 text-right text-xs font-semibold text-foreground uppercase border-b-2 border-border">작업</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-border">
                                    {filteredLogs.map((log) => (
                                        <tr key={log.id} className="hover:bg-accent transition-colors cursor-pointer" onClick={() => handleRowClick(log, false)}>
                                            <td className="px-6 py-4">
                                                {isSuccessStatus(log.status) ? (
                                                    <div className="flex items-center gap-2">
                                                        <CheckmarkCircleRegular className="w-5 h-5 text-chart-2" />
                                                        <span className="text-sm font-medium text-chart-2">{STATUS_LABELS[log.status] || '성공'}</span>
                                                    </div>

                                                ) : isProcessingStatus(log.status) ? (
                                                    <div className="flex items-center gap-2">
                                                        <ClockRegular className="w-5 h-5 text-chart-4 animate-spin" />
                                                        <span className="text-sm font-medium text-chart-4">{STATUS_LABELS[log.status] || '처리 중'}</span>
                                                    </div>
                                                ) : (
                                                    <div className="flex items-center gap-2">
                                                        <WarningRegular className="w-5 h-5 text-destructive" />
                                                        <span className="text-sm font-medium text-destructive">{STATUS_LABELS[log.status] || '실패'}</span>
                                                    </div>
                                                )}
                                            </td>
                                            <td className="px-6 py-4">
                                                <div className="flex items-center gap-2">
                                                    <DocumentRegular className="w-4 h-4 text-muted-foreground" />
                                                    <span className="text-sm font-medium text-foreground">{log.filename}</span>
                                                </div>
                                            </td>
                                            <td className="px-6 py-4">
                                                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                                    <CalendarRegular className="w-4 h-4" />
                                                    {formatDate(log.created_at)}
                                                </div>
                                            </td>
                                            <td className="px-6 py-4">
                                                {isSuccessStatus(log.status) && log.extracted_data && (
                                                    <span className="text-sm text-foreground">{Object.keys(log.extracted_data).length}개 필드 추출</span>
                                                )}
                                                {isErrorStatus(log.status) && log.error && (
                                                    <span className="text-sm text-destructive" title={log.error}>{log.error.substring(0, 50)}...</span>
                                                )}
                                            </td>
                                            <td className="px-6 py-4 text-right">
                                                <div className="flex items-center justify-end gap-2">
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        onClick={(e) => { e.stopPropagation(); handleRetry(log) }}
                                                        title="재시도"
                                                    >
                                                        <ArrowClockwiseRegular className="w-4 h-4" />
                                                    </Button>
                                                    {isSuccessStatus(log.status) && log.extracted_data && (
                                                        <Button
                                                            size="sm"
                                                            onClick={(e) => { e.stopPropagation(); handleDownload(log) }}
                                                            className="bg-chart-2 hover:bg-chart-2/90"
                                                        >
                                                            <ArrowDownloadRegular className="w-4 h-4 mr-1" />
                                                            Excel
                                                        </Button>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </Card>
            </div >

            {/* Detail Modal */}
            {
                selectedLog && (
                    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setSelectedLog(null)}>
                        <Card className="max-w-2xl w-full mx-4 max-h-[80vh] overflow-hidden" onClick={(e) => e.stopPropagation()}>
                            <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-muted">
                                <div className="flex items-center gap-3">
                                    <EyeRegular className="w-5 h-5 text-chart-1" />
                                    <div>
                                        <h3 className="font-bold text-foreground">추출 상세 정보</h3>
                                        <p className="text-sm text-muted-foreground">{selectedLog.filename}</p>
                                    </div>
                                </div>
                                <Button variant="ghost" size="icon" onClick={() => setSelectedLog(null)}>
                                    <DismissRegular className="w-5 h-5" />
                                </Button>
                            </div>
                            <div className="p-6 overflow-auto max-h-[60vh]">
                                {isErrorStatus(selectedLog.status) ? (
                                    <div className="text-center py-8">
                                        <WarningRegular className="w-12 h-12 mx-auto mb-3 text-destructive" />
                                        <p className="font-semibold text-foreground">추출 실패</p>
                                        <p className="text-sm text-destructive mt-2">{selectedLog.error || '알 수 없는 오류'}</p>
                                    </div>
                                ) : selectedLog.extracted_data ? (
                                    <ExtractionDataViewer
                                        data={selectedLog.extracted_data}
                                        title="추출된 데이터"
                                    />
                                ) : (
                                    <p className="text-center text-muted-foreground py-8">추출 데이터가 없습니다</p>
                                )}
                            </div>
                            <div className="flex justify-end gap-3 px-6 py-4 border-t border-border bg-muted">
                                <Button variant="outline" onClick={() => handleRetry(selectedLog)}>
                                    <ArrowClockwiseRegular className="w-4 h-4 mr-2" />
                                    재시도
                                </Button>
                                {isSuccessStatus(selectedLog.status) && selectedLog.extracted_data && (
                                    <Button onClick={() => handleDownload(selectedLog)} className="bg-chart-2 hover:bg-chart-2/90">
                                        <ArrowDownloadRegular className="w-4 h-4 mr-1" />
                                        Excel 다운로드
                                    </Button>
                                )}
                                <Button variant="secondary" onClick={() => setSelectedLog(null)}>
                                    닫기
                                </Button>
                            </div>
                        </Card>
                    </div>
                )
            }
        </div >
    )
}
