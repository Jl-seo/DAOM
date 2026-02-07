/* eslint-disable @typescript-eslint/no-explicit-any */
/* eslint-disable react-hooks/exhaustive-deps */
import { useState, useEffect } from 'react'
import { Search, Download, Calendar, User, Activity, RefreshCw } from 'lucide-react'
import { API_CONFIG } from '../constants'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/auth/AuthContext'

interface AuditLog {
    id: string
    timestamp: string
    user_id: string
    user_email: string
    action: string
    resource_type: string
    resource_id: string
    details?: Record<string, unknown>
    ip_address?: string
}

const actionColors: Record<string, string> = {
    CREATE: 'bg-chart-2/10 text-chart-2',
    READ: 'bg-primary/10 text-primary',
    UPDATE: 'bg-chart-4/10 text-chart-4',
    DELETE: 'bg-destructive/10 text-destructive',
    EXPORT: 'bg-chart-5/10 text-chart-5',
    EXTRACT: 'bg-chart-3/10 text-chart-3',
    LOGIN: 'bg-chart-1/10 text-chart-1',
    LOGOUT: 'bg-muted text-muted-foreground'
}

export function AuditLogViewer() {
    const [logs, setLogs] = useState<AuditLog[]>([])
    const [loading, setLoading] = useState(true)
    const [filters, setFilters] = useState({
        action: '',
        resource_type: '',
        start_date: '',
        end_date: ''
    })
    const { getAccessToken } = useAuth()

    const fetchLogs = async () => {
        setLoading(true)
        try {
            const token = await getAccessToken()
            if (!token) {
                console.error('No access token available')
                setLoading(false)
                return
            }

            const params = new URLSearchParams()
            if (filters.action) params.set('action', filters.action)
            if (filters.resource_type) params.set('resource_type', filters.resource_type)
            if (filters.start_date) params.set('start_date', filters.start_date)
            if (filters.end_date) params.set('end_date', filters.end_date)

            const response = await fetch(
                `${API_CONFIG.BASE_URL}/audit?${params.toString()}`,
                {
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    }
                }
            )

            if (response.ok) {
                const data = await response.json()
                setLogs(data.items || [])
            } else {
                console.error('Audit fetch failed:', response.status)
            }
        } catch (error) {
            console.error('Failed to fetch audit logs:', error)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        fetchLogs()
    }, [])

    const formatDate = (isoString: string) => {
        return new Date(isoString).toLocaleString('ko-KR', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        })
    }

    const exportCSV = () => {
        const headers = ['시간', '사용자', '액션', '리소스', 'ID', 'IP']
        const rows = logs.map(log => [
            log.timestamp,
            log.user_email,
            log.action,
            log.resource_type,
            log.resource_id,
            log.ip_address || ''
        ])

        const csv = [headers, ...rows].map(row => row.join(',')).join('\n')
        const blob = new Blob([csv], { type: 'text/csv' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `audit_logs_${new Date().toISOString().split('T')[0]}.csv`
        a.click()
    }

    return (
        <Card className="overflow-hidden">
            {/* Header */}
            <div className="p-6 border-b border-border">
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-primary/10 rounded-xl">
                            <Activity className="w-5 h-5 text-primary" />
                        </div>
                        <div>
                            <h2 className="text-xl font-bold text-foreground">감사 로그</h2>
                            <p className="text-sm text-muted-foreground">시스템 활동 기록</p>
                        </div>
                    </div>
                    <div className="flex gap-2">
                        <Button variant="outline" onClick={fetchLogs}>
                            <RefreshCw className="w-4 h-4 mr-2" />
                            새로고침
                        </Button>
                        <Button onClick={exportCSV}>
                            <Download className="w-4 h-4 mr-2" />
                            CSV 내보내기
                        </Button>
                    </div>
                </div>

                {/* Filters */}
                <div className="flex flex-wrap gap-3">
                    <select
                        value={filters.action}
                        onChange={(e) => setFilters({ ...filters, action: e.target.value })}
                        className="px-3 py-2 text-sm border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-ring bg-background"
                    >
                        <option value="">전체 액션</option>
                        <option value="CREATE">생성</option>
                        <option value="READ">조회</option>
                        <option value="UPDATE">수정</option>
                        <option value="DELETE">삭제</option>
                        <option value="EXPORT">내보내기</option>
                        <option value="EXTRACT">추출</option>
                    </select>

                    <select
                        value={filters.resource_type}
                        onChange={(e) => setFilters({ ...filters, resource_type: e.target.value })}
                        className="px-3 py-2 text-sm border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-ring bg-background"
                    >
                        <option value="">전체 리소스</option>
                        <option value="model">모델</option>
                        <option value="document">문서</option>
                        <option value="extraction">추출</option>
                        <option value="template">템플릿</option>
                    </select>

                    <Input
                        type="date"
                        value={filters.start_date}
                        onChange={(e) => setFilters({ ...filters, start_date: e.target.value })}
                        className="w-auto"
                    />

                    <Input
                        type="date"
                        value={filters.end_date}
                        onChange={(e) => setFilters({ ...filters, end_date: e.target.value })}
                        className="w-auto"
                    />

                    <Button variant="secondary" onClick={fetchLogs}>
                        <Search className="w-4 h-4 mr-2" />
                        검색
                    </Button>
                </div>
            </div>

            {/* Table */}
            <div className="overflow-x-auto">
                <table className="w-full">
                    <thead className="bg-muted border-b border-border">
                        <tr>
                            <th className="px-6 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                                <Calendar className="w-4 h-4 inline mr-1" />
                                시간
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                                <User className="w-4 h-4 inline mr-1" />
                                사용자
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                                액션
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                                리소스
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                                ID
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                                토큰
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                                IP
                            </th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                        {loading ? (
                            <tr>
                                <td colSpan={7} className="px-6 py-12 text-center text-muted-foreground">
                                    <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2" />
                                    로딩 중...
                                </td>
                            </tr>
                        ) : logs.length === 0 ? (
                            <tr>
                                <td colSpan={7} className="px-6 py-12 text-center text-muted-foreground">
                                    감사 로그가 없습니다
                                </td>
                            </tr>
                        ) : (
                            logs.map(log => (
                                <tr key={log.id} className="hover:bg-accent">
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                                        {formatDate(log.timestamp)}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-foreground font-medium">
                                        {log.user_email}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <span className={`px-2 py-1 text-xs font-semibold rounded-full ${actionColors[log.action] || 'bg-muted text-muted-foreground'}`}>
                                            {log.action}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                                        {log.resource_type}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground font-mono">
                                        {log.resource_id.slice(0, 8)}...
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                                        {(log.details as any)?.token_usage?.total_tokens ? (
                                            <span className="text-purple-600 font-semibold">
                                                {(log.details as any).token_usage.total_tokens.toLocaleString()}
                                            </span>
                                        ) : (
                                            <span className="text-muted-foreground">-</span>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                                        {log.ip_address || '-'}
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>
        </Card>
    )
}
