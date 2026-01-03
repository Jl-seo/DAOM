import { Button } from '@/components/ui/button'

export type StatusFilterValue = 'all' | 'success' | 'processing' | 'draft' | 'error'

interface StatusFilterProps {
    value: StatusFilterValue
    onChange: (status: StatusFilterValue) => void
}

export function StatusFilter({ value, onChange }: StatusFilterProps) {
    const statuses = [
        { value: 'all' as const, label: '전체' },
        { value: 'processing' as const, label: '진행 중' },
        { value: 'draft' as const, label: '임시저장' },
        { value: 'success' as const, label: '확정완료' },
        { value: 'error' as const, label: '실패' }
    ]

    return (
        <div className="flex gap-2">
            {statuses.map((status) => (
                <Button
                    key={status.value}
                    variant={value === status.value ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => onChange(status.value)}
                    className={
                        value === status.value
                            ? status.value === 'success'
                                ? 'bg-chart-2 hover:bg-chart-2/90'
                                : status.value === 'error'
                                    ? 'bg-destructive hover:bg-destructive/90'
                                    : status.value === 'processing'
                                        ? 'bg-chart-4 hover:bg-chart-4/90'
                                        : status.value === 'draft'
                                            ? 'bg-amber-500 hover:bg-amber-500/90'
                                            : ''
                            : ''
                    }
                >
                    {status.label}
                </Button>
            ))}
        </div>
    )
}
