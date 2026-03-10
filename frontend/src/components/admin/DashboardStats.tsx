import { useState, useEffect } from 'react'
import { BarChart, Bar, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from 'recharts'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Activity, Database, FileText, TrendingUp, CheckCircle2 } from 'lucide-react'
import { apiClient } from '../../lib/api'

const STATUS_LABELS: Record<string, string> = {
    'P100': '대기 중',
    'P200': '업로드 중',
    'P300': '분석 중',
    'P400': 'AI 추출 중',
    'P500': '추출 완료 (대기)',
    'S100': '최종 승인',
    'E100': '추출 실패',
    'E200': '시스템 오류',
    'E300': '사용자 취소'
}

const STATUS_COLORS: Record<string, string> = {
    'S100': 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
    'P500': 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
    'E100': 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
    'E200': 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
    'E300': 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
    'default': 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400'
}

export function DashboardStats() {
    const [stats, setStats] = useState<any>(null)
    const [loading, setLoading] = useState(true)
    const [period, setPeriod] = useState(30) // Default to 30 days

    useEffect(() => {
        fetchStats(period)
    }, [period])

    const fetchStats = async (days: number) => {
        setLoading(true)
        try {
            const res = await apiClient.get(`/audit/stats?days=${days}`)
            setStats(res.data)
        } catch (error) {
            console.error('Failed to load stats:', error)
        } finally {
            setLoading(false)
        }
    }

    if (loading) return <div className="p-8 text-center text-muted-foreground">로딩 중...</div>

    if (!stats || !stats.summary) return <div className="p-8 text-center">데이터가 없습니다</div>

    const { summary, daily_trend, model_usage, recent_activity } = stats
    
    // Top 5 Models to display safely on the horizontal bar chart
    const topModels = [...model_usage].sort((a: any, b: any) => b.value - a.value).slice(0, 5)

    return (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* Header / Filter section */}
            <div className="flex items-center justify-between">
                <h2 className="text-xl font-semibold tracking-tight">대시보드 통계</h2>
                <div className="flex items-center gap-2 text-sm">
                    <span className="text-muted-foreground">기간:</span>
                    <select
                        className="border border-border rounded-md px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-primary/50 bg-background text-sm"
                        value={period}
                        onChange={(e) => setPeriod(Number(e.target.value))}
                    >
                        <option value={7}>최근 7일</option>
                        <option value={30}>최근 30일 (이번 달)</option>
                        <option value={90}>최근 3개월</option>
                    </select>
                </div>
            </div>

            {/* KPI Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <KPICard
                    title="해당 기간 추출 건수"
                    value={summary.total_extractions}
                    icon={Database}
                    description={`선택한 ${period}일 동안의 처리량`}
                />
                <KPICard
                    title="성공률"
                    value={`${summary.success_rate}%`}
                    icon={CheckCircle2}
                    description="해당 기간 평균 성공률 (완료 및 승인)"
                    trend="positive"
                />
                <KPICard
                    title="활성 모델"
                    value={summary.active_models}
                    icon={FileText}
                    description="해당 기간 사용된 데이터 모델"
                />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Daily Trend Chart (Area Chart) */}
                <Card>
                    <CardHeader>
                        <CardTitle className="text-lg flex items-center gap-2">
                            <TrendingUp className="w-4 h-4 text-primary" />
                            일별 추출 현황
                        </CardTitle>
                        <CardDescription>최근 {period}일간의 문서 처리량 추이</CardDescription>
                    </CardHeader>
                    <CardContent className="h-[280px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={daily_trend} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                                <defs>
                                    <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3}/>
                                        <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0}/>
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
                                <XAxis
                                    dataKey="date"
                                    tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
                                    axisLine={false}
                                    tickLine={false}
                                    tickFormatter={(val) => val.slice(5)} // Show MM-DD only
                                />
                                <YAxis
                                    tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
                                    axisLine={false}
                                    tickLine={false}
                                />
                                <Tooltip
                                    contentStyle={{
                                        backgroundColor: 'hsl(var(--card))',
                                        borderColor: 'hsl(var(--border))',
                                        borderRadius: '8px',
                                        fontSize: '12px'
                                    }}
                                />
                                <Area type="monotone" dataKey="count" stroke="hsl(var(--primary))" strokeWidth={2} fillOpacity={1} fill="url(#colorCount)" />
                            </AreaChart>
                        </ResponsiveContainer>
                    </CardContent>
                </Card>

                {/* Model Usage Chart (Top 5 Horizontal Bar Chart) */}
                <Card>
                    <CardHeader>
                        <CardTitle className="text-lg flex items-center gap-2">
                            <Activity className="w-4 h-4 text-chart-2" />
                            상위 모델 현황 (Top 5)
                        </CardTitle>
                        <CardDescription>해당 기간 가장 많이 사용된 추출 모델</CardDescription>
                    </CardHeader>
                    <CardContent className="h-[280px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={topModels} layout="vertical" margin={{ top: 0, right: 20, left: 0, bottom: 0 }}>
                                <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} stroke="hsl(var(--border))" />
                                <XAxis type="number" hide />
                                <YAxis 
                                    type="category" 
                                    dataKey="name" 
                                    width={140} 
                                    tick={{ fontSize: 11, fill: 'hsl(var(--foreground))' }} 
                                    axisLine={false} 
                                    tickLine={false} 
                                    tickFormatter={(value) => value.length > 15 ? `${value.slice(0, 15)}...` : value}
                                />
                                <Tooltip
                                    cursor={{ fill: 'hsl(var(--muted)/0.5)' }}
                                    contentStyle={{
                                        backgroundColor: 'hsl(var(--card))',
                                        borderColor: 'hsl(var(--border))',
                                        borderRadius: '8px',
                                        fontSize: '12px'
                                    }}
                                />
                                <Bar dataKey="value" fill="#005bbb" radius={[0, 4, 4, 0]} barSize={20} />
                            </BarChart>
                        </ResponsiveContainer>
                    </CardContent>
                </Card>
            </div>

            {/* Recent Activity Mini Table */}
            <Card>
                <CardHeader>
                    <CardTitle className="text-base">최근 활동</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="space-y-4">
                        {recent_activity.map((activity: any) => {
                            const statusLabel = STATUS_LABELS[activity.status] || activity.status
                            const badgeColor = STATUS_COLORS[activity.status] || STATUS_COLORS['default']
                            return (
                                <div key={activity.id} className="flex items-center justify-between border-b border-border pb-2 last:border-0 last:pb-0">
                                    <div className="flex flex-col">
                                        <span className="text-sm font-medium">{activity.model}</span>
                                        <span className="text-xs text-muted-foreground">{activity.filename} · {activity.user}</span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <span className={`text-xs px-2 py-1 rounded-full ${badgeColor}`}>
                                            {statusLabel}
                                        </span>
                                        <span className="text-xs text-muted-foreground w-[70px] text-right">
                                            {new Date(activity.timestamp).toLocaleDateString()}
                                        </span>
                                    </div>
                                </div>
                            )
                        })}
                    </div>
                </CardContent>
            </Card>
        </div>
    )
}

function KPICard({ title, value, icon: Icon, description }: any) {
    return (
        <Card>
            <CardContent className="p-6">
                <div className="flex items-center justify-between space-y-0 pb-2">
                    <p className="text-sm font-medium text-muted-foreground">
                        {title}
                    </p>
                    <Icon className="h-4 w-4 text-muted-foreground" />
                </div>
                <div className="text-2xl font-bold">{value}</div>
                <p className="text-xs text-muted-foreground mt-1">
                    {description}
                </p>
            </CardContent>
        </Card>
    )
}
