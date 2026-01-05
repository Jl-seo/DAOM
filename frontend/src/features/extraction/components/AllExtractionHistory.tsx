import { useState, useMemo } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
// import { useNavigate } from 'react-router-dom'
import { Clock, Search, AlertTriangle, Check, ChevronsUpDown } from 'lucide-react'
import {
    Command,
    CommandEmpty,
    CommandGroup,
    CommandInput,
    CommandItem,
    CommandList,
} from "@/components/ui/command"
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from "@/components/ui/popover"
import { cn } from "@/lib/utils"
import { apiClient, modelsApi, usersApi, extractionApi } from '../../../lib/api'
import { downloadAsExcel } from '../../../utils/excel'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card } from '@/components/ui/card'
import { ExtractionLogTable } from './ExtractionLogTable'
import type { ExtractionLog } from '../../verification/types'
import { isSuccessStatus, isErrorStatus, isProcessingStatus } from '../../verification/constants/status'

interface AllExtractionHistoryProps {
    onNavigate?: (path: string) => void
}

const Combobox = ({ value, onChange, options, placeholder, searchPlaceholder }: any) => {
    const [open, setOpen] = useState(false)

    // Find selected label
    const selectedLabel = useMemo(() => {
        if (value === 'all') return placeholder || "전체"
        return options.find((opt: any) => opt.value === value)?.label || placeholder
    }, [value, options, placeholder])

    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
                <Button
                    variant="outline"
                    role="combobox"
                    aria-expanded={open}
                    className="w-[200px] justify-between font-normal"
                >
                    {selectedLabel}
                    <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[200px] p-0">
                <Command>
                    <CommandInput placeholder={searchPlaceholder || "검색..."} />
                    <CommandList>
                        <CommandEmpty>결과가 없습니다.</CommandEmpty>
                        <CommandGroup>
                            <CommandItem
                                value="all"
                                onSelect={() => {
                                    onChange('all')
                                    setOpen(false)
                                }}
                            >
                                <Check
                                    className={cn(
                                        "mr-2 h-4 w-4",
                                        value === 'all' ? "opacity-100" : "opacity-0"
                                    )}
                                />
                                {placeholder || "전체"}
                            </CommandItem>
                            {options.map((opt: any) => (
                                <CommandItem
                                    key={opt.value}
                                    value={opt.label} // Use label for search matching
                                    onSelect={() => {
                                        onChange(opt.value)
                                        setOpen(false)
                                    }}
                                >
                                    <Check
                                        className={cn(
                                            "mr-2 h-4 w-4",
                                            value === opt.value ? "opacity-100" : "opacity-0"
                                        )}
                                    />
                                    {opt.label}
                                </CommandItem>
                            ))}
                        </CommandGroup>
                    </CommandList>
                </Command>
            </PopoverContent>
        </Popover>
    )
}

