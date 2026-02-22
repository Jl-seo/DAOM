import { useState, useEffect } from 'react'
import { FileText } from 'lucide-react'

interface OcrTextViewerProps {
    ocrText?: string
}

/**
 * Shared OCR text viewer component.
 * Shows the raw OCR-extracted text with proper formatting,
 * or an empty state when no text is available.
 * Defers rendering for massive payloads to prevent UI freezing.
 */
export function OcrTextViewer({ ocrText }: OcrTextViewerProps) {
    const [deferredText, setDeferredText] = useState<string>('')
    const [isTruncated, setIsTruncated] = useState(false)

    useEffect(() => {
        if (!ocrText) return

        // Defer rendering to prevent blocking the main thread during hydration of massive Excel payloads
        const timer = setTimeout(() => {
            if (ocrText.length > 100000) {
                setDeferredText(ocrText.slice(0, 100000))
                setIsTruncated(true)
            } else {
                setDeferredText(ocrText)
                setIsTruncated(false)
            }
        }, 100)

        return () => clearTimeout(timer)
    }, [ocrText])

    if (ocrText) {
        return (
            <div className="flex flex-col h-full w-full">
                {isTruncated && (
                    <div className="bg-yellow-500/10 text-yellow-600 text-xs p-2 text-center shrink-0 border-b border-yellow-500/20">
                        문서 텍스트가 너무 길어 시스템 보호를 위해 처음 100,000자까지만 화면에 표시됩니다. (실제 데이터 추출은 100% 정상 진행됩니다)
                    </div>
                )}
                <pre className="whitespace-pre-wrap font-mono text-sm leading-relaxed text-foreground/80 max-w-4xl mx-auto p-6 flex-1 overflow-auto">
                    {deferredText || '텍스트 렌더링 중... 잠시만 기다려주세요.'}
                </pre>
            </div>
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
