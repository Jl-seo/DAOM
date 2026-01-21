import { Split, FileDiff, CheckCircle2, ChevronRight, AlertCircle, Download, RefreshCw, Loader2 } from 'lucide-react'
import { clsx } from 'clsx'
import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import * as XLSX from 'xlsx'

interface ComparisonResult {
    differences: Difference[]
    error?: string
}

interface Difference {
    id: string | number
    description: string
    category: string
    location_1: number[] | null // [ymin, xmin, ymax, xmax] 0-1000
    location_2: number[] | null
    page_number?: number
}

interface ComparisonData {
    candidate_index: number
    result: ComparisonResult
    file_url?: string
    filename?: string // 파일명 (optional)
    error?: string
}

// 파일 URL에서 파일명 추출 헬퍼 함수
function getFilenameFromUrl(url?: string, fallbackIndex?: number): string {
    if (!url) return `파일 ${(fallbackIndex || 0) + 1}`
    try {
        const urlObj = new URL(url)
        const pathname = urlObj.pathname
        const filename = pathname.split('/').pop() || ''
        // URL 디코딩하고 확장자 제거
        const decoded = decodeURIComponent(filename)
        // 너무 길면 자르기
        if (decoded.length > 30) {
            return decoded.slice(0, 27) + '...'
        }
        return decoded || `파일 ${(fallbackIndex || 0) + 1}`
    } catch {
        return `파일 ${(fallbackIndex || 0) + 1}`
    }
}

interface ComparisonWorkspaceProps {
    fileUrl: string
    candidateFileUrl: string // Legacy single URL
    candidateFileUrls?: string[] | null // Multi URLs
    comparisonResult: ComparisonResult | null // Legacy single result
    comparisons?: ComparisonData[] // Multi results
    onRetry?: () => void // Retry callback
    isRefining?: boolean // 재시도 중 로딩 상태
}