export function AllExtractionHistory({ onNavigate }: AllExtractionHistoryProps) {
    const queryClient = useQueryClient()
    const [modelFilter, setModelFilter] = useState<string>('all')
    const [userFilter, setUserFilter] = useState<string>('all')
    const [searchTerm, setSearchTerm] = useState('')
    const [statusFilter, setStatusFilter] = useState<'all' | 'success' | 'processing' | 'error'>('all')

    // Fetch Models for Name Mapping
    const { data: models = [] } = useQuery({
        queryKey: ['models'],
        queryFn: async () => {
            const res = await modelsApi.getAll()
            return res.data
        },
        staleTime: Infinity
    })

    // Fetch Users for Filter
    const { data: users = [] } = useQuery({
        queryKey: ['users'],
        queryFn: async () => {
            const res = await usersApi.getAll()
            return res.data
        },
        staleTime: Infinity
    })

    const modelMap = useMemo(() => {
        return models.reduce((acc: any, model: any) => {
            acc[model.id] = model.name
            return acc
        }, {})
    }, [models])

    const { data: logs = [], isLoading, error } = useQuery({
        queryKey: ['extraction-logs-all'],
        queryFn: async () => {
            const res = await apiClient.get(`/extraction/logs/all`, {
                params: { limit: 200 }
            })
            return res.data as ExtractionLog[]
        },
        refetchInterval: 30000
    })

    const filteredLogs = logs.map(log => ({
        ...log,
        model_name: modelMap[log.model_id] || log.model_id // Map Model Name
    })).filter(log => {
        const matchesSearch = log.filename.toLowerCase().includes(searchTerm.toLowerCase())
        const matchesModel = modelFilter === 'all' || log.model_id === modelFilter
        const matchesUser = userFilter === 'all' || log.user_id === userFilter
        let matchesStatus = false
        switch (statusFilter) {
            case 'all':
                matchesStatus = true
                break
            case 'success':
                matchesStatus = isSuccessStatus(log.status)
                break
            case 'processing':
                matchesStatus = isProcessingStatus(log.status)
                break
            case 'error':
                matchesStatus = isErrorStatus(log.status)
                break
            default:
                matchesStatus = true
        }
        return matchesSearch && matchesStatus && matchesModel && matchesUser
    })

    const handleDownload = (log: ExtractionLog) => {
        if (!log.extracted_data) {
            toast.error('추출 데이터가 없습니다')
            return
        }

        const data = Object.fromEntries(
            Object.entries(log.extracted_data).map(([k, v]) => [
                k,
                typeof v === 'object' && v?.value ? v.value : v
            ])
        )

        downloadAsExcel(
            [{ filename: log.filename, ...data }],
            `${log.filename}_${new Date(log.created_at).toLocaleDateString()}`
        )
        toast.success('Excel 다운로드!')
    }

    const handleRetry = async (log: ExtractionLog) => {
        toast.promise(apiClient.post(`/extraction/retry/${log.id}`), {
            loading: '재시도 요청 중...',
            success: '재시도 작업이 시작되었습니다. 잠시 후 목록이 갱신됩니다.',
            error: '재시도 요청 실패'
        })
        await queryClient.invalidateQueries({ queryKey: ['extraction-logs-all'] })
    }

    const handleCancel = async (log: ExtractionLog) => {
        if (!log.job_id) return
        if (!confirm('정말로 이 작업을 취소하시겠습니까?')) return
        try {
            await extractionApi.cancelJob(log.job_id)
            toast.success('작업이 취소되었습니다.')
            await queryClient.invalidateQueries({ queryKey: ['extraction-logs-all'] })
        } catch {
            toast.error('작업 취소 실패')
        }
    }

    const handleDelete = async (log: ExtractionLog) => {
        if (!confirm('정말로 이 기록을 삭제하시겠습니까? 복구할 수 없습니다.')) return
        try {
            await extractionApi.deleteJob(log.id)
            toast.success('기록이 삭제되었습니다.')
            await queryClient.invalidateQueries({ queryKey: ['extraction-logs-all'] })
        } catch {
            toast.error('삭제 실패')
        }
    }

    const handleView = (log: ExtractionLog) => {
        // Navigate to the model page
        // Ideally we would pass the log ID to open it, but for now we just go to the model
        if (onNavigate) {
            onNavigate(`model-${log.model_id}`)
            toast.info('해당 모델 페이지로 이동합니다.')
        }
    }

    return (
        <div className="flex-1 p-8 overflow-auto bg-background">
            <div className="max-w-7xl mx-auto">
                {/* Header */}
                <div className="mb-6">
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-3">
                            <div className="w-12 h-12 bg-primary/10 rounded-xl flex items-center justify-center">
                                <Clock className="w-6 h-6 text-primary" />
                            </div>
                            <div>
                                <h1 className="text-2xl font-bold text-foreground">전체 추출 기록</h1>
                                <p className="text-sm text-muted-foreground">총 {filteredLogs.length}개 기록</p>
                            </div>
                        </div>
                    </div>

                    {/* Filters */}
                    <div className="flex gap-4">
                        <div className="flex-1 relative">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                            <Input
                                type="text"
                                placeholder="파일명 검색..."
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                                className="pl-10"
                            />
                        </div>
                        <div className="flex gap-2">
                            <Combobox
                                value={userFilter}
                                onChange={setUserFilter}
                                options={users.map((u: any) => ({
                                    value: u.id,
                                    label: u.name ? `${u.name} (${u.email})` : u.email
                                }))}
                                placeholder="모든 사용자"
                                searchPlaceholder="사용자 이름/이메일 검색"
                            />
                            <Combobox
                                value={modelFilter}
                                onChange={setModelFilter}
                                options={models.map((m: any) => ({ value: m.id, label: m.name }))}
                                placeholder="모든 모델"
                                searchPlaceholder="모델 검색"
                            />
                            <Button
                                variant={statusFilter === 'all' ? 'default' : 'outline'}
                                onClick={() => setStatusFilter('all')}
                            >
                                전체
                            </Button>
                            <Button
                                variant={statusFilter === 'processing' ? 'default' : 'outline'}
                                onClick={() => setStatusFilter('processing')}
                                className={statusFilter === 'processing' ? 'bg-chart-4 hover:bg-chart-4/90' : ''}
                            >
                                진행 중
                            </Button>
                            <Button
                                variant={statusFilter === 'success' ? 'default' : 'outline'}
                                onClick={() => setStatusFilter('success')}
                                className={statusFilter === 'success' ? 'bg-chart-2 hover:bg-chart-2/90' : ''}
                            >
                                성공
                            </Button>
                            <Button
                                variant={statusFilter === 'error' ? 'destructive' : 'outline'}
                                onClick={() => setStatusFilter('error')}
                            >
                                실패
                            </Button>
                        </div>
                    </div>
                </div>

                {/* Content */}
                <Card className="overflow-hidden border-none shadow-none bg-transparent">
                    {isLoading && (
                        <div className="flex items-center justify-center py-12">
                            <div className="text-center">
                                <Clock className="w-12 h-12 mx-auto mb-3 animate-pulse text-primary" />
                                <p className="text-muted-foreground">기록을 불러오는 중...</p>
                            </div>
                        </div>
                    )}

                    {error && (
                        <div className="flex items-center justify-center py-12">
                            <div className="text-center">
                                <AlertTriangle className="w-12 h-12 mx-auto mb-3 text-destructive" />
                                <p className="text-foreground font-semibold">기록을 불러올 수 없습니다</p>
                            </div>
                        </div>
                    )}

                    {!isLoading && !error && (
                        <ExtractionLogTable
                            logs={filteredLogs}
                            showModelColumn={true}
                            onView={handleView}
                            onDownload={handleDownload}
                            onRetry={handleRetry}
                            onCancel={handleCancel}
                            onDelete={handleDelete}
                        />
                    )}
                </Card>
            </div>
        </div>
    )
}
