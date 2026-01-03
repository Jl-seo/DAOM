interface JSONPreviewProps {
    data: Record<string, any>[]
}

export function JSONPreview({ data }: JSONPreviewProps) {
    return (
        <div className="overflow-auto max-h-[400px]">
            <pre className="bg-sidebar text-chart-2 p-4 rounded-lg text-xs font-mono leading-relaxed">
                {JSON.stringify(data, null, 2)}
            </pre>
        </div>
    )
}
