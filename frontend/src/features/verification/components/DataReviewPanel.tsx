import { useState } from 'react'
import { CheckCircle2, RefreshCw, Download, Upload, Maximize2, Minimize2, Bug } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ExtractionPreview } from './ExtractionPreview'
// import { ExtractionGrid } from '../../extraction/components/ExtractionGrid'
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
    currentParsedContent?: string | null // NEW: Parsed text from LayoutParser
    isBetaMode?: boolean
}

export function DataReviewPanel({
    currentGuideExtracted,
    currentOtherData,
    currentParsedContent,
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
    documentId,
    isBetaMode = false
}: DataReviewPanelProps) {
    const [isExpanded, setIsExpanded] = useState(false)
    const [showDebugModal, setShowDebugModal] = useState(false)



    // Columns for the "Other Data" (Table) tab - REMOVED for Beta Text View
    // const tableColumns = ...

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

            {/* DEBUG INFO BANNER - Make it VERY visible */}
            {debugData && Object.keys(debugData).length > 0 && (
                <div className="mx-6 mt-3 mb-2 p-4 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
                    <div className="flex items-start justify-between">
                        <div className="flex-1">
                            <div className="font-semibold text-sm mb-2 flex items-center gap-2">
                                <Bug className="w-4 h-4" />
                                디버그 정보 (LLM 추출 상세)
                            </div>
                            <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs font-mono">
                                {debugData._chunked && (
                                    <div><span className="text-muted-foreground">청킹 모드:</span> <span className="font-semibold text-blue-600">활성화</span></div>
                                )}
                                {debugData._debug_chunking?.total_chunks !== undefined && (
                                    <div><span className="text-muted-foreground">처리된 청크:</span> <span className="font-semibold">{debugData._debug_chunking.total_chunks}</span></div>
                                )}
                                {debugData._debug_chunking?.successful_chunks !== undefined && (
                                    <div><span className="text-muted-foreground">성공한 청크:</span> <span className="font-semibold text-green-600">{debugData._debug_chunking.successful_chunks}</span></div>
                                )}
                                {debugData._debug_chunking?.chunk_debug?.[0]?.tables_count !== undefined && (
                                    <div><span className="text-muted-foreground">표 개수:</span> <span className="font-semibold">{debugData._debug_chunking.chunk_debug[0].tables_count}</span></div>
                                )}
                                {debugData._debug_chunking?.chunk_debug?.[0]?.prompt_size && (
                                    <div><span className="text-muted-foreground">프롬프트 크기:</span> <span className="font-semibold">{debugData._debug_chunking.chunk_debug[0].prompt_size} chars</span></div>
                                )}
                                {debugData._debug_chunking?.chunk_debug?.[0]?.response_size && (
                                    <div><span className="text-muted-foreground">LLM 응답 크기:</span> <span className="font-semibold">{debugData._debug_chunking.chunk_debug[0].response_size} chars</span></div>
                                )}
                                {/* Token Usage Display */}
                                {debugData.token_usage && (
                                    <>
                                        <div><span className="text-muted-foreground">입력 토큰:</span> <span className="font-semibold text-purple-600">{debugData.token_usage.prompt_tokens?.toLocaleString()}</span></div>
                                        <div><span className="text-muted-foreground">출력 토큰:</span> <span className="font-semibold text-purple-600">{debugData.token_usage.completion_tokens?.toLocaleString()}</span></div>
                                        <div><span className="text-muted-foreground">총 토큰:</span> <span className="font-semibold text-orange-600">{debugData.token_usage.total_tokens?.toLocaleString()}</span></div>
                                    </>
                                )}
                            </div>
                            {debugData._debug_chunking?.chunk_debug?.[0]?.response_preview && (
                                <details className="mt-2">
                                    <summary className="text-xs cursor-pointer text-blue-600 hover:underline">LLM 응답 미리보기 보기</summary>
                                    <pre className="mt-2 p-2 bg-slate-900 text-slate-50 rounded text-xs overflow-x-auto">
                                        {debugData._debug_chunking.chunk_debug[0].response_preview}
                                    </pre>
                                </details>
                            )}
                        </div>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setShowDebugModal(true)}
                            className="ml-4"
                        >
                            전체 보기
                        </Button>
                    </div>
                </div>
            )}

            <Tabs defaultValue="fields" className="flex-1 flex flex-col min-h-0">
                <div className="px-6 border-b bg-muted/40">
                    <TabsList className="bg-transparent h-12 p-0 space-x-6">
                        <TabsTrigger value="fields" className="h-full rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:shadow-none px-0">추출 필드</TabsTrigger>
                        {/* Only show Parsed Text tab when Beta mode is enabled — content may or may not be available */}
                        {isBetaMode && (
                            <TabsTrigger value="parsed_text" className="h-full rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:shadow-none px-0">
                                Parsed Text {currentParsedContent ? `(${(currentParsedContent.length / 1000).toFixed(1)}K)` : '(대기중)'} <span className="ml-1 text-[10px] bg-blue-100 text-blue-800 px-1 rounded">BETA</span>
                            </TabsTrigger>
                        )}
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
                    <TabsContent value="parsed_text" className="mt-0 h-full p-0 data-[state=inactive]:hidden">
                        <ScrollArea className="h-full">
                            <div className="p-6">
                                {currentParsedContent ? (
                                    <pre className="text-xs font-mono whitespace-pre-wrap bg-muted/30 p-4 rounded-md border text-foreground/80 leading-relaxed">
                                        {currentParsedContent}
                                    </pre>
                                ) : (
                                    <div className="flex flex-col items-center justify-center py-10 text-muted-foreground gap-2">
                                        <p>파싱된 텍스트가 없습니다.</p>
                                        <p className="text-xs">Beta 기능을 활성화하거나 재추출해주세요.</p>
                                    </div>
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
