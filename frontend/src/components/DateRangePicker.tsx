import { CalendarRegular } from '@fluentui/react-icons'
import { Button } from '@/components/ui/button'

type DatePreset = 'all' | 'today' | 'week' | 'month'

interface DateRangePickerProps {
    value: DatePreset
    onChange: (preset: DatePreset) => void
}

export function DateRangePicker({ value, onChange }: DateRangePickerProps) {
    const presets: { value: DatePreset; label: string }[] = [
        { value: 'all', label: '전체' },
        { value: 'today', label: '오늘' },
        { value: 'week', label: '이번 주' },
        { value: 'month', label: '이번 달' }
    ]

    return (
        <div className="flex items-center gap-2">
            <CalendarRegular className="w-4 h-4 text-muted-foreground" />
            <div className="flex gap-1">
                {presets.map((preset) => (
                    <Button
                        key={preset.value}
                        variant={value === preset.value ? 'default' : 'secondary'}
                        size="sm"
                        onClick={() => onChange(preset.value)}
                    >
                        {preset.label}
                    </Button>
                ))}
            </div>
        </div>
    )
}
