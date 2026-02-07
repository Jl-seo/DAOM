import { useState, forwardRef, useImperativeHandle } from 'react'
import { Viewer, Worker, SpecialZoomLevel } from '@react-pdf-viewer/core'
import { pageNavigationPlugin } from '@react-pdf-viewer/page-navigation'
import { highlightPlugin, type RenderHighlightsProps } from '@react-pdf-viewer/highlight'
import { searchPlugin } from '@react-pdf-viewer/search'
import { zoomPlugin, type RenderZoomInProps, type RenderZoomOutProps } from '@react-pdf-viewer/zoom'

import '@react-pdf-viewer/core/lib/styles/index.css'
import '@react-pdf-viewer/page-navigation/lib/styles/index.css'
import '@react-pdf-viewer/highlight/lib/styles/index.css'
import '@react-pdf-viewer/search/lib/styles/index.css'
import '@react-pdf-viewer/zoom/lib/styles/index.css'

import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut, RotateCcw, FileText, File } from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { OcrTextViewer } from './OcrTextViewer'
import { RawTableRenderer } from './RawTableRenderer'

// ... Highlight Interface ...
interface Highlight {
    fieldKey?: string // Add fieldKey to identify specific highlights
    content: string
    pageIndex: number
    position: {
        boundingRect: {
            x1: number
            y1: number
            x2: number
            y2: number
            width: number
            height: number
        }
    }
}

interface PDFViewerProps {
    fileUrl: string
    highlights?: Highlight[]
    activeFieldKey?: string | null
    onHighlightClick?: (fieldKey: string) => void
    ocrText?: string
    rawTables?: any[]  // Tables from Document Intelligence
    isBetaMode?: boolean
}

export interface PDFViewerHandle {
    scrollToHighlight: (fieldKey: string) => void
}

