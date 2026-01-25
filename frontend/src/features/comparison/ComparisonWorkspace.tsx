import { Split, FileDiff, CheckCircle2, ChevronRight, AlertCircle, Download, RefreshCw, Loader2, ChevronLeft, ArrowUpDown, Eye, EyeOff } from 'lucide-react'
import { clsx } from 'clsx'
import { useState, useEffect, useRef, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import * as XLSX from 'xlsx'
import type { ExcelExportColumn } from '../verification/types'

interface ComparisonResult {
    differences: Difference[]
    error?: string
    metadata?: {
        model?: string
        method?: string
        rules_applied?: boolean
        pixel_diff_count?: number
    }
}

// ... existing code ...



interface Difference {
    id: string | number
    description: string
    category: string
    location_1: number[] | null // [ymin, xmin, ymax, xmax] 0-1000
    location_2: number[] | null
    page_number?: number
    confidence?: number // 0.0 - 1.0 (신뢰도)
}

interface ComparisonData {
    candidate_index: number
    result: ComparisonResult
    file_url?: string
    filename?: string // 파일명 (optional)
    error?: string
}

// 파일 URL에서 파일명 추출 헬퍼 함수
// UUID_originalfilename 패턴이면 원본 파일명 추출, UUID만 있으면 친화적 이름으로 변경
function getFilenameFromUrl(url?: string, fallbackIndex?: number, fallbackPrefix?: string): string {
    const fallbackName = `${fallbackPrefix || 'Candidate'} ${(fallbackIndex ?? 0) + 1}`
    if (!url) return fallbackName
    try {
        const urlObj = new URL(url)
        const pathname = urlObj.pathname
        const filename = pathname.split('/').pop() || ''
        const decoded = decodeURIComponent(filename)

        // UUID_originalfilename 패턴 감지 (uuid_filename.ext 형식)
        const uuidPrefixPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_(.+)$/i
        const match = decoded.match(uuidPrefixPattern)
        if (match) {
            // UUID 뒤의 원본 파일명 추출
            const originalFilename = match[1]
            if (originalFilename.length > 30) {
                return originalFilename.slice(0, 27) + '...'
            }
            return originalFilename
        }

        // 순수 UUID 패턴 감지 (8-4-4-4-12 형식, 파일명 없음)
        const pureUuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
        if (pureUuidPattern.test(decoded)) {
            return fallbackName
        }

        // 너무 길면 자르기
        if (decoded.length > 30) {
            return decoded.slice(0, 27) + '...'
        }
        return decoded || fallbackName
    } catch {
        return fallbackName
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
    excelColumns?: ExcelExportColumn[] // Custom Excel columns
}

export function ComparisonWorkspace({
    fileUrl,
    candidateFileUrl,
    candidateFileUrls,
    comparisonResult,
    comparisons,
    onRetry,
    isRefining = false,
    excelColumns
}: ComparisonWorkspaceProps) {
    const { t } = useTranslation()
    const [selectedDifferenceId, setSelectedDifferenceId] = useState<string | number | null>(null)
    const [selectedCandidateIndex, setSelectedCandidateIndex] = useState<number>(0)

    // UI 상태: 목록 접기, 정렬, 필터
    const [isListCollapsed, setIsListCollapsed] = useState(false)
    const [isResultsCollapsed, setIsResultsCollapsed] = useState(false)
    const [sortByDiffs, setSortByDiffs] = useState(false) // true = 차이점 많은 순
    const [hideNoDiffs, setHideNoDiffs] = useState(false) // true = 차이점 없는 것 숨김

    // 모바일 탭 상태: 'images' | 'results'

    // Reset selection when comparisons change
    useEffect(() => {
        setSelectedCandidateIndex(0)
    }, [comparisons])

    // 정렬/필터된 목록 생성
    const filteredComparisons = useMemo(() => {
        if (!comparisons) return []

        let result = comparisons.map((comp, originalIndex) => ({ ...comp, originalIndex }))

        // 차이점 없는 것 필터링
        if (hideNoDiffs) {
            result = result.filter(comp => (comp.result?.differences?.length || 0) > 0)
        }

        // 차이점 순으로 정렬
        if (sortByDiffs) {
            result.sort((a, b) =>
                (b.result?.differences?.length || 0) - (a.result?.differences?.length || 0)
            )
        }

        return result
    }, [comparisons, hideNoDiffs, sortByDiffs])

    // Excel Export Handler
    const handleExportExcel = () => {
        if (!comparisons || comparisons.length === 0) {
            toast.error(t('extraction.errors.no_data_to_download'))
            return
        }

        try {
            // Collect all differences from all candidates
            const rows: { no: number; candidate: number; page: number | string; category: string; description: string; confidence: string }[] = []
            let rowNum = 1

            comparisons.forEach((comp, idx) => {
                if (comp.result?.differences) {
                    comp.result.differences.forEach(diff => {
                        rows.push({
                            no: rowNum++,
                            candidate: idx + 1,
                            page: diff.page_number || '-',
                            category: diff.category || 'unknown',
                            description: diff.description || '',
                            confidence: diff.confidence !== undefined ? `${Math.round(diff.confidence * 100)}%` : '-'
                        })
                    })
                }
            })

            if (rows.length === 0) {
                toast.info(t('comparison.export.no_diffs'))
                return
            }

            // Create worksheet
            // Default columns if not provided
            const defaultCols: ExcelExportColumn[] = [
                { key: 'no', label: t('comparison.export.no_header') || 'No', width: 8, enabled: true },
                { key: 'candidate', label: t('comparison.export.candidate_header') || 'Candidate', width: 12, enabled: true },
                { key: 'page', label: t('comparison.export.page_header') || 'Page', width: 10, enabled: true },
                { key: 'category', label: t('comparison.export.category_header') || 'Category', width: 15, enabled: true },
                { key: 'description', label: t('comparison.export.description_header') || 'Description', width: 60, enabled: true },
                { key: 'confidence', label: t('comparison.export.confidence_header') || 'Confidence', width: 10, enabled: true }
            ]

            const activeCols = (excelColumns?.length ? excelColumns : defaultCols).filter(c => c.enabled)

            const rowData = rows.map(r => {
                const row: any = {}
                activeCols.forEach(col => {
                    // Map internal keys to data keys if needed, currently they match roughly
                    // But 'page_number' in schema vs 'page' in defaults. Let's align.
                    let val: any = ''
                    if (col.key === 'page_number') val = r.page
                    else if (col.key === 'page') val = r.page
                    else val = (r as any)[col.key]

                    row[col.key] = val
                })
                return row
            })

            // Create worksheet
            const ws = XLSX.utils.json_to_sheet(rowData, {
                header: activeCols.map(c => c.key)
            })

            // Set column headers and widths
            const colWidths: { wch: number }[] = []
            activeCols.forEach((col, idx) => {
                // Header cell address (e.g. A1, B1...)
                const cellAddr = XLSX.utils.encode_cell({ r: 0, c: idx })
                if (ws[cellAddr]) {
                    ws[cellAddr].v = col.label
                    ws[cellAddr].t = 's'
                }
                colWidths.push({ wch: col.width || 15 })
            })

            ws['!cols'] = colWidths

            // Create workbook and export
            const wb = XLSX.utils.book_new()
            XLSX.utils.book_append_sheet(wb, ws, t('comparison.export.sheet_name'))
            XLSX.writeFile(wb, `comparison_results_${new Date().toISOString().slice(0, 10)}.xlsx`)

            toast.success(t('comparison.export.success'))
        } catch (err) {
            console.error('Excel export error:', err)
            toast.error(t('comparison.export.failed'))
        }
    }

    // Determine current comparison data
    // Use candidateFileUrls as fallback for panel visibility during retry
    const hasMultipleCandidates = (candidateFileUrls && candidateFileUrls.length > 1) || (comparisons && comparisons.length > 1)
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

            {/* Candidate List Panel - Show if we have multiple candidates OR multiple candidateFileUrls */}
            {hasMultipleCandidates && (
                <div className={clsx(
                    "flex flex-col gap-2 border-r shrink-0 overflow-hidden transition-all duration-200",
                    isListCollapsed ? "w-10" : "w-[220px] pr-2"
                )}>
                    {/* 접기 버튼 */}
                    <div className="flex items-center justify-between px-1">
                        {!isListCollapsed && (
                            <h3 className="text-sm font-bold text-muted-foreground">
                                {t('comparison.workspace.candidates_list') || '후보 목록'} ({filteredComparisons.length})
                            </h3>
                        )}
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setIsListCollapsed(!isListCollapsed)}
                            className="h-7 w-7 p-0"
                            title={isListCollapsed ? '목록 펼치기' : '목록 접기'}
                        >
                            {isListCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
                        </Button>
                    </div>

                    {/* 필터/정렬 버튼 (접혀있지 않을 때만) */}
                    {!isListCollapsed && (
                        <div className="flex gap-1 px-1">
                            <Button
                                variant={sortByDiffs ? "default" : "outline"}
                                size="sm"
                                onClick={() => setSortByDiffs(!sortByDiffs)}
                                className="h-6 px-2 text-xs flex-1"
                                title="차이점 많은 순 정렬"
                            >
                                <ArrowUpDown className="w-3 h-3 mr-1" />
                                정렬
                            </Button>
                            <Button
                                variant={hideNoDiffs ? "default" : "outline"}
                                size="sm"
                                onClick={() => setHideNoDiffs(!hideNoDiffs)}
                                className="h-6 px-2 text-xs flex-1"
                                title="차이점 없는 항목 숨기기"
                            >
                                {hideNoDiffs ? <Eye className="w-3 h-3 mr-1" /> : <EyeOff className="w-3 h-3 mr-1" />}
                                필터
                            </Button>
                        </div>
                    )}

                    {/* 목록 아이템 */}
                    {!isListCollapsed && (
                        <div className="flex-1 overflow-y-auto space-y-1 px-1">
                            {filteredComparisons.map((comp) => (
                                <div
                                    key={comp.originalIndex}
                                    onClick={() => setSelectedCandidateIndex(comp.originalIndex)}
                                    className={clsx(
                                        "p-2 rounded-lg text-sm cursor-pointer border hover:bg-muted/50 transition-colors flex items-center justify-between",
                                        selectedCandidateIndex === comp.originalIndex
                                            ? "bg-primary/10 border-primary text-primary font-medium"
                                            : "bg-card border-border text-foreground"
                                    )}
                                >
                                    <span className="truncate flex-1" title={comp.filename || getFilenameFromUrl(comp.file_url, comp.originalIndex)}>
                                        {comp.filename || getFilenameFromUrl(comp.file_url, comp.originalIndex)}
                                    </span>
                                    {comp.error ? (
                                        <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
                                    ) : (
                                        <div className={clsx(
                                            "flex items-center gap-1 text-xs px-1.5 py-0.5 rounded shrink-0",
                                            (comp.result?.differences?.length || 0) > 0 ? "bg-orange-100 text-orange-700" : "bg-green-100 text-green-700"
                                        )}>
                                            {comp.result?.differences?.length || 0}
                                        </div>
                                    )}
                                </div>
                            ))}
                            {filteredComparisons.length === 0 && (
                                <p className="text-xs text-muted-foreground text-center py-4">
                                    필터 조건에 맞는 항목이 없습니다
                                </p>
                            )}
                        </div>
                    )}
                </div>
            )}

            <div className="flex-1 flex flex-col md:flex-row gap-4 overflow-hidden">
                {/* Left: Image Comparison View - Desktop always, Mobile only when tab is 'images' */}
                <div className={clsx(
                    "flex flex-col gap-4 overflow-hidden",
                    "md:flex-1",
                    "flex-1" // 모바일에서도 항상 표시 (상하 배치)
                )}>
                    <div className="flex items-center justify-between shrink-0 px-2">
                        <h3 className="text-lg font-bold flex items-center gap-2">
                            <Split className="w-5 h-5 text-primary" />
                            {t('comparison.title.workspace')}
                            <span className="text-sm font-normal text-muted-foreground ml-2">
                                ({isMultiMode ? t('comparison.workspace.subtitle_multi', { index: selectedCandidateIndex + 1 }) : t('comparison.workspace.subtitle_single')})
                            </span>
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
                            <div className="relative flex-1 bg-white rounded-lg border overflow-auto flex items-center justify-center">
                                <div style={{ transform: `scale(${zoom})`, transformOrigin: 'top left', position: 'relative', display: 'inline-block' }}>
                                    <img
                                        ref={baselineImgRef}
                                        src={fileUrl}
                                        alt="Baseline"
                                        className="max-w-full max-h-full cursor-zoom-in block"
                                        loading="lazy"
                                        decoding="async"
                                        onClick={() => setExpandedImage(fileUrl)}
                                    />
                                    {/* Overlay for diffs - positioned absolutely over the image */}
                                    <svg className="absolute inset-0 w-full h-full pointer-events-none" style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }}>
                                        {currentComparison?.differences?.map((diff, idx) => {
                                            const loc = diff.location_1; // [y1, x1, y2, x2] normalized 0-1
                                            if (!loc) return null;
                                            const [y1, x1, y2, x2] = loc;
                                            // Backend returns 0-1. If logic says 0-1000, verify. 
                                            // Assuming 0-1 based on my pixel_diff implementation.
                                            // If the values are > 1, assume 0-1000 and divide.
                                            let ny1 = y1, nx1 = x1, ny2 = y2, nx2 = x2;
                                            if (y1 > 1 || x1 > 1) { ny1 /= 1000; nx1 /= 1000; ny2 /= 1000; nx2 /= 1000; }

                                            const isSelected = selectedDifferenceId === diff.id;

                                            return (
                                                <rect
                                                    key={diff.id || idx}
                                                    x={`${nx1 * 100}%`}
                                                    y={`${ny1 * 100}%`}
                                                    width={`${(nx2 - nx1) * 100}%`}
                                                    height={`${(ny2 - ny1) * 100}%`}
                                                    fill={isSelected ? "rgba(255, 0, 0, 0.2)" : "rgba(255, 0, 0, 0.05)"}
                                                    stroke={isSelected ? "red" : "rgba(255, 0, 0, 0.5)"}
                                                    strokeWidth={isSelected ? (2 / zoom) : (1 / zoom)}
                                                    className="pointer-events-auto cursor-pointer hover:fill-red-500/30 transition-all"
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        setSelectedDifferenceId(diff.id);
                                                    }}
                                                >
                                                    <title>{diff.description}</title>
                                                </rect>
                                            );
                                        })}
                                    </svg>
                                </div>
                            </div>
                        </div>

                        {/* Candidate Image */}
                        <div className="flex-1 flex flex-col gap-2 relative">
                            <div className="text-xs font-bold text-center bg-card py-1 rounded-t-lg border-b truncate px-2" title={isMultiMode ? getFilenameFromUrl(currentCandidateUrl, selectedCandidateIndex) : ''}>
                                {t('comparison.workspace.candidate')}: {isMultiMode ? (comparisons?.[selectedCandidateIndex]?.filename || getFilenameFromUrl(currentCandidateUrl, selectedCandidateIndex)) : t('comparison.workspace.single_file') || '단일 파일'}
                            </div>
                            <div className="relative flex-1 bg-white rounded-lg border overflow-auto flex items-center justify-center">
                                {currentCandidateUrl ? (
                                    <div style={{ transform: `scale(${zoom})`, transformOrigin: 'top left', position: 'relative', display: 'inline-block' }}>
                                        <img
                                            ref={candidateImgRef}
                                            src={currentCandidateUrl}
                                            alt="Candidate"
                                            className="max-w-full max-h-full cursor-zoom-in block"
                                            loading="lazy"
                                            decoding="async"
                                            onClick={() => setExpandedImage(currentCandidateUrl)}
                                        />
                                        {/* Overlay for diffs - positioned absolutely over the image */}
                                        <svg className="absolute inset-0 w-full h-full pointer-events-none" style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }}>
                                            {currentComparison?.differences?.map((diff, idx) => {
                                                const loc = diff.location_2 || diff.location_1;
                                                if (!loc) return null;
                                                const [y1, x1, y2, x2] = loc;
                                                let ny1 = y1, nx1 = x1, ny2 = y2, nx2 = x2;
                                                if (y1 > 1 || x1 > 1) { ny1 /= 1000; nx1 /= 1000; ny2 /= 1000; nx2 /= 1000; }

                                                const isSelected = selectedDifferenceId === diff.id;

                                                return (
                                                    <rect
                                                        key={diff.id || idx}
                                                        x={`${nx1 * 100}%`}
                                                        y={`${ny1 * 100}%`}
                                                        width={`${(nx2 - nx1) * 100}%`}
                                                        height={`${(ny2 - ny1) * 100}%`}
                                                        fill={isSelected ? "rgba(255, 0, 0, 0.2)" : "rgba(255, 0, 0, 0.05)"}
                                                        stroke={isSelected ? "red" : "rgba(255, 0, 0, 0.5)"}
                                                        strokeWidth={isSelected ? (2 / zoom) : (1 / zoom)}
                                                        className="pointer-events-auto cursor-pointer hover:fill-red-500/30 transition-all"
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            setSelectedDifferenceId(diff.id);
                                                        }}
                                                    >
                                                        <title>{diff.description}</title>
                                                    </rect>
                                                );
                                            })}
                                        </svg>
                                    </div>
                                ) : (
                                    <div className="flex items-center justify-center h-full text-muted-foreground">
                                        {t('comparison.workspace.no_image') || '이미지 없음'}
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
            </div>

            {/* Right: Difference List - Desktop always, Mobile only when tab is 'results' */}
            <div className={clsx(
                "flex flex-col gap-4 overflow-hidden transition-all duration-200",
                isResultsCollapsed ? "w-10 md:w-12" : "md:w-[400px]",
                "md:shrink-0 md:border-l",
                isResultsCollapsed ? "" : "md:pl-4",
                "flex-1 md:flex-none" // 모바일에서도 항상 표시 (상하 배치)
            )}>
                <div className="flex items-center justify-between shrink-0">
                    {!isResultsCollapsed && (
                        <h3 className="text-lg font-bold flex items-center gap-2">
                            <FileDiff className="w-5 h-5" />
                            {t('comparison.workspace.analysis_results')}
                        </h3>
                    )}
                    <div className="flex gap-2">
                        {!isResultsCollapsed && onRetry && (
                            <Button variant="outline" size="sm" onClick={onRetry}>
                                <RefreshCw className="w-4 h-4 mr-1" />
                                {t('common.actions.retry') || '재시도'}
                            </Button>
                        )}
                        {!isResultsCollapsed && (
                            <Button variant="outline" size="sm" onClick={handleExportExcel}>
                                <Download className="w-4 h-4 mr-1" />
                                Excel
                            </Button>
                        )}
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setIsResultsCollapsed(!isResultsCollapsed)}
                            className="shrink-0"
                        >
                            {isResultsCollapsed ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                        </Button>
                    </div>
                </div>

                {!isResultsCollapsed && (
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

                        {currentComparison?.differences?.map((diff) => (
                            <div
                                key={diff.id}
                                onClick={() => setSelectedDifferenceId(selectedDifferenceId === diff.id ? null : diff.id)}
                                className={clsx(
                                    "group bg-card border rounded-lg p-3 cursor-pointer transition-all hover:shadow-md",
                                    selectedDifferenceId === diff.id ? "ring-2 ring-primary border-transparent" : "hover:border-primary/50"
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
                                        {/* 신뢰도 표시 (개선된 UI) */}
                                        {diff.confidence !== undefined && (
                                            <div
                                                className={clsx(
                                                    "flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full border shadow-sm",
                                                    diff.confidence >= 0.8 ? "bg-green-50 text-green-700 border-green-200" :
                                                        diff.confidence >= 0.5 ? "bg-amber-50 text-amber-700 border-amber-200" :
                                                            "bg-slate-50 text-slate-500 border-slate-200"
                                                )}
                                                title={`AI 신뢰도: ${Math.round(diff.confidence * 100)}%`}
                                            >
                                                {diff.confidence >= 0.8 ? <CheckCircle2 className="w-3 h-3" /> :
                                                    diff.confidence >= 0.5 ? <AlertCircle className="w-3 h-3" /> :
                                                        <div className="w-3 h-3 rounded-full bg-slate-300" />}
                                                <span>
                                                    {diff.confidence >= 0.8 ? '확실함' :
                                                        diff.confidence >= 0.5 ? '검토 필요' :
                                                            '낮은 가능성'}
                                                </span>
                                            </div>
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
                )}
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
