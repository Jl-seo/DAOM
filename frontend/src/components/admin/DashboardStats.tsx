import { useState, useEffect } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Activity, Database, FileText, TrendingUp, CheckCircle2 } from 'lucide-react'
import { apiClient } from '../../lib/api'

const COLORS = ['#005bbb', '#00b0ff', '#1E88E5', '#64b5f6', '#90caf9', '#e3f2fd']

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
                    description="해당 기간 평균 성공률"
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
                {/* Daily Trend Chart */}
                <Card>
                    <CardHeader>
                        <CardTitle className="text-lg flex items-center gap-2">
                            <TrendingUp className="w-4 h-4 text-primary" />
                            일별 추출 현황
                        </CardTitle>
                        <CardDescription>최근 {period}일간의 문서 처리량 추이</CardDescription>
                    </CardHeader>
                    <CardContent className="h-[240px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={daily_trend} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
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
                                    cursor={{ fill: 'hsl(var(--muted)/0.5)' }}
                                    contentStyle={{
                                        backgroundColor: 'hsl(var(--card))',
                                        borderColor: 'hsl(var(--border))',
                                        borderRadius: '8px',
                                        fontSize: '12px'
                                    }}
                                />
                                <Bar dataKey="count" fill="hsl(var(--primary))" barSize={24} radius={[4, 4, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    </CardContent>
                </Card>

                {/* Model Usage Chart */}
                <Card>
                    <CardHeader>
                        <CardTitle className="text-lg flex items-center gap-2">
                            <Activity className="w-4 h-4 text-chart-2" />
                            모델별 사용량
                        </CardTitle>
                        <CardDescription>가장 많이 사용된 추출 모델</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="h-[240px]">
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie
                                        data={model_usage}
                                        cx="50%"
                                        cy="50%"
                                        innerRadius={70} // Make it a Donut Chart
                                        outerRadius={90}
                                        paddingAngle={5}
                                        dataKey="value"
                                        stroke="none"
                                    >
                                        {model_usage.map((_: any, index: number) => (
                                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                        ))}
                                    </Pie>
                                    <Tooltip
                                        contentStyle={{
                                            backgroundColor: 'hsl(var(--card))',
                                            borderColor: 'hsl(var(--border))',
                                            borderRadius: '8px',
                                            fontSize: '12px',
                                            border: 'none',
                                            boxShadow: '0 4px 12px rgba(0,0,0,0.1)'
                                        }}
                                    />
                                </PieChart>
                            </ResponsiveContainer>
                        </div>
                        <div className="flex flex-wrap justify-center gap-x-4 gap-y-2 mt-4 max-h-[80px] overflow-y-auto overflow-x-hidden pr-2 text-xs">
                            {model_usage.map((entry: any, index: number) => (
                                <div key={entry.name} className="flex items-center gap-1.5 text-muted-foreground w-max">
                                    <div className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ backgroundColor: COLORS[index % COLORS.length] }} />
                                    <span className="truncate max-w-[120px]">{entry.name}</span>
                                    <span className="font-medium text-foreground ml-0.5">{entry.value}</span>
                                </div>
                            ))}
                        </div>
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
                        {recent_activity.map((activity: any) => (
                            <div key={activity.id} className="flex items-center justify-between border-b border-border pb-2 last:border-0 last:pb-0">
                                <div className="flex flex-col">
                                    <span className="text-sm font-medium">{activity.model}</span>
                                    <span className="text-xs text-muted-foreground">{activity.filename} · {activity.user}</span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <span className={`text-xs px-2 py-1 rounded-full ${activity.status === 'success'
                                        ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                                        : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                                        }`}>
                                        {activity.status}
                                    </span>
                                    <span className="text-xs text-muted-foreground">
                                        {new Date(activity.timestamp).toLocaleDateString()}
                                    </span>
                                </div>
                            </div>
                        ))}
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