export function ComparisonWorkspace({
    fileUrl,
    candidateFileUrl,
    candidateFileUrls,
    comparisonResult,
    comparisons,
    onRetry,
    isRefining = false
}: ComparisonWorkspaceProps) {
    const { t } = useTranslation()
    const [selectedDiffId, setSelectedDiffId] = useState<string | number | null>(null)
    const [selectedCandidateIndex, setSelectedCandidateIndex] = useState<number>(0)

    // Reset selection when comparisons change
    useEffect(() => {
        setSelectedCandidateIndex(0)
    }, [comparisons])

    // Excel Export Handler
    const handleExportExcel = () => {
        if (!comparisons || comparisons.length === 0) {
            toast.error('내보낼 데이터가 없습니다')
            return
        }

        try {
            // Collect all differences from all candidates
            const rows: { no: number; candidate: number; page: number | string; category: string; description: string }[] = []
            let rowNum = 1

            comparisons.forEach((comp, idx) => {
                if (comp.result?.differences) {
                    comp.result.differences.forEach(diff => {
                        rows.push({
                            no: rowNum++,
                            candidate: idx + 1,
                            page: diff.page_number || '-',
                            category: diff.category || 'unknown',
                            description: diff.description || ''
                        })
                    })
                }
            })

            if (rows.length === 0) {
                toast.info('차이점이 없습니다')
                return
            }

            // Create worksheet
            const ws = XLSX.utils.json_to_sheet(rows, {
                header: ['no', 'candidate', 'page', 'category', 'description']
            })

            // Set column headers in Korean
            ws['A1'] = { v: 'No.', t: 's' }
            ws['B1'] = { v: '비교 대상', t: 's' }
            ws['C1'] = { v: '페이지', t: 's' }
            ws['D1'] = { v: '유형', t: 's' }
            ws['E1'] = { v: '차이점 설명', t: 's' }

            // Set column widths
            ws['!cols'] = [
                { wch: 8 },   // id
                { wch: 12 },  // candidate
                { wch: 10 },  // page
                { wch: 15 },  // category
                { wch: 60 }   // description
            ]

            // Create workbook and export
            const wb = XLSX.utils.book_new()
            XLSX.utils.book_append_sheet(wb, ws, '비교 결과')
            XLSX.writeFile(wb, `comparison_results_${new Date().toISOString().slice(0, 10)}.xlsx`)

            toast.success('Excel 파일이 다운로드되었습니다')
        } catch (err) {
            console.error('Excel export error:', err)
            toast.error('Excel 내보내기 실패')
        }
    }

    // Determine current comparison data
    const isMultiMode = comparisons && comparisons.length > 0

    // Get current candidate data
    const currentComparison = isMultiMode
        ? comparisons[selectedCandidateIndex]?.result
        : comparisonResult

    const currentCandidateUrl = isMultiMode
        ? (comparisons[selectedCandidateIndex]?.file_url || candidateFileUrls?.[selectedCandidateIndex])
        : candidateFileUrl

    const currentError = isMultiMode
        ? comparisons[selectedCandidateIndex]?.error
        : null



    const baselineImgRef = useRef<HTMLImageElement>(null)
    const candidateImgRef = useRef<HTMLImageElement>(null)



    const [zoom, setZoom] = useState(1)

    const handleZoomIn = () => setZoom(prev => Math.min(prev + 0.5, 5))
    const handleZoomOut = () => setZoom(prev => Math.max(prev - 0.5, 1))
    const handleResetZoom = () => setZoom(1)

    // Full screen image view state
    const [expandedImage, setExpandedImage] = useState<string | null>(null)

    return (
        <div className="flex h-full gap-6 p-6 relative">
            {/* 재시도 중 로딩 오버레이 */}
            {isRefining && (
                <div className="absolute inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center">
                    <div className="flex flex-col items-center gap-3 text-center">
                        <Loader2 className="w-10 h-10 animate-spin text-primary" />
                        <p className="text-lg font-medium">{t('common.messages.refining') || '재추출 중...'}</p>
                        <p className="text-sm text-muted-foreground">새로운 비교 결과가 곧 표시됩니다</p>
                    </div>
                </div>
            )}

            {/* Optional: Candidate List (if multiple) */}
            {isMultiMode && (comparisons.length > 1) && (
                <div className="w-[200px] flex flex-col gap-2 border-r pr-2 shrink-0 overflow-y-auto">
                    <h3 className="text-sm font-bold text-muted-foreground mb-2 px-1">{t('comparison.workspace.candidates_list')}</h3>
                    {comparisons.map((comp, idx) => (
                        <div
                            key={idx}
                            onClick={() => setSelectedCandidateIndex(idx)}
                            className={clsx(
                                "p-2 rounded-lg text-sm cursor-pointer border hover:bg-muted/50 transition-colors flex items-center justify-between",
                                selectedCandidateIndex === idx
                                    ? "bg-primary/10 border-primary text-primary font-medium"
                                    : "bg-card border-border text-foreground"
                            )}
                        >
                            <span className="truncate flex-1" title={getFilenameFromUrl(comp.file_url, idx)}>
                                {comp.filename || getFilenameFromUrl(comp.file_url, idx)}
                            </span>
                            {comp.error ? (
                                <AlertCircle className="w-4 h-4 text-red-500" />
                            ) : (
                                <div className="flex items-center gap-1 text-xs px-1.5 py-0.5 bg-muted rounded">
                                    {comp.result?.differences?.length || 0} {t('comparison.workspace.diffs') || '차이점'}
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {/* Left: Image Comparison View */}
            <div className="flex-1 flex flex-col gap-4 overflow-hidden">
                <div className="flex items-center justify-between shrink-0 px-2">
                    <h3 className="text-lg font-bold flex items-center gap-2">
                        <Split className="w-5 h-5 text-primary" />
                        {t('comparison.title.workspace')} ({isMultiMode ? t('comparison.workspace.subtitle_multi', { index: selectedCandidateIndex + 1 }) : t('comparison.workspace.subtitle_single')})
                    </h3>
                    <div className="flex items-center gap-2">
                        <div className="flex items-center gap-1 bg-muted rounded-md p-1 mr-4">
                            <Button variant="ghost" size="sm" onClick={handleZoomOut} disabled={zoom <= 1} className="h-6 w-6 p-0 hover:bg-background">
                                <span className="text-lg font-bold leading-none mb-0.5">-</span>
                            </Button>
                            <span className="text-xs font-mono w-10 text-center">{Math.round(zoom * 100)}%</span>
                            <Button variant="ghost" size="sm" onClick={handleZoomIn} disabled={zoom >= 5} className="h-6 w-6 p-0 hover:bg-background">
                                <span className="text-lg font-bold leading-none mb-0.5">+</span>
                            </Button>
                            <Button variant="ghost" size="sm" onClick={handleResetZoom} disabled={zoom === 1} className="h-6 px-2 text-[10px] hover:bg-background">
                                {t('common.actions.reset') || '초기화'}
                            </Button>
                        </div>
                        <div className="text-xs text-muted-foreground">
                            {t('comparison.workspace.diffs_count', { count: currentComparison?.differences?.length || 0 })}
                        </div>
                    </div>
                </div>

                <div className="flex-1 flex gap-2 overflow-hidden bg-muted/30 rounded-xl p-2">
                    {/* Baseline Image */}
                    <div className="flex-1 flex flex-col gap-2 relative">
                        <div className="text-xs font-bold text-center bg-card py-1 rounded-t-lg border-b">
                            {t('comparison.workspace.baseline')}
                        </div>
                        <div className="relative flex-1 bg-white rounded-lg border overflow-auto">
                            <div style={{ transform: `scale(${zoom})`, transformOrigin: 'top left', width: '100%', height: '100%' }}>
                                <img
                                    ref={baselineImgRef}
                                    src={fileUrl}
                                    alt="Baseline"
                                    className="w-full h-full object-contain cursor-zoom-in"
                                    onClick={() => setExpandedImage(fileUrl)}
                                />
                            </div>
                        </div>
                    </div>

                    {/* Candidate Image */}
                    <div className="flex-1 flex flex-col gap-2 relative">
                        <div className="text-xs font-bold text-center bg-card py-1 rounded-t-lg border-b truncate px-2" title={isMultiMode ? getFilenameFromUrl(currentCandidateUrl, selectedCandidateIndex) : ''}>
                            {t('comparison.workspace.candidate')}: {isMultiMode ? (comparisons?.[selectedCandidateIndex]?.filename || getFilenameFromUrl(currentCandidateUrl, selectedCandidateIndex)) : t('comparison.workspace.single_file') || '단일 파일'}
                        </div>
                        <div className="relative flex-1 bg-white rounded-lg border overflow-auto">
                            {currentCandidateUrl ? (
                                <div style={{ transform: `scale(${zoom})`, transformOrigin: 'top left', width: '100%', height: '100%' }}>
                                    <img
                                        ref={candidateImgRef}
                                        src={currentCandidateUrl}
                                        alt="Candidate"
                                        className="w-full h-full object-contain cursor-zoom-in"
                                        onClick={() => setExpandedImage(currentCandidateUrl)}
                                    />
                                </div>
                            ) : (
                                <div className="flex items-center justify-center h-full text-muted-foreground">
                                    No Image
                                </div>
                            )}

                            {/* Error Overlay */}
                            {currentError && (
                                <div className="absolute inset-0 flex items-center justify-center bg-black/50 text-white p-4 text-center">
                                    <div>
                                        <AlertCircle className="w-10 h-10 mx-auto mb-2 text-red-400" />
                                        <p>{t('comparison.workspace.error')}</p>
                                        <p className="text-sm opacity-80">{currentError}</p>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </div>

            {/* Right: Difference List */}
            <div className="w-[400px] flex flex-col gap-4 overflow-hidden shrink-0 border-l pl-4">
                <div className="flex items-center justify-between shrink-0">
                    <h3 className="text-lg font-bold flex items-center gap-2">
                        <FileDiff className="w-5 h-5" />
                        {t('comparison.workspace.analysis_results')}
                    </h3>
                    <div className="flex gap-2">
                        {onRetry && (
                            <Button variant="outline" size="sm" onClick={onRetry}>
                                <RefreshCw className="w-4 h-4 mr-1" />
                                {t('common.actions.retry') || '재시도'}
                            </Button>
                        )}
                        <Button variant="outline" size="sm" onClick={handleExportExcel}>
                            <Download className="w-4 h-4 mr-1" />
                            Excel
                        </Button>
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto custom-scrollbar space-y-3 pr-2">
                    {/* Empty State */}
                    {(!currentComparison || currentComparison.differences?.length === 0) && !currentError && (
                        <div className="text-center py-10 text-muted-foreground">
                            <CheckCircle2 className="w-10 h-10 mx-auto mb-3 opacity-20" />
                            <p>{t('comparison.workspace.no_differences')}</p>
                            <p className="text-xs">{t('comparison.workspace.identical_docs')}</p>
                        </div>
                    )}

                    {/* Error State */}
                    {currentError && (
                        <div className="text-center py-10 text-red-500">
                            <AlertCircle className="w-10 h-10 mx-auto mb-3 opacity-50" />
                            <p>{t('comparison.workspace.error')}</p>
                        </div>
                    )}

                    {currentComparison?.differences.map((diff) => (
                        <div
                            key={diff.id}
                            onClick={() => setSelectedDiffId(selectedDiffId === diff.id ? null : diff.id)}
                            className={clsx(
                                "group bg-card border rounded-lg p-3 cursor-pointer transition-all hover:shadow-md",
                                selectedDiffId === diff.id ? "ring-2 ring-primary border-transparent" : "hover:border-primary/50"
                            )}
                        >
                            <div className="flex items-start justify-between mb-2">
                                <div className="flex items-center gap-2">
                                    <span className={clsx(
                                        "text-[10px] font-bold px-2 py-0.5 rounded-full uppercase",
                                        diff.category === 'content' ? "bg-red-100 text-red-600" :
                                            diff.category === 'layout' ? "bg-blue-100 text-blue-600" :
                                                "bg-gray-100 text-gray-600"
                                    )}>
                                        {t(`comparison.categories.${diff.category}`) || diff.category}
                                    </span>
                                    {diff.page_number && (
                                        <span className="text-[10px] font-medium text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                                            {t('comparison.workspace.page')} {diff.page_number}
                                        </span>
                                    )}
                                </div>
                                <span className="text-xs text-muted-foreground">#{diff.id}</span>
                            </div>
                            <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">
                                {diff.description}
                            </p>
                            <div className="mt-2 flex items-center justify-end opacity-0 group-hover:opacity-100 transition-opacity">
                                <span className="text-xs text-primary font-medium flex items-center">
                                    {t('comparison.workspace.check_location')} <ChevronRight className="w-3 h-3 ml-1" />
                                </span>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Expanded Image Modal */}
            {expandedImage && (
                <div
                    className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4"
                    onClick={() => setExpandedImage(null)}
                >
                    <div className="relative max-w-[90vw] max-h-[90vh] w-full h-full flex items-center justify-center">
                        <img
                            src={expandedImage}
                            alt="Expanded View"
                            className="max-w-full max-h-full object-contain"
                        />
                        <Button
                            variant="ghost"
                            size="sm"
                            className="absolute top-4 right-4 text-white hover:bg-white/20"
                            onClick={() => setExpandedImage(null)}
                        >
                            Close
                        </Button>
                    </div>
                </div>
            )}
        </div>
    )
}
