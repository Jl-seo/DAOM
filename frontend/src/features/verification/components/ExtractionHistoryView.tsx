/* eslint-disable @typescript-eslint/no-explicit-any */
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
        <div className="flex-1 flex flex-col bg-muted/30 min-h-0 overflow-auto">
            {/* 헤더 - 모바일에서 축소 */}
            <div className="p-4 md:p-8 pb-2 md:pb-4 shrink-0">
                <div className="flex flex-col md:flex-row md:justify-between md:items-end gap-4 mb-4 md:mb-6">
                    <div>
                        <h1 className="text-xl md:text-3xl font-bold flex items-center gap-2 md:gap-3 flex-wrap">
                            {model.name}
                            <Badge variant="outline" className="text-sm md:text-base font-normal px-2 md:px-3 py-0.5 md:py-1">
                                {model.fields?.length || 0}개 필드
                            </Badge>
                        </h1>
                        <p className="text-muted-foreground mt-1 md:mt-2 text-sm md:text-lg line-clamp-2">{model.description}</p>
                    </div>
                    <Button
                        size="default"
                        onClick={onNewExtraction}
                        className="text-sm md:text-base px-4 md:px-8 h-10 md:h-12 shadow-lg shadow-primary/20 transition-transform hover:scale-105 w-full md:w-auto shrink-0"
                    >
                        <Upload className="w-4 h-4 md:w-5 md:h-5 mr-2" /> 새 문서 추출하기
                    </Button>
                </div>
            </div>

            {/* 테이블 컨테이너 */}
            <div className="flex-1 px-4 md:px-8 pb-4 md:pb-8 min-h-0">
                <Card className="h-full flex flex-col shadow-sm border-muted-foreground/20 min-h-[300px]">
                    <div className="p-3 md:p-4 border-b bg-muted/5 flex items-center gap-2 shrink-0">
                        <History className="w-4 h-4 md:w-5 md:h-5 text-muted-foreground" />
                        <span className="font-semibold text-base md:text-lg">최근 추출 기록</span>
                    </div>
                    <div className="flex-1 overflow-auto min-h-0">
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
