import { useRef } from 'react'
import { Upload, History, Files, ScanLine } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ExtractionHistory } from '@/features/extraction/components/ExtractionHistory'
import type { ExtractionModel } from '../types'
import { apiClient } from '@/lib/api'
import { toast } from 'sonner'
import { useQueryClient } from '@tanstack/react-query'
import { DEXScanner } from './DEXScanner'
import { useState } from 'react'

interface ExtractionHistoryViewProps {
    model: ExtractionModel
    onNewExtraction: () => void
    onSelectHistory: (log: any) => void
    onViewAggregated: () => void
}

export function ExtractionHistoryView({
    model,
    onNewExtraction,
    onSelectHistory,
    onViewAggregated
}: ExtractionHistoryViewProps) {
    const queryClient = useQueryClient()
    const fileInputRef = useRef<HTMLInputElement>(null)
    const [isScannerOpen, setIsScannerOpen] = useState(false)

    const handleBatchUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = Array.from(e.target.files || [])
        if (!files.length) return

        const uploadPromise = async () => {
            const CHUNK_SIZE = 10;
            for (let i = 0; i < files.length; i += CHUNK_SIZE) {
                const chunk = files.slice(i, i + CHUNK_SIZE);
                const formData = new FormData();
                chunk.forEach(f => formData.append('files', f));
                formData.append('model_id', model.id);
                await apiClient.post('/extraction/start-batch-jobs', formData);
            }
        }

        toast.promise(uploadPromise(), {
            loading: `${files.length}개의 파일을 일괄 업로드 중입니다...`,
            success: () => {
                queryClient.invalidateQueries({ queryKey: ['extraction-logs', model.id] })
                queryClient.invalidateQueries({ queryKey: ['extraction-logs-all'] })
                return `${files.length}개의 문서 추출 작업이 백그라운드에서 시작되었습니다.`
            },
            error: '일괄 업로드에 실패했습니다.'
        })

        if (fileInputRef.current) {
            fileInputRef.current.value = ''
        }
    }

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
                    <div className="flex flex-col md:flex-row gap-2 w-full md:w-auto shrink-0">
                        {model.beta_features?.use_dex_validation && (
                            <Button
                                variant="secondary"
                                onClick={() => setIsScannerOpen(true)}
                                className="text-sm md:text-base px-4 md:px-6 h-10 md:h-12 shadow-sm transition-transform hover:scale-105"
                            >
                                <ScanLine className="w-4 h-4 md:w-5 md:h-5 mr-2" /> 실시간 스캔 (DEX Beta)
                            </Button>
                        )}
                        <Button
                            variant="secondary"
                            onClick={onViewAggregated}
                            className="bg-primary/10 text-primary hover:bg-primary/20 text-sm md:text-base px-4 md:px-6 h-10 md:h-12 shadow-sm transition-all"
                        >
                            <Files className="w-4 h-4 md:w-5 md:h-5 mr-2" /> 통합 데이터 모아보기
                        </Button>
                        <Button
                            variant="outline"
                            size="default"
                            onClick={() => fileInputRef.current?.click()}
                            className="text-sm md:text-base px-4 md:px-6 h-10 md:h-12 shadow-sm transition-transform hover:scale-105"
                        >
                            <Files className="w-4 h-4 md:w-5 md:h-5 mr-2" /> 다중 파일 자동 추출
                        </Button>
                        <input
                            type="file"
                            multiple
                            accept=".pdf,.png,.jpg,.jpeg,.xlsx,.csv,.tiff"
                            className="hidden"
                            ref={fileInputRef}
                            onChange={handleBatchUpload}
                        />
                        <Button
                            size="default"
                            onClick={onNewExtraction}
                            className="text-sm md:text-base px-4 md:px-6 h-10 md:h-12 shadow-lg shadow-primary/20 transition-transform hover:scale-105"
                        >
                            <Upload className="w-4 h-4 md:w-5 md:h-5 mr-2" /> 단일 문서 정밀 추출
                        </Button>
                    </div>
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

            {isScannerOpen && (
                <DEXScanner
                    model={model}
                    onClose={() => setIsScannerOpen(false)}
                />
            )}
        </div>
    )
}
