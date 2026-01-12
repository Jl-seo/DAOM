import { useState, useEffect } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Activity, Database, FileText, TrendingUp, CheckCircle2 } from 'lucide-react'
import { apiClient } from '../../lib/api'

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8', '#82ca9d']

export function DashboardStats() {
    const [stats, setStats] = useState<any>(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        fetchStats()
    }, [])

    const fetchStats = async () => {
        try {
            const res = await apiClient.get('/audit/stats')
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
            {/* KPI Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <KPICard
                    title="총 추출 건수"
                    value={summary.total_extractions}
                    icon={Database}
                    description="누적 문서 처리량"
                />
                <KPICard
                    title="성공률"
                    value={`${summary.success_rate}%`}
                    icon={CheckCircle2}
                    description="전체 평균 성공률"
                    trend="positive"
                />
                <KPICard
                    title="활성 모델"
                    value={summary.active_models}
                    icon={FileText}
                    description="사용 중인 데이터 모델"
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
                        <CardDescription>최근 7일간의 문서 처리량 추이</CardDescription>
                    </CardHeader>
                    <CardContent className="h-[300px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={daily_trend}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
                                <XAxis
                                    dataKey="date"
                                    tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }}
                                    axisLine={false}
                                    tickLine={false}
                                />
                                <YAxis
                                    tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }}
                                    axisLine={false}
                                    tickLine={false}
                                />
                                <Tooltip
                                    contentStyle={{
                                        backgroundColor: 'hsl(var(--card))',
                                        borderColor: 'hsl(var(--border))',
                                        borderRadius: '8px'
                                    }}
                                />
                                <Bar dataKey="count" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
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
                    <CardContent className="h-[300px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                                <Pie
                                    data={model_usage}
                                    cx="50%"
                                    cy="50%"
                                    innerRadius={60}
                                    outerRadius={80}
                                    paddingAngle={5}
                                    dataKey="value"
                                >
                                    {model_usage.map((_: any, index: number) => (
                                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                    ))}
                                </Pie>
                                <Tooltip
                                    contentStyle={{
                                        backgroundColor: 'hsl(var(--card))',
                                        borderColor: 'hsl(var(--border))',
                                        borderRadius: '8px'
                                    }}
                                />
                            </PieChart>
                        </ResponsiveContainer>
                        <div className="flex flex-wrap justify-center gap-4 mt-2">
                            {model_usage.map((entry: any, index: number) => (
                                <div key={entry.name} className="flex items-center gap-1.5 text-xs text-muted-foreground">
                                    <div className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS[index % COLORS.length] }} />
                                    {entry.name} ({entry.value})
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
