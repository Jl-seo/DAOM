import { useRef, useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { GripVertical, GripHorizontal } from 'lucide-react'
// Renamed exports in v4.4.1: PanelGroup -> Group, PanelResizeHandle -> Separator
import { Panel, Group as PanelGroup, Separator as PanelResizeHandle } from 'react-resizable-panels'

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
    const [latestData, setLatestData] = useState<{ guide: any, other: any[] } | null>(null)

    // Layout state
    const [direction, setDirection] = useState<'horizontal' | 'vertical'>('horizontal')

    useEffect(() => {
        const checkLayout = () => {
            const mobile = window.innerWidth < 768
            setDirection(mobile ? 'vertical' : 'horizontal')
        }

        checkLayout()
        window.addEventListener('resize', checkLayout)
        return () => window.removeEventListener('resize', checkLayout)
    }, [])

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
            import.meta.env.DEV && console.log('[AutoSave] Saving data...', latestData)
            onSaveRef.current(latestData.guide, latestData.other)
        }, 1000) // 1 second debounce

        return () => clearTimeout(timer)
    }, [latestData])

    // Sync Scroll Effect: Data -> PDF
    useEffect(() => {
        if (selectedFieldKey && pdfViewerRef.current) {
            pdfViewerRef.current.scrollToHighlight(selectedFieldKey)
        }
    }, [selectedFieldKey])

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
                <div className="w-64 border-r shrink-0 hidden md:block">
                    {/* Note: Document Deck hidden on mobile for now as it needs a better UI, or make it collapsible */}
                    <DocumentDeck
                        subDocuments={previewData.sub_documents}
                        selectedIndex={selectedSubDocIndex}
                        onSelect={onSubDocSelect}
                    />
                </div>
            )}

            {/* Resizable Main Area */}
            <div className="flex-1 min-w-0 h-full flex flex-col relative bg-background">
                <PanelGroup orientation={direction} className="!h-full !w-full">
                    {/* PDF Viewer Panel */}
                    <Panel defaultSize={50} minSize={25} collapsible={false} className="relative">
                        <div className="h-full w-full overflow-hidden">
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
                    </Panel>

                    <PanelResizeHandle className={direction === 'horizontal'
                        ? "w-2 bg-border hover:bg-primary/20 transition-colors flex items-center justify-center outline-none"
                        : "h-2 bg-border hover:bg-primary/20 transition-colors flex items-center justify-center outline-none"
                    }>
                        <div className="z-10 bg-background border rounded-sm p-0.5">
                            {direction === 'horizontal'
                                ? <GripVertical className="h-4 w-4 text-muted-foreground" />
                                : <GripHorizontal className="h-4 w-4 text-muted-foreground" />}
                        </div>
                    </PanelResizeHandle>

                    {/* Data Review Panel */}
                    <Panel minSize={20}>
                        <div className="h-full w-full overflow-hidden">
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
                                documentId={fileUrl}
                                debugData={previewData?.debug_data}
                            />
                        </div>
                    </Panel>
                </PanelGroup>
            </div>
        </motion.div>
    )
}
