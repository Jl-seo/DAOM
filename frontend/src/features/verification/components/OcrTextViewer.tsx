import { FileText } from 'lucide-react'

interface OcrTextViewerProps {
    ocrText?: string
}

/**
 * Shared OCR text viewer component.
 * Shows the raw OCR-extracted text with proper formatting,
 * or an empty state when no text is available.
 */
export function OcrTextViewer({ ocrText }: OcrTextViewerProps) {
    if (ocrText) {
        return (
            <pre className="whitespace-pre-wrap font-mono text-sm leading-relaxed text-foreground/80 max-w-4xl mx-auto p-6">
                {ocrText}
            </pre>
        )
    }

    return (
        <div className="flex flex-col items-center justify-center h-full text-muted-foreground p-8 text-center">
            <FileText className="w-12 h-12 mb-4 opacity-20" />
            <p>OCR 텍스트가 없습니다.</p>
            <p className="text-xs mt-2 opacity-60">
                문서가 아직 분석되지 않았거나 텍스트를 추출할 수 없습니다.
            </p>
        </div>
    )
}
