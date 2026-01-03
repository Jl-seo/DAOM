import { Upload, History } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ExtractionHistory } from '@/features/extraction/components/ExtractionHistory'
import type { ExtractionModel } from '../types'

interface ExtractionHistoryViewProps {
    model: ExtractionModel
    onNewExtraction: () => void
    onSelectHistory: (log: any) => void
}

export function ExtractionHistoryView({
    model,
    onNewExtraction,
    onSelectHistory
}: ExtractionHistoryViewProps) {
    return (
        <div className="flex-1 flex flex-col bg-muted/30 h-full overflow-hidden">
            <div className="p-8 pb-4">
                <div className="flex justify-between items-end mb-6">
                    <div>
                        <h1 className="text-3xl font-bold flex items-center gap-3">
                            {model.name}
                            <Badge variant="outline" className="text-base font-normal px-3 py-1">
                                {model.fields?.length || 0}개 필드
                            </Badge>
                        </h1>
                        <p className="text-muted-foreground mt-2 text-lg">{model.description}</p>
                    </div>
                    <Button
                        size="lg"
                        onClick={onNewExtraction}
                        className="text-base px-8 h-12 shadow-lg shadow-primary/20 transition-transform hover:scale-105"
                    >
                        <Upload className="w-5 h-5 mr-2" /> 새 문서 추출하기
                    </Button>
                </div>
            </div>

            <div className="flex-1 px-8 pb-8 overflow-hidden">
                <Card className="h-full flex flex-col shadow-sm border-muted-foreground/20">
                    <div className="p-4 border-b bg-muted/5 flex items-center gap-2">
                        <History className="w-5 h-5 text-muted-foreground" />
                        <span className="font-semibold text-lg">최근 추출 기록</span>
                    </div>
                    <div className="flex-1 overflow-hidden">
                        <ExtractionHistory
                            modelId={model.id}
                            embedded={true}
                            onNewExtraction={onNewExtraction}
                            onSelectRecord={(record) => onSelectHistory(record)}
                        />
                    </div>
                </Card>
            </div>
        </div>
    )
}
