import { DocumentRegular, ArrowTrendingRegular, DismissCircleRegular, CheckmarkCircleRegular } from '@fluentui/react-icons'
import { Card, CardContent } from '@/components/ui/card'

interface StatsData {
    total: number
    success: number
    error: number
    today: number
}

interface StatsDashboardProps {
    stats: StatsData
}

export function StatsDashboard({ stats }: StatsDashboardProps) {
    const successRate = stats.total > 0 ? ((stats.success / stats.total) * 100).toFixed(1) : 0

    const statCards = [
        {
            label: '총 추출 건수',
            value: stats.total,
            icon: DocumentRegular,
            color: 'text-primary',
            bgColor: 'bg-primary/10',
        },
        {
            label: '성공률',
            value: `${successRate}%`,
            icon: ArrowTrendingRegular,
            color: 'text-chart-2',
            bgColor: 'bg-chart-2/10',
        },
        {
            label: '실패 건수',
            value: stats.error,
            icon: DismissCircleRegular,
            color: 'text-destructive',
            bgColor: 'bg-destructive/10',
        },
        {
            label: '오늘 추출',
            value: stats.today,
            icon: CheckmarkCircleRegular,
            color: 'text-chart-4',
            bgColor: 'bg-chart-4/10',
        },
    ]

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            {statCards.map((stat) => (
                <Card key={stat.label} className="hover:shadow-md transition-shadow">
                    <CardContent className="p-6">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm font-medium text-muted-foreground">{stat.label}</p>
                                <p className={`text-3xl font-bold mt-2 ${stat.color}`}>{stat.value}</p>
                            </div>
                            <div className={`w-12 h-12 ${stat.bgColor} rounded-xl flex items-center justify-center`}>
                                <stat.icon className={`w-6 h-6 ${stat.color}`} />
                            </div>
                        </div>
                    </CardContent>
                </Card>
            ))}
        </div>
    )
}
