/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useMemo, useCallback, useEffect } from 'react'
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
    currentOtherData: any[]
    exportData?: any[] | null
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
    onUnmask?: (fieldKey: string) => Promise<string | undefined>
    documentId?: string | null // Unique identifier for the document (fileUrl or ID)
    currentParsedContent?: string | null // NEW: Parsed text from LayoutParser
    isBetaMode?: boolean
    isRawData?: boolean
}

// Fields to keep in the export JSON — everything else gets stripped
const KEEP_FIELDS = new Set(['value', 'confidence'])

function cleanForExport(data: Record<string, any>): Record<string, any> {
    const stripInternal = (obj: any): any => {
        if (Array.isArray(obj)) return obj.map(stripInternal)
        if (obj && typeof obj === 'object') {
            // If this object has a 'value' key, it's a field cell — keep only value + confidence
            if ('value' in obj) {
                const cleaned: Record<string, any> = {}
                for (const [k, v] of Object.entries(obj)) {
                    if (KEEP_FIELDS.has(k)) {
                        cleaned[k] = stripInternal(v)
                    }
                }
                return cleaned
            }
            // Otherwise recurse normally (e.g., nested row objects in tables)
            const filtered: Record<string, any> = {}
            for (const [k, v] of Object.entries(obj)) {
                if (!k.startsWith('_')) filtered[k] = stripInternal(v)
            }
            return filtered
        }
        return obj
    }

    const clean: Record<string, any> = {}
    for (const [key, val] of Object.entries(data)) {
        if (!key.startsWith('_')) clean[key] = stripInternal(val)
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
                    value + confidence만 표시
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
    exportData,
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
    onUnmask,
    documentId,
    isBetaMode = false,
    isRawData = false
}: DataReviewPanelProps) {
    const [isExpanded, setIsExpanded] = useState(false)
    const [showDebugModal, setShowDebugModal] = useState(false)
    const [isRendering, setIsRendering] = useState(false)
    const [deferredData, setDeferredData] = useState({
        guideExtracted: currentGuideExtracted,
        parsedContent: currentParsedContent,
        otherData: currentOtherData,
        exportData: exportData
    })

    // Defer rendering of massive payloads to ensure the browser paints the loading state first
    useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setIsRendering(true)

        // Yield to browser event loop to paint the "Loading" overlay before locking main thread
        const timer = setTimeout(() => {
            setDeferredData({
                guideExtracted: currentGuideExtracted,
                parsedContent: currentParsedContent,
                otherData: currentOtherData,
                exportData: exportData
            })
            setIsRendering(false)
        }, 150)
        return () => clearTimeout(timer)
    }, [currentGuideExtracted, currentParsedContent, currentOtherData, exportData, documentId])


    // Columns for the "Other Data" (Table) tab - REMOVED for Beta Text View
    // const tableColumns = ...

    return (
        <Card className={`h-full flex flex-col bg-background overflow-hidden border-0 rounded-none relative transition-all duration-300 ${isExpanded ? 'fixed inset-0 z-50' : ''}`}>
            {isRendering && (
                <div className="fixed inset-0 z-[9999] bg-background/80 flex flex-col items-center justify-center backdrop-blur-md">
                    <RefreshCw className="w-12 h-12 animate-spin text-primary mb-6" />
                    <p className="text-xl font-bold text-foreground">데이터를 화면에 불러오고 있습니다...</p>
                    <p className="text-base text-muted-foreground mt-2">데이터 양이 많을 경우 잠시 화면이 멈출 수 있습니다.</p>
                </div>
            )}
            <DebugInfoModal
                isOpen={showDebugModal}
                onClose={() => setShowDebugModal(false)}
                data={debugData}
            />

            <div className="px-6 py-3 border-b bg-card flex justify-between items-center shrink-0">
                <span className="flex items-center gap-2 font-semibold">
                    <CheckCircle2 className="w-5 h-5 text-green-500" />
                    {isRawData ? 'AI 원본 추출 결과 (Raw Data)' : '규칙 반영 최종 결과 (Refined Data)'}
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
                        {isBetaMode && (
                            <TabsTrigger value="parsed_text" className="h-full rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:shadow-none px-0">
                                Parsed Text {deferredData.parsedContent ? `(${(deferredData.parsedContent.length / 1000).toFixed(1)}K)` : '(대기중)'} <span className="ml-1 text-[10px] bg-blue-100 text-blue-800 px-1 rounded">BETA</span>
                            </TabsTrigger>
                        )}
                        <TabsTrigger value="mapped" className="h-full rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:shadow-none px-0">매핑된 결과 (Export)</TabsTrigger>
                        <TabsTrigger value="raw" className="h-full rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:shadow-none px-0">Raw JSON</TabsTrigger>
                    </TabsList>
                </div>

                <div className="flex-1 overflow-hidden relative">
                    <TabsContent value="fields" className="mt-0 h-full p-0 data-[state=inactive]:hidden">
                        <ExtractionPreview
                            key={`${documentId || 'default'}-${Object.keys(deferredData.guideExtracted || {}).length}`}
                            guideExtracted={deferredData.guideExtracted || {}}
                            otherData={deferredData.otherData || []}
                            modelFields={model?.fields || previewData?.model_fields || []}
                            onFieldSelect={onFieldSelect}
                            onDataChange={onDataChange}
                            onSave={onSave}
                            selectedField={selectedFieldKey}
                            onUnmask={onUnmask}
                            readOnly={false}
                            dexValidation={previewData?.__dex_validation__ as DexValidationData | undefined}
                        />
                    </TabsContent>
                    <TabsContent value="parsed_text" className="mt-0 h-full p-0 data-[state=inactive]:hidden">
                        <ScrollArea className="h-full">
                            <div className="p-6">
                                {deferredData.parsedContent ? (
                                    <pre className="text-xs font-mono whitespace-pre-wrap bg-muted/30 p-4 rounded-md border text-foreground/80 leading-relaxed">
                                        {deferredData.parsedContent}
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
                    <TabsContent value="mapped" className="mt-0 h-full p-0 data-[state=inactive]:hidden bg-muted/10">
                        {Array.isArray(deferredData.exportData) && deferredData.exportData.length > 0 ? (
                            <div className="h-full flex flex-col">
                                <div className="px-6 pt-4 pb-2 flex items-center justify-between shrink-0">
                                    <div className="text-xs text-muted-foreground">
                                        현재 저장된 매핑 설정에 따라 변환된 <b>플랫 테이블 (Flat Table)</b> 형태입니다. 
                                        {deferredData.exportData.length > 0 && ` (총 ${deferredData.exportData.length}행)`}
                                    </div>
                                    <Button variant="outline" size="sm" onClick={onDownload} className="h-7 text-xs gap-1.5 border-primary/20 text-primary hover:bg-primary/10">
                                        <Download className="w-3.5 h-3.5" /> 엑셀 다운로드
                                    </Button>
                                </div>
                                <div className="flex-1 overflow-auto px-6 pb-6 mt-2">
                                    <div className="rounded-md border bg-white shadow-sm inline-block min-w-full">
                                        <table className="w-full text-sm text-left">
                                            <thead className="bg-slate-50 border-b sticky top-0 z-10">
                                                <tr>
                                                    <th className="px-4 py-2 font-semibold text-slate-600 text-xs whitespace-nowrap bg-slate-50 border-r border-slate-200 w-12 text-center shadow-[0_1px_0_0_#e2e8f0]">#</th>
                                                    {Object.keys(deferredData.exportData[0] || {}).map(colKey => (
                                                        colKey !== 'bbox' && !colKey.startsWith('_') && (
                                                            <th key={colKey} className="px-4 py-2 font-semibold text-slate-700 text-xs whitespace-nowrap bg-slate-50 border-r border-slate-200 shadow-[0_1px_0_0_#e2e8f0]">
                                                                {colKey}
                                                            </th>
                                                        )
                                                    ))}
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-slate-100">
                                                {deferredData.exportData.map((row: any, idx: number) => (
                                                    <tr key={idx} className="hover:bg-blue-50/50 transition-colors">
                                                        <td className="px-4 py-2 text-slate-400 text-xs border-r border-slate-100 text-center bg-slate-50/50">{idx + 1}</td>
                                                        {Object.keys(deferredData.exportData[0] || {}).map(colKey => (
                                                            colKey !== 'bbox' && !colKey.startsWith('_') && (
                                                                <td key={colKey} className="px-4 py-2 text-slate-700 whitespace-nowrap border-r border-slate-100">
                                                                    {typeof row[colKey] === 'object' && row[colKey] !== null
                                                                        ? (row[colKey].value !== undefined ? String(row[colKey].value) : JSON.stringify(row[colKey]))
                                                                        : String(row[colKey] ?? '')}
                                                                </td>
                                                            )
                                                        ))}
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            </div>
                        ) : (
                            <div className="flex flex-col items-center justify-center p-12 text-center h-full">
                                <div className="w-12 h-12 bg-muted/50 rounded-full flex items-center justify-center mb-4">
                                    <CheckCircle2 className="w-6 h-6 text-muted-foreground" />
                                </div>
                                <h3 className="text-lg font-medium text-foreground">매핑된 엑셀 데이터가 없습니다</h3>
                                <p className="text-sm text-muted-foreground mt-2 max-w-md">
                                    이 모델은 내보내기 매핑(Export Engine)이 설정되어 있지 않거나, 아직 추출된 배열 데이터가 존재하지 않습니다.<br/><br/>
                                    또는 폼(Form) 형태의 데이터 추출 결과일 수 있습니다. JSON 원본 포맷만 제공됩니다.
                                </p>
                            </div>
                        )}
                    </TabsContent>
                    <TabsContent value="raw" className="mt-0 h-full p-0 data-[state=inactive]:hidden">
                        <RawJsonView data={deferredData.guideExtracted} />
                    </TabsContent>
                </div>
            </Tabs>
        </Card>
    )
}
