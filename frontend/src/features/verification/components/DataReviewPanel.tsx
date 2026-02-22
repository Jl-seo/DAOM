/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useMemo, useCallback } from 'react'
import { CheckCircle2, RefreshCw, Download, Upload, Maximize2, Minimize2, Bug, Copy, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ExtractionPreview } from './ExtractionPreview'
import { DexValidationBanner, type DexValidationData } from './DexValidationBanner'
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

// Internal fields to strip from export JSON
const INTERNAL_FIELDS = ['bbox', 'page_number', 'original_value', 'low_confidence', 'validation_status']

function cleanForExport(data: Record<string, any>): Record<string, any> {
    const stripInternal = (obj: any): any => {
        if (Array.isArray(obj)) return obj.map(stripInternal)
        if (obj && typeof obj === 'object') {
            const filtered: Record<string, any> = {}
            for (const [k, v] of Object.entries(obj)) {
                if (!INTERNAL_FIELDS.includes(k)) filtered[k] = stripInternal(v)
            }
            return filtered
        }
        return obj
    }

    const clean: Record<string, any> = {}
    for (const [key, val] of Object.entries(data)) {
        clean[key] = stripInternal(val)
    }
    return clean
}

function RawJsonView({ data }: { data: Record<string, any> }) {
    const [copied, setCopied] = useState(false)
    const cleanData = useMemo(() => cleanForExport(data || {}), [data])
    const jsonStr = useMemo(() => JSON.stringify(cleanData, null, 2), [cleanData])

    const handleCopy = useCallback(() => {
        navigator.clipboard.writeText(jsonStr)
            .then(() => {
                setCopied(true)
                setTimeout(() => setCopied(false), 2000)
            })
            .catch(() => {
                // Fallback for browsers that block clipboard API
                const textarea = document.createElement('textarea')
                textarea.value = jsonStr
                document.body.appendChild(textarea)
                textarea.select()
                document.execCommand('copy')
                document.body.removeChild(textarea)
                setCopied(true)
                setTimeout(() => setCopied(false), 2000)
            })
    }, [jsonStr])

    return (
        <div className="h-full flex flex-col">
            <div className="flex items-center justify-between px-6 pt-4 pb-2">
                <span className="text-xs text-muted-foreground">
                    내부 필드 제외 (bbox, page_number 등)
                </span>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={handleCopy}
                    className="gap-1.5 text-xs h-7"
                >
                    {copied ? <Check className="w-3.5 h-3.5 text-green-500" /> : <Copy className="w-3.5 h-3.5" />}
                    {copied ? '복사됨!' : 'JSON 복사'}
                </Button>
            </div>
            <ScrollArea className="flex-1">
                <pre className="px-6 pb-6 text-xs font-mono whitespace-pre-wrap">
                    {jsonStr}
                </pre>
            </ScrollArea>
        </div>
    )
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
                            {/* Pipeline Stage Diagnostics */}
                            {debugData.beta_pipeline_stages && (
                                <div className="mt-3 pt-3 border-t border-yellow-500/20">
                                    <div className="font-semibold text-xs mb-2">📊 파이프라인 단계별 상태</div>
                                    <div className="space-y-1">
                                        {Object.entries(debugData.beta_pipeline_stages as Record<string, any>).map(([stage, info]: [string, any]) => {
                                            const isOk = info?.status === 'ok'
                                            const label: Record<string, string> = {
                                                '1_layout_parser': '1️⃣ LayoutParser',
                                                '2_prompt': '2️⃣ 프롬프트 생성',
                                                '3_llm_call': '3️⃣ LLM 호출',
                                                '4_normalize': '4️⃣ 응답 정규화',
                                                '5_post_process': '5️⃣ 후처리',
                                                'exception': '💥 예외',
                                            }
                                            return (
                                                <div key={stage} className="flex items-start gap-2 text-xs font-mono">
                                                    <span>{isOk ? '✅' : '❌'}</span>
                                                    <span className="font-semibold min-w-[120px]">{label[stage] || stage}</span>
                                                    <span className="text-muted-foreground">
                                                        {info?.content_chars && `${info.content_chars.toLocaleString()}자`}
                                                        {info?.field_count && `${info.field_count}필드`}
                                                        {info?.raw_key_count !== undefined && `응답 ${info.raw_key_count}키`}
                                                        {info?.fields_recovered !== undefined && `${info.fields_recovered}필드 복구`}
                                                        {info?.fields_with_values !== undefined && (
                                                            <span>
                                                                <span className="text-green-600">{info.fields_with_values}값</span>
                                                                {info.fields_null > 0 && <span className="text-red-600 ml-1">{info.fields_null}null</span>}
                                                            </span>
                                                        )}
                                                        {info?.error && <span className="text-red-600">{info.error.slice(0, 100)}</span>}
                                                    </span>
                                                </div>
                                            )
                                        })}
                                    </div>
                                </div>
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

            {/* DEX Validation Banner */}
            {previewData?.__dex_validation__ && (
                <div className="px-6 pt-4">
                    <DexValidationBanner data={previewData.__dex_validation__ as DexValidationData} />
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
                            dexValidation={previewData?.__dex_validation__ as DexValidationData | undefined}
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
                        <RawJsonView data={currentGuideExtracted} />
                    </TabsContent>
                </div>
            </Tabs>
        </Card>
    )
}
