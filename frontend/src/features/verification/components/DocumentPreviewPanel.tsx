import { forwardRef } from 'react'
import { FileText, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { PDFViewer, type PDFViewerHandle } from './PDFViewer'
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
    return (
        <Card className="h-full flex flex-col bg-muted/10 overflow-hidden border-0 rounded-none md:border-r">
            <div className="px-4 py-2 border-b bg-card flex justify-between items-center text-sm font-medium text-muted-foreground shrink-0">
                <span>원본 문서 미리보기</span>
                {file && <Badge variant="outline">{file.name}</Badge>}
            </div>
            <div className="flex-1 relative overflow-hidden flex items-center justify-center bg-muted/20 min-h-0">
                {fileUrl ? (
                    (file?.type?.includes('pdf') || fileUrl.toLowerCase().endsWith('.pdf'))
                        ? <PDFViewer
                            ref={ref}
                            fileUrl={fileUrl}
                            highlights={highlights}
                            activeFieldKey={selectedFieldKey || undefined}
                            onHighlightClick={onHighlightClick}
                        />
                        : <img src={fileUrl} className="max-w-full max-h-full object-contain p-4 shadow-md" alt="doc" />
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
