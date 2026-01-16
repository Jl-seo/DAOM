import { useRef, useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { GripVertical } from 'lucide-react'

import { DocumentDeck } from './DocumentDeck'
import { DocumentPreviewPanel } from './DocumentPreviewPanel'
import { DataReviewPanel } from './DataReviewPanel'
import type { PDFViewerHandle } from './PDFViewer'
import { downloadAsExcel } from '../../../utils/excel'
import type { PreviewData, ExtractionModel, Highlight } from '../types'

interface ExtractionReviewViewProps {
    // Data
    previewData: PreviewData | null
    result: Record<string, any> | null
    model: ExtractionModel
    highlights: Highlight[]

    // State
    selectedSubDocIndex: number
    selectedFieldKey: string | null

    // File info
    file: File | null
    fileUrl: string | null

    // Actions
    onSubDocSelect: (index: number) => void
    onFieldSelect: (key: string | null) => void
    onRetry: () => void
    onSave: (editedGuideData?: Record<string, any>, editedOtherData?: any[]) => void
    onReset: () => void
}

export function ExtractionReviewView({
    previewData,
    result,
    model,
    highlights,
    selectedSubDocIndex,
    selectedFieldKey,
    file,
    fileUrl,
    onSubDocSelect,
    onFieldSelect,
    onRetry,
    onReset,
    onSave
}: ExtractionReviewViewProps) {
    const pdfViewerRef = useRef<PDFViewerHandle>(null)
    const containerRef = useRef<HTMLDivElement>(null)

    const [latestData, setLatestData] = useState<{ guide: any, other: any[] } | null>(null)

    // Resizable state: left panel width percentage (0-100)
    const [leftPanelWidth, setLeftPanelWidth] = useState(50)
    const [isDragging, setIsDragging] = useState(false)

    // Get current document data based on sub-document selection
    const currentGuideExtracted = previewData?.sub_documents && previewData.sub_documents.length > 0
        ? previewData.sub_documents[selectedSubDocIndex]?.data?.guide_extracted
        : previewData?.guide_extracted

    const currentOtherData = previewData?.sub_documents && previewData.sub_documents.length > 0
        ? previewData.sub_documents[selectedSubDocIndex]?.data?.other_data
        : previewData?.other_data

    // Store callbacks in refs to prevent infinite loops from prop changes
    const onSaveRef = useRef(onSave)
    onSaveRef.current = onSave

    // Auto-Save Effect
    useEffect(() => {
        if (!latestData) return

        const timer = setTimeout(() => {
            process.env.NODE_ENV === 'development' && console.log('[AutoSave] Saving data...', latestData)
            onSaveRef.current(latestData.guide, latestData.other)
        }, 1000) // 1 second debounce

        return () => clearTimeout(timer)
    }, [latestData]) // Removed onSave from deps - use ref instead

    // Sync Scroll Effect: Data -> PDF
    useEffect(() => {
        if (selectedFieldKey && pdfViewerRef.current) {
            pdfViewerRef.current.scrollToHighlight(selectedFieldKey)
        }
    }, [selectedFieldKey])

    // Drag handlers for resizer
    const handleMouseDown = useCallback((e: React.MouseEvent) => {
        e.preventDefault()
        setIsDragging(true)
    }, [])

    const handleMouseMove = useCallback((e: MouseEvent) => {
        if (!isDragging || !containerRef.current) return

        const containerRect = containerRef.current.getBoundingClientRect()
        const newWidth = ((e.clientX - containerRect.left) / containerRect.width) * 100

        // Clamp between 20% and 80%
        setLeftPanelWidth(Math.min(80, Math.max(20, newWidth)))
    }, [isDragging])

    const handleMouseUp = useCallback(() => {
        setIsDragging(false)
    }, [])

    // Attach/detach global mouse events for dragging
    useEffect(() => {
        if (isDragging) {
            document.addEventListener('mousemove', handleMouseMove)
            document.addEventListener('mouseup', handleMouseUp)
            document.body.style.cursor = 'col-resize'
            document.body.style.userSelect = 'none'
        } else {
            document.removeEventListener('mousemove', handleMouseMove)
            document.removeEventListener('mouseup', handleMouseUp)
            document.body.style.cursor = ''
            document.body.style.userSelect = ''
        }

        return () => {
            document.removeEventListener('mousemove', handleMouseMove)
            document.removeEventListener('mouseup', handleMouseUp)
            document.body.style.cursor = ''
            document.body.style.userSelect = ''
        }
    }, [isDragging, handleMouseMove, handleMouseUp])

    const handleDownload = () => {
        // Use latest edited data if available, otherwise fall back to result or initial preview
        const dataToExport = latestData
            ? { ...latestData.guide, other_data: latestData.other }
            : (result || { ...currentGuideExtracted, other_data: currentOtherData })

        if (!dataToExport) return
        downloadAsExcel(dataToExport, `${model.name}_extraction.xlsx`)
    }

    return (
        <motion.div
            key="review"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className="h-full flex flex-row overflow-hidden"
        >
            {/* Left: Document Deck (Multi-Doc) */}
            {previewData?.sub_documents && previewData.sub_documents.length > 1 && (
                <div className="w-64 border-r shrink-0">
                    <DocumentDeck
                        subDocuments={previewData.sub_documents}
                        selectedIndex={selectedSubDocIndex}
                        onSelect={onSubDocSelect}
                    />
                </div>
            )}

            {/* Resizable Main Area */}
            <div
                ref={containerRef}
                className="flex-1 min-w-0 h-full flex flex-row relative"
            >
                {/* Left Panel: PDF Viewer */}
                <div
                    className="h-full overflow-hidden"
                    style={{ width: `${leftPanelWidth}%` }}
                >
                    <DocumentPreviewPanel
                        ref={pdfViewerRef}
                        file={file}
                        fileUrl={fileUrl}
                        highlights={highlights}
                        selectedFieldKey={selectedFieldKey}
                        onHighlightClick={onFieldSelect}
                        onRetry={onRetry}
                    />
                </div>

                {/* Resizable Handle */}
                <div
                    onMouseDown={handleMouseDown}
                    className={`
                        w-2 h-full flex items-center justify-center cursor-col-resize
                        bg-border hover:bg-primary/30 transition-colors
                        ${isDragging ? 'bg-primary/50' : ''}
                    `}
                >
                    <GripVertical className="w-3 h-3 text-muted-foreground" />
                </div>

                {/* Right Panel: Data Review */}
                <div
                    className="h-full overflow-hidden"
                    style={{ width: `calc(${100 - leftPanelWidth}% - 8px)` }}
                >
                    <DataReviewPanel
                        currentGuideExtracted={currentGuideExtracted || {}}
                        currentOtherData={currentOtherData || []}
                        model={model}
                        previewData={previewData}
                        selectedFieldKey={selectedFieldKey}
                        onFieldSelect={onFieldSelect}
                        onDataChange={setLatestData}
                        onSave={onSave}
                        onReset={onReset}
                        onRetry={onRetry}
                        onDownload={handleDownload}
                        documentId={fileUrl} // Pass fileUrl as stable identifier
                        debugData={previewData?.debug_data}
                    />
                </div>
            </div>
        </motion.div>
    )
}
