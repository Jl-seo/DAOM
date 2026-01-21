import { forwardRef } from 'react'
import { FileText, RefreshCw, ZoomIn, ZoomOut, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { PDFViewer, type PDFViewerHandle } from './PDFViewer'
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch'
import type { Highlight } from '../types'

interface DocumentPreviewPanelProps {
    file: File | null
    fileUrl: string | null
    highlights: Highlight[]
    selectedFieldKey: string | null
    onHighlightClick: (key: string) => void
    onRetry: () => void
}

export const DocumentPreviewPanel = forwardRef<PDFViewerHandle, DocumentPreviewPanelProps>(({
    file,
    fileUrl,
    highlights,
    selectedFieldKey,
    onHighlightClick,
    onRetry
}, ref) => {
    const isPdf = file?.type?.includes('pdf') || fileUrl?.toLowerCase().endsWith('.pdf')

    return (
        <Card className="h-full flex flex-col bg-muted/10 overflow-hidden border-0 rounded-none md:border-r">
            <div className="px-4 py-2 border-b bg-card flex justify-between items-center text-sm font-medium text-muted-foreground shrink-0">
                <span>원본 문서 미리보기</span>
                {file && <Badge variant="outline">{file.name}</Badge>}
            </div>
            <div className="flex-1 relative overflow-hidden flex items-center justify-center bg-muted/20 min-h-0">
                {fileUrl ? (
                    isPdf
                        ? <PDFViewer
                            ref={ref}
                            fileUrl={fileUrl}
                            highlights={highlights}
                            activeFieldKey={selectedFieldKey || undefined}
                            onHighlightClick={onHighlightClick}
                        />
                        : (
                            <TransformWrapper
                                initialScale={1}
                                minScale={0.5}
                                maxScale={5}
                                centerOnInit={true}
                            >
                                {({ zoomIn, zoomOut, resetTransform }) => (
                                    <div className="w-full h-full flex flex-col">
                                        {/* Image Zoom Controls */}
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
                                        {/* Zoomable Image */}
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
                        )
                ) : (
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
                )}
            </div>
        </Card>
    )
})

DocumentPreviewPanel.displayName = 'DocumentPreviewPanel'

