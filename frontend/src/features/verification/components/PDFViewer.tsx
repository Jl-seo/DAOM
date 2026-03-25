/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useRef, useCallback, forwardRef, useImperativeHandle, useEffect } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'

import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut, RotateCcw, FileText, File } from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { OcrTextViewer } from './OcrTextViewer'
import { RawTableRenderer } from './RawTableRenderer'

// PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`

// ... Highlight Interface ...
interface Highlight {
    fieldKey?: string
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
    rawTables?: any[]
    isBetaMode?: boolean
}

export interface PDFViewerHandle {
    scrollToHighlight: (fieldKey: string) => void
}

export const PDFViewer = forwardRef<PDFViewerHandle, PDFViewerProps>(({ fileUrl, highlights = [], activeFieldKey, onHighlightClick, ocrText, rawTables = [], isBetaMode = false }, ref) => {
    const [totalPages, setTotalPages] = useState(0)
    const [currentPage, setCurrentPage] = useState(1) // 1-indexed for react-pdf
    const [scale, setScale] = useState(1.0)
    const [activeTab, setActiveTab] = useState<'pdf' | 'ocr' | 'tables'>('pdf')
    const containerRef = useRef<HTMLDivElement>(null)
    const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map())

    // Auto-fit to container width on load
    const [containerWidth, setContainerWidth] = useState<number | undefined>(undefined)

    useEffect(() => {
        if (!containerRef.current) return
        const observer = new ResizeObserver((entries) => {
            for (const entry of entries) {
                setContainerWidth(entry.contentRect.width)
            }
        })
        observer.observe(containerRef.current)
        return () => observer.disconnect()
    }, [])

    // Track visible page via IntersectionObserver
    useEffect(() => {
        if (totalPages === 0) return

        const observer = new IntersectionObserver(
            (entries) => {
                // Find the most visible page
                let maxRatio = 0
                let visiblePage = currentPage
                entries.forEach(entry => {
                    if (entry.intersectionRatio > maxRatio) {
                        maxRatio = entry.intersectionRatio
                        const pageNum = Number(entry.target.getAttribute('data-page-number'))
                        if (pageNum) visiblePage = pageNum
                    }
                })
                if (maxRatio > 0) {
                    setCurrentPage(visiblePage)
                }
            },
            {
                root: containerRef.current,
                threshold: [0, 0.25, 0.5, 0.75, 1.0],
            }
        )

        pageRefs.current.forEach((el) => {
            observer.observe(el)
        })

        return () => observer.disconnect()
    }, [totalPages, currentPage])

    const handleDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
        setTotalPages(numPages)
    }

    const jumpToPage = useCallback((pageNum: number) => {
        const el = pageRefs.current.get(pageNum)
        if (el) {
            el.scrollIntoView({ behavior: 'smooth', block: 'start' })
            setCurrentPage(pageNum)
        }
    }, [])

    const handlePrevPage = () => {
        if (currentPage > 1) jumpToPage(currentPage - 1)
    }

    const handleNextPage = () => {
        if (currentPage < totalPages) jumpToPage(currentPage + 1)
    }

    const handleZoomIn = () => setScale(s => Math.min(s + 0.25, 3.0))
    const handleZoomOut = () => setScale(s => Math.max(s - 0.25, 0.5))
    const handleFitWidth = () => setScale(1.0)

    // Expose methods to parent
    useImperativeHandle(ref, () => ({
        scrollToHighlight: (fieldKey: string) => {
            const target = highlights.find(h => h.fieldKey === fieldKey)
            if (!target) return

            // Jump to page (react-pdf uses 1-indexed)
            const targetPage = target.pageIndex + 1
            jumpToPage(targetPage)

            // Zoom in for focus
            setScale(1.5)

            // Poll for highlight element and scroll to it
            let attempts = 0
            const maxAttempts = 20
            const interval = setInterval(() => {
                attempts++
                const el = document.getElementById(`highlight-${fieldKey}`)
                if (el) {
                    clearInterval(interval)
                    el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' })
                    // Flash effect
                    el.style.boxShadow = '0 0 0 4px rgba(250, 204, 21, 0.8)'
                    setTimeout(() => {
                        el.style.transition = 'box-shadow 0.5s ease-out'
                        el.style.boxShadow = 'none'
                    }, 1000)
                } else if (attempts >= maxAttempts) {
                    clearInterval(interval)
                    console.warn(`[PDFViewer] Could not find highlight element: highlight-${fieldKey}`)
                }
            }, 100)
        }
    }), [highlights, jumpToPage])

    // Render highlight overlays for a specific page
    const renderHighlightsForPage = (pageIndex: number) => {
        const pageHighlights = highlights.filter(h => h.pageIndex === pageIndex)
        if (pageHighlights.length === 0) return null

        return (
            <div className="absolute inset-0 pointer-events-none" style={{ zIndex: 10 }}>
                {pageHighlights.map((area, idx) => {
                    const isActive = area.fieldKey === activeFieldKey
                    const hasActive = !!activeFieldKey
                    const isDimmed = hasActive && !isActive

                    return (
                        <div
                            key={idx}
                            id={`highlight-${area.fieldKey}`}
                            className={`
                                absolute transition-all duration-300 ease-out cursor-pointer group pointer-events-auto
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
                            <div
                                className={`
                                    w-full h-full rounded-[2px] backdrop-blur-[1px]
                                    ${isActive
                                        ? 'bg-yellow-400/30 border-2 border-yellow-600 shadow-[0_0_15px_rgba(234,179,8,0.6)] animate-pulse-subtle'
                                        : 'bg-yellow-300/10 border border-yellow-500/50 hover:bg-yellow-300/20 hover:border-yellow-600'
                                    }
                                `}
                            />
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

    // Calculate page width based on scale and container
    const pageWidth = containerWidth ? (containerWidth - 32) * scale : undefined

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
                                <button onClick={handlePrevPage} disabled={currentPage <= 1} className="p-1 rounded hover:bg-accent disabled:opacity-30">
                                    <ChevronLeft className="w-3 h-3" />
                                </button>
                                <span className="text-[10px] font-medium w-12 text-center tabular-nums">
                                    {totalPages > 0 ? `${currentPage} / ${totalPages}` : '-'}
                                </span>
                                <button onClick={handleNextPage} disabled={currentPage >= totalPages} className="p-1 rounded hover:bg-accent disabled:opacity-30">
                                    <ChevronRight className="w-3 h-3" />
                                </button>
                            </div>

                            {/* Zoom Controls */}
                            <div className="flex items-center gap-0.5 ml-2">
                                <button onClick={handleZoomOut} className="p-1.5 rounded hover:bg-accent text-foreground" title="축소">
                                    <ZoomOut className="w-3.5 h-3.5" />
                                </button>
                                <span className="text-[10px] font-medium w-10 text-center tabular-nums">
                                    {Math.round(scale * 100)}%
                                </span>
                                <button onClick={handleZoomIn} className="p-1.5 rounded hover:bg-accent text-foreground" title="확대">
                                    <ZoomIn className="w-3.5 h-3.5" />
                                </button>
                                <button onClick={handleFitWidth} className="p-1.5 rounded hover:bg-accent text-foreground" title="전체보기">
                                    <RotateCcw className="w-3.5 h-3.5" />
                                </button>
                            </div>
                        </div>
                    )}
                </div>

                {/* Content Area */}
                <div className="flex-1 overflow-hidden relative bg-muted/30">
                    <TabsContent value="pdf" className="h-full mt-0 w-full absolute inset-0">
                        <div
                            ref={containerRef}
                            className="h-full w-full overflow-auto custom-pdf-viewer"
                            style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', padding: '16px' }}
                        >
                            <Document
                                file={fileUrl}
                                onLoadSuccess={handleDocumentLoadSuccess}
                                loading={
                                    <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
                                        PDF 로딩 중...
                                    </div>
                                }
                                error={
                                    <div className="flex items-center justify-center h-full text-destructive text-sm">
                                        PDF를 불러올 수 없습니다.
                                    </div>
                                }
                            >
                                {Array.from({ length: totalPages }, (_, i) => i + 1).map((pageNum) => (
                                    <div
                                        key={pageNum}
                                        ref={(el) => {
                                            if (el) pageRefs.current.set(pageNum, el)
                                            else pageRefs.current.delete(pageNum)
                                        }}
                                        data-page-number={pageNum}
                                        className="relative shadow-md bg-white mb-2"
                                        style={{ display: 'inline-block' }}
                                    >
                                        <Page
                                            pageNumber={pageNum}
                                            width={pageWidth}
                                            renderTextLayer={true}
                                            renderAnnotationLayer={true}
                                        />
                                        {/* Highlight Overlays */}
                                        {renderHighlightsForPage(pageNum - 1)}
                                    </div>
                                ))}
                            </Document>
                        </div>
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
