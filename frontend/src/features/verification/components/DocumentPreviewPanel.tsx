/* eslint-disable @typescript-eslint/no-explicit-any */
import { forwardRef, useState } from 'react'
import { FileText, RefreshCw, ZoomIn, ZoomOut, RotateCcw, File, FileSpreadsheet } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PDFViewer, type PDFViewerHandle } from './PDFViewer'
import { ExcelGridViewer, type ExcelGridViewerHandle } from './ExcelGridViewer'
import { OcrTextViewer } from './OcrTextViewer'
import { RawTableRenderer } from './RawTableRenderer'
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch'
import { getFileType } from '../utils/fileTypeUtils'
import type { Highlight } from '../types'

interface DocumentPreviewPanelProps {
    file: File | null
    fileUrl: string | null
    filename?: string | null
    highlights: Highlight[]
    selectedFieldKey: string | null
    onHighlightClick: (key: string) => void
    onRetry: () => void
    ocrText?: string
    rawTables?: any[]
    isBetaMode?: boolean
}

// Union handle type — both PDFViewer and ExcelGridViewer expose scrollToHighlight
type ViewerHandle = PDFViewerHandle | ExcelGridViewerHandle

export const DocumentPreviewPanel = forwardRef<ViewerHandle, DocumentPreviewPanelProps>(({
    file,
    fileUrl,
    filename,
    highlights,
    selectedFieldKey,
    onHighlightClick,
    onRetry,
    ocrText,
    rawTables,
    isBetaMode = false
}, ref) => {
    const fileType = getFileType(file, fileUrl)
    const [imageTab, setImageTab] = useState<string>('image')

    // ─── Render helpers ───
    const renderOcrTab = () => (
        <TabsTrigger
            value="ocr"
            className="data-[state=active]:bg-background data-[state=active]:shadow-sm rounded-t-lg rounded-b-none border-b-2 border-transparent data-[state=active]:border-primary px-4 py-2 h-full gap-2 text-xs"
        >
            <FileText className="w-3.5 h-3.5" /> OCR 텍스트
        </TabsTrigger>
    )

    const renderTablesTab = () => {
        if (!rawTables || rawTables.length === 0) return null
        return (
            <TabsTrigger
                value="tables"
                className="data-[state=active]:bg-background data-[state=active]:shadow-sm rounded-t-lg rounded-b-none border-b-2 border-transparent data-[state=active]:border-primary px-4 py-2 h-full gap-2 text-xs"
            >
                <FileText className="w-3.5 h-3.5" /> 표 ({rawTables.length})
            </TabsTrigger>
        )
    }

    const renderOcrContent = () => (
        <TabsContent value="ocr" className="flex-1 mt-0 overflow-auto bg-background">
            <OcrTextViewer ocrText={ocrText} />
        </TabsContent>
    )

    const renderTablesContent = () => {
        if (!rawTables || rawTables.length === 0) return null
        return (
            <TabsContent value="tables" className="flex-1 mt-0 overflow-auto bg-background">
                <RawTableRenderer rawTables={rawTables || []} />
            </TabsContent>
        )
    }

    // ─── Viewer by file type ───
    const renderViewer = () => {
        if (!fileUrl) {
            return (
                <div className="text-center space-y-3 z-10">
                    <FileText className="w-12 h-12 mx-auto text-muted-foreground/50" />
                    <div>
                        <p className="text-sm font-medium text-foreground">원본 문서를 표시할 수 없습니다</p>
                        <p className="text-xs text-muted-foreground mt-1">
                            파일이 만료되었거나 접근할 수 없습니다
                        </p>
                    </div>
                    {onRetry && (
                        <Button size="sm" variant="outline" onClick={onRetry}>
                            <RefreshCw className="w-3 h-3 mr-1.5" />
                            재추출
                        </Button>
                    )}
                </div>
            )
        }

        // ── PDF ──
        if (fileType === 'pdf') {
            return (
                <PDFViewer
                    ref={ref as React.Ref<PDFViewerHandle>}
                    fileUrl={fileUrl}
                    highlights={highlights}
                    activeFieldKey={selectedFieldKey || undefined}
                    onHighlightClick={onHighlightClick}
                    ocrText={ocrText}
                    rawTables={rawTables}
                    isBetaMode={isBetaMode}
                />
            )
        }

        // ── Excel ──
        if (fileType === 'excel') {
            return (
                <Tabs
                    value={imageTab}
                    onValueChange={setImageTab}
                    className="w-full h-full flex flex-col"
                >
                    <TabsList className="w-full justify-start rounded-none border-b bg-muted/50 h-10 px-2 shrink-0">
                        <TabsTrigger
                            value="image"
                            className="data-[state=active]:bg-background data-[state=active]:shadow-sm rounded-t-lg rounded-b-none border-b-2 border-transparent data-[state=active]:border-primary px-4 py-2 h-full gap-2 text-xs"
                        >
                            <FileSpreadsheet className="w-3.5 h-3.5" /> 스프레드시트
                        </TabsTrigger>
                        {renderOcrTab()}
                        {renderTablesTab()}
                    </TabsList>

                    <TabsContent value="image" className="flex-1 mt-0 overflow-hidden relative">
                        <ExcelGridViewer
                            ref={ref as React.Ref<ExcelGridViewerHandle>}
                            fileUrl={fileUrl}
                            highlights={highlights}
                            activeFieldKey={selectedFieldKey || undefined}
                            onHighlightClick={onHighlightClick}
                        />
                    </TabsContent>
                    {renderOcrContent()}
                    {renderTablesContent()}
                </Tabs>
            )
        }

        // ── Image (default) ──
        return (
            <Tabs
                value={imageTab}
                onValueChange={setImageTab}
                className="w-full h-full flex flex-col"
            >
                <TabsList className="w-full justify-start rounded-none border-b bg-muted/50 h-10 px-2 shrink-0">
                    <TabsTrigger
                        value="image"
                        className="data-[state=active]:bg-background data-[state=active]:shadow-sm rounded-t-lg rounded-b-none border-b-2 border-transparent data-[state=active]:border-primary px-4 py-2 h-full gap-2 text-xs"
                    >
                        <File className="w-3.5 h-3.5" /> 이미지 원본
                    </TabsTrigger>
                    {renderOcrTab()}
                    {renderTablesTab()}
                </TabsList>

                <TabsContent value="image" className="flex-1 mt-0 overflow-hidden relative">
                    <TransformWrapper
                        initialScale={1}
                        minScale={0.5}
                        maxScale={5}
                        centerOnInit={true}
                    >
                        {({ zoomIn, zoomOut, resetTransform }) => (
                            <div className="w-full h-full flex flex-col">
                                <div className="flex items-center justify-center gap-2 py-2 bg-muted/50 border-b shrink-0">
                                    <button
                                        onClick={() => zoomOut()}
                                        className="p-1.5 rounded hover:bg-accent text-foreground"
                                        title="축소"
                                    >
                                        <ZoomOut className="w-4 h-4" />
                                    </button>
                                    <span className="text-xs text-muted-foreground">확대/축소</span>
                                    <button
                                        onClick={() => zoomIn()}
                                        className="p-1.5 rounded hover:bg-accent text-foreground"
                                        title="확대"
                                    >
                                        <ZoomIn className="w-4 h-4" />
                                    </button>
                                    <button
                                        onClick={() => resetTransform()}
                                        className="p-1.5 rounded hover:bg-accent text-foreground ml-2"
                                        title="초기화"
                                    >
                                        <RotateCcw className="w-4 h-4" />
                                    </button>
                                </div>
                                <div className="flex-1 overflow-hidden">
                                    <TransformComponent
                                        wrapperStyle={{ width: '100%', height: '100%' }}
                                        contentStyle={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                                    >
                                        <img
                                            src={fileUrl}
                                            className="max-w-full max-h-full object-contain shadow-md"
                                            alt="doc"
                                            draggable={false}
                                        />
                                    </TransformComponent>
                                </div>
                            </div>
                        )}
                    </TransformWrapper>
                </TabsContent>
                {renderOcrContent()}
                {renderTablesContent()}
            </Tabs>
        )
    }

    return (
        <Card className="h-full flex flex-col bg-muted/10 overflow-hidden border-0 rounded-none md:border-r">
            <div className="px-4 py-2 border-b bg-card flex justify-between items-center text-sm font-medium text-muted-foreground shrink-0">
                <span>원본 문서 미리보기</span>
                {(file?.name || filename) && <Badge variant="outline">{file?.name || filename}</Badge>}
            </div>
            <div className="flex-1 relative overflow-hidden flex items-center justify-center bg-muted/20 min-h-0">
                {renderViewer()}
            </div>
        </Card>
    )
})

DocumentPreviewPanel.displayName = 'DocumentPreviewPanel'
