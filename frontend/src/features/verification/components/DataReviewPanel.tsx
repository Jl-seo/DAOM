import { useState } from 'react'
import { CheckCircle2, RefreshCw, Download, Upload, Maximize2, Minimize2, Bug } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ExtractionPreview } from './ExtractionPreview'
import { ExtractionGrid } from '../../extraction/components/ExtractionGrid'
import { DebugInfoModal } from './DebugInfoModal'
import type { ExtractionModel, PreviewData } from '../types'

interface DataReviewPanelProps {
    currentGuideExtracted: Record<string, any>
    currentOtherData: any[]
    model: ExtractionModel
    previewData: PreviewData | null // For fallback fields
    debugData?: any // Optional debug data

    selectedFieldKey: string | null
    onFieldSelect: (key: string | null) => void
    onDataChange: (data: { guide: any, other: any[] }) => void
    onSave: (guide: Record<string, any>, other: any[]) => void
    onReset: () => void
    onRetry: () => void
    onDownload: () => void
    documentId?: string | null // Unique identifier for the document (fileUrl or ID)
}

export function DataReviewPanel({
    currentGuideExtracted,
    currentOtherData,
    model,
    previewData,
    debugData,
    selectedFieldKey,
    onFieldSelect,
    onDataChange,
    onSave,
    onReset,
    onRetry,
    onDownload,
    documentId
}: DataReviewPanelProps) {
    const [isExpanded, setIsExpanded] = useState(false)
    const [showDebugModal, setShowDebugModal] = useState(false)

    // Columns for the "Other Data" (Table) tab
    const tableColumns = currentOtherData && currentOtherData.length > 0
        ? Object.keys(currentOtherData[0] || {}).map(key => ({
            accessorKey: key,
            header: key,
            cell: (info: any) => <span className="text-sm">{info.getValue()}</span>
        }))
        : []

    return (
        <Card className={`h-full flex flex-col bg-background overflow-hidden border-0 rounded-none transition-all duration-300 ${isExpanded ? 'fixed inset-0 z-50' : ''}`}>
            <DebugInfoModal
                isOpen={showDebugModal}
                onClose={() => setShowDebugModal(false)}
                data={debugData}
            />

            <div className="px-6 py-3 border-b bg-card flex justify-between items-center shrink-0">
                <span className="flex items-center gap-2 font-semibold">
                    <CheckCircle2 className="w-5 h-5 text-green-500" />
                    추출 결과 확인
                </span>
                <div className="flex gap-2">
                    <Button variant="ghost" size="icon" onClick={() => setShowDebugModal(true)} title="View Debug Info">
                        <Bug className="w-4 h-4 text-muted-foreground" />
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => setIsExpanded(!isExpanded)}>
                        {isExpanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                    </Button>
                    <div className="w-px h-6 bg-border mx-1" />
                    <Button variant="outline" onClick={onReset} className="text-muted-foreground hover:text-foreground">
                        <Upload className="w-4 h-4 mr-2" /> 새 문서
                    </Button>
                    <Button variant="outline" onClick={onRetry} className="text-muted-foreground hover:text-foreground">
                        <RefreshCw className="w-4 h-4 mr-2" /> 재시도
                    </Button>
                    <Button onClick={onDownload} variant="outline" className="text-muted-foreground hover:text-foreground">
                        <Download className="w-4 h-4 mr-2" /> 엑셀 다운로드
                    </Button>
                </div>
            </div>

            <Tabs defaultValue="fields" className="flex-1 flex flex-col min-h-0">
                <div className="px-6 border-b bg-muted/40">
                    <TabsList className="bg-transparent h-12 p-0 space-x-6">
                        <TabsTrigger value="fields" className="h-full rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:shadow-none px-0">추출 필드</TabsTrigger>
                        <TabsTrigger value="table" className="h-full rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:shadow-none px-0">상세 테이블</TabsTrigger>
                        <TabsTrigger value="raw" className="h-full rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:shadow-none px-0">Raw JSON</TabsTrigger>
                    </TabsList>
                </div>

                <div className="flex-1 overflow-hidden relative">
                    <TabsContent value="fields" className="mt-0 h-full p-0 data-[state=inactive]:hidden">
                        <ExtractionPreview
                            // Force remount when document changes OR when data arrives
                            // This resets local state while preventing loops during editing
                            key={`${documentId || 'default'}-${Object.keys(currentGuideExtracted || {}).length}`}
                            guideExtracted={currentGuideExtracted || {}}
                            otherData={currentOtherData || []}
                            modelFields={model?.fields || previewData?.model_fields || []}
                            onFieldSelect={onFieldSelect}
                            onDataChange={onDataChange}
                            onSave={onSave}
                            selectedField={selectedFieldKey} // Sync: Data Selection Control
                            readOnly={false}
                        />
                    </TabsContent>
                    <TabsContent value="table" className="mt-0 h-full p-0 data-[state=inactive]:hidden">
                        <ScrollArea className="h-full">
                            <div className="p-6">
                                {/* Check if currentOtherData exists and has length before rendering ExtractionGrid */}
                                {currentOtherData && currentOtherData.length > 0 ? (
                                    <ExtractionGrid
                                        data={currentOtherData}
                                        columns={tableColumns}
                                    />
                                ) : (
                                    <div className="text-center text-muted-foreground py-10">테이블 데이터가 없습니다</div>
                                )}
                            </div>
                        </ScrollArea>
                    </TabsContent>
                    <TabsContent value="raw" className="mt-0 h-full p-0 data-[state=inactive]:hidden">
                        <ScrollArea className="h-full">
                            <pre className="p-6 text-xs font-mono whitespace-pre-wrap">
                                {JSON.stringify(currentGuideExtracted, null, 2)}
                            </pre>
                        </ScrollArea>
                    </TabsContent>
                </div>
            </Tabs>
        </Card>
    )
}