export const PDFViewer = forwardRef<PDFViewerHandle, PDFViewerProps>(({ fileUrl, highlights = [], activeFieldKey, onHighlightClick, ocrText, rawTables = [], isBetaMode = false }, ref) => {
    const [currentPage, setCurrentPage] = useState(0)
    const [totalPages, setTotalPages] = useState(0)
    const [activeTab, setActiveTab] = useState<'pdf' | 'ocr' | 'tables'>('pdf')

    // Plugins
    const pageNavigationPluginInstance = pageNavigationPlugin()
    const { jumpToPage } = pageNavigationPluginInstance

    const searchPluginInstance = searchPlugin({
        keyword: '',
        onHighlightKeyword: (props) => {
            props.highlightEle.style.backgroundColor = 'rgba(59, 130, 246, 0.3)'
            props.highlightEle.style.border = '1px solid rgba(59, 130, 246, 0.5)'
        }
    })
    const { highlight, clearHighlights } = searchPluginInstance

    const zoomPluginInstance = zoomPlugin()
    const { ZoomIn: ZoomInCtrl, ZoomOut: ZoomOutCtrl } = zoomPluginInstance

    // Expose methods to parent
    useImperativeHandle(ref, () => ({
        scrollToHighlight: (fieldKey: string) => {
            const target = highlights.find(h => h.fieldKey === fieldKey)

            // 1. Text Search Highlight (Visual Correction)
            clearHighlights()
            if (target && target.content) {
                const searchContent = target.content.toString().trim()
                if (searchContent.length > 0) {
                    highlight({
                        keyword: searchContent,
                        matchCase: false,
                        wholeWords: false,
                    })
                }
            }

            // 2. OCR Coordinate Jump (Navigation)
            if (target) {
                // If we are not on the target page, jump to it
                if (currentPage !== target.pageIndex) {
                    jumpToPage(target.pageIndex)
                }

                // ZOOM IN for focus (User Request)
                zoomPluginInstance.zoomTo(1.5) // 150% zoom

                // Robust Polling: Wait for element to appear in DOM
                let attempts = 0
                const maxAttempts = 20 // 2 seconds max
                const interval = setInterval(() => {
                    attempts++
                    const el = document.getElementById(`highlight-${fieldKey}`)

                    if (el) {
                        clearInterval(interval)

                        // Scroll logic
                        el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' })

                        // Add temporary visual cue (flash)
                        el.style.boxShadow = '0 0 0 4px rgba(250, 204, 21, 0.8)'
                        setTimeout(() => {
                            el.style.transition = 'box-shadow 0.5s ease-out'
                            el.style.boxShadow = 'none'
                        }, 1000)

                    } else if (attempts >= maxAttempts) {
                        clearInterval(interval)
                        console.warn(`[PDFViewer] Could not find highlight element: highlight-${fieldKey} after ${maxAttempts} attempts`)
                    }
                }, 100)
            }
        }
    }), [highlights, jumpToPage, highlight, clearHighlights, zoomPluginInstance, currentPage])

    // Highlight Rendering
    const renderHighlights = (props: RenderHighlightsProps) => {
        return (
            <div>
                {highlights
                    .filter(area => area.pageIndex === props.pageIndex)
                    .map((area, idx) => {
                        const isActive = area.fieldKey === activeFieldKey
                        const hasActive = !!activeFieldKey
                        const isDimmed = hasActive && !isActive

                        return (
                            <div
                                key={idx}
                                id={`highlight-${area.fieldKey}`}
                                className={`
                                    absolute transition-all duration-300 ease-out cursor-pointer group
                                    ${isActive ? 'z-50' : 'z-10 hover:z-20'}
                                    ${isDimmed ? 'opacity-30 grayscale' : 'opacity-100'}
                                `}
                                style={{
                                    left: `${area.position.boundingRect.x1}%`,
                                    top: `${area.position.boundingRect.y1}%`,
                                    width: `${area.position.boundingRect.width}%`,
                                    height: `${area.position.boundingRect.height}%`,
                                }}
                                title={area.content}
                                onClick={(e) => {
                                    e.stopPropagation()
                                    if (area.fieldKey) {
                                        onHighlightClick?.(area.fieldKey)
                                    }
                                }}
                            >
                                {/* The visual box - separated for better animation handling */}
                                <div
                                    className={`
                                        w-full h-full rounded-[2px] backdrop-blur-[1px]
                                        ${isActive
                                            ? 'bg-yellow-400/30 border-2 border-yellow-600 shadow-[0_0_15px_rgba(234,179,8,0.6)] animate-pulse-subtle'
                                            : 'bg-yellow-300/10 border border-yellow-500/50 hover:bg-yellow-300/20 hover:border-yellow-600'
                                        }
                                    `}
                                />

                                {/* Label Tag (Only visible on hover or active) */}
                                {(isActive || !hasActive) && (
                                    <div className={`
                                        absolute -top-6 left-0 px-1.5 py-0.5 text-[10px] font-bold text-white bg-yellow-600 rounded shadow-sm
                                        opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none
                                        ${isActive ? 'opacity-100' : ''}
                                    `}>
                                        {area.fieldKey}
                                    </div>
                                )}
                            </div>
                        )
                    })}
            </div>
        )
    }

    const highlightPluginInstance = highlightPlugin({
        renderHighlights,
    })


    const handlePrevPage = () => {
        if (currentPage > 0) {
            jumpToPage(currentPage - 1)
        }
    }

    const handleNextPage = () => {
        if (currentPage < totalPages - 1) {
            jumpToPage(currentPage + 1)
        }
    }

    return (
        <div className="w-full h-full flex flex-col bg-muted rounded-lg overflow-hidden min-h-0 border border-border">
            <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'pdf' | 'ocr')} className="flex flex-col h-full">
                {/* Header with Tabs and Toolbar */}
                <div className="flex items-center justify-between px-2 bg-muted/80 border-b border-border shrink-0">
                    <TabsList className="bg-transparent p-0 h-9">
                        <TabsTrigger
                            value="pdf"
                            className="data-[state=active]:bg-background data-[state=active]:shadow-sm rounded-t-lg rounded-b-none border-b-2 border-transparent data-[state=active]:border-primary px-4 py-2 h-full gap-2 text-xs"
                        >
                            <File className="w-3.5 h-3.5" /> PDF 원본
                        </TabsTrigger>
                        <TabsTrigger
                            value="ocr"
                            className="data-[state=active]:bg-background data-[state=active]:shadow-sm rounded-t-lg rounded-b-none border-b-2 border-transparent data-[state=active]:border-primary px-4 py-2 h-full gap-2 text-xs"
                        >
                            <FileText className="w-3.5 h-3.5" /> OCR 텍스트
                        </TabsTrigger>
                        {isBetaMode && rawTables && rawTables.length > 0 && (
                            <TabsTrigger
                                value="tables"
                                className="data-[state=active]:bg-background data-[state=active]:shadow-sm rounded-t-lg rounded-b-none border-b-2 border-transparent data-[state=active]:border-primary px-4 py-2 h-full gap-2 text-xs"
                            >
                                <FileText className="w-3.5 h-3.5" /> 표 ({rawTables.length})
                            </TabsTrigger>
                        )}
                    </TabsList>

                    {/* PDF Toolbar (Only visible in PDF tab) */}
                    {activeTab === 'pdf' && (
                        <div className="flex items-center">
                            {/* Page Nav */}
                            <div className="flex items-center gap-1 bg-background/50 rounded-md px-1 py-0.5 border">
                                <button onClick={handlePrevPage} disabled={currentPage <= 0} className="p-1 rounded hover:bg-accent disabled:opacity-30">
                                    <ChevronLeft className="w-3 h-3" />
                                </button>
                                <span className="text-[10px] font-medium w-12 text-center tabular-nums">
                                    {totalPages > 0 ? `${currentPage + 1} / ${totalPages}` : '-'}
                                </span>
                                <button onClick={handleNextPage} disabled={currentPage >= totalPages - 1} className="p-1 rounded hover:bg-accent disabled:opacity-30">
                                    <ChevronRight className="w-3 h-3" />
                                </button>
                            </div>

                            {/* Zoom Controls */}
                            <div className="flex items-center gap-0.5 ml-2">
                                <ZoomOutCtrl>
                                    {(props: RenderZoomOutProps) => (
                                        <button onClick={props.onClick} className="p-1.5 rounded hover:bg-accent text-foreground" title="축소">
                                            <ZoomOut className="w-3.5 h-3.5" />
                                        </button>
                                    )}
                                </ZoomOutCtrl>
                                <ZoomInCtrl>
                                    {(props: RenderZoomInProps) => (
                                        <button onClick={props.onClick} className="p-1.5 rounded hover:bg-accent text-foreground" title="확대">
                                            <ZoomIn className="w-3.5 h-3.5" />
                                        </button>
                                    )}
                                </ZoomInCtrl>
                                <button
                                    onClick={() => zoomPluginInstance.zoomTo(SpecialZoomLevel.PageWidth)}
                                    className="p-1.5 rounded hover:bg-accent text-foreground"
                                    title="전체보기"
                                >
                                    <RotateCcw className="w-3.5 h-3.5" />
                                </button>
                            </div>
                        </div>
                    )}
                </div>

                {/* Content Area */}
                <div className="flex-1 overflow-hidden relative bg-muted/30">
                    <TabsContent value="pdf" className="h-full mt-0 w-full absolute inset-0">
                        <Worker workerUrl="https://unpkg.com/pdfjs-dist@3.11.174/build/pdf.worker.min.js">
                            <div className="h-full w-full custom-pdf-viewer">
                                <Viewer
                                    fileUrl={fileUrl}
                                    plugins={[highlightPluginInstance, pageNavigationPluginInstance, zoomPluginInstance, searchPluginInstance]}
                                    onDocumentLoad={(e) => setTotalPages(e.doc.numPages)}
                                    onPageChange={(e) => setCurrentPage(e.currentPage)}
                                    defaultScale={SpecialZoomLevel.PageWidth}
                                />
                            </div>
                        </Worker>
                    </TabsContent>

                    <TabsContent value="ocr" className="h-full mt-0 w-full absolute inset-0 overflow-auto bg-background">
                        <OcrTextViewer ocrText={ocrText} />
                    </TabsContent>

                    {/* Tables from Document Intelligence (Beta Only) */}
                    {isBetaMode && (
                        <TabsContent value="tables" className="h-full mt-0 w-full absolute inset-0 overflow-auto bg-background">
                            <RawTableRenderer rawTables={rawTables} />
                        </TabsContent>
                    )}
                </div>
            </Tabs>
        </div>
    )
})

PDFViewer.displayName = 'PDFViewer'
