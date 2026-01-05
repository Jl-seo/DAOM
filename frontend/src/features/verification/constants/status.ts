export const EXTRACTION_STATUS = {
    // Processing states (P-Series)
    PENDING: 'P100',
    UPLOADING: 'P200',
    ANALYZING: 'P300',
    REFINING: 'P400',
    PREVIEW_READY: 'P500',

    // Success states (S-Series)
    SUCCESS: 'S100',
    CONFIRMED: 'S200',
    COMPLETE: 'S300', // UI-only state for wizard completion

    // Error states (E-Series)
    FAILED: 'E100',
    ERROR: 'E200',
    CANCELLED: 'E300'
} as const

export type ExtractionStatusType = typeof EXTRACTION_STATUS[keyof typeof EXTRACTION_STATUS]

export const STATUS_LABELS: Record<string, string> = {
    [EXTRACTION_STATUS.PENDING]: '대기 중',
    [EXTRACTION_STATUS.UPLOADING]: '업로드 중',
    [EXTRACTION_STATUS.ANALYZING]: '문서 분석 중',
    [EXTRACTION_STATUS.REFINING]: '데이터 정제 중',
    [EXTRACTION_STATUS.PREVIEW_READY]: '임시저장',
    [EXTRACTION_STATUS.SUCCESS]: '완료',
    [EXTRACTION_STATUS.CONFIRMED]: '확정 완료',
    [EXTRACTION_STATUS.COMPLETE]: '완료',
    [EXTRACTION_STATUS.FAILED]: '실패',
    [EXTRACTION_STATUS.ERROR]: '오류',
    [EXTRACTION_STATUS.CANCELLED]: '취소됨'
}

export const STATUS_COLORS: Record<string, string> = {
    [EXTRACTION_STATUS.PENDING]: 'text-muted-foreground',
    [EXTRACTION_STATUS.UPLOADING]: 'text-chart-4',
    [EXTRACTION_STATUS.ANALYZING]: 'text-chart-4',
    [EXTRACTION_STATUS.REFINING]: 'text-chart-4',
    [EXTRACTION_STATUS.PREVIEW_READY]: 'text-chart-1',
    [EXTRACTION_STATUS.SUCCESS]: 'text-chart-2',
    [EXTRACTION_STATUS.CONFIRMED]: 'text-chart-2',
    [EXTRACTION_STATUS.COMPLETE]: 'text-chart-2',
    [EXTRACTION_STATUS.FAILED]: 'text-destructive',
    [EXTRACTION_STATUS.ERROR]: 'text-destructive',
    [EXTRACTION_STATUS.CANCELLED]: 'text-muted-foreground'
}

// Progress percentage for each status (0-100)
export const STATUS_PROGRESS: Record<string, number> = {
    [EXTRACTION_STATUS.PENDING]: 5,
    [EXTRACTION_STATUS.UPLOADING]: 15,
    [EXTRACTION_STATUS.ANALYZING]: 40,
    [EXTRACTION_STATUS.REFINING]: 75,
    [EXTRACTION_STATUS.PREVIEW_READY]: 95,
    [EXTRACTION_STATUS.SUCCESS]: 100,
    [EXTRACTION_STATUS.CONFIRMED]: 100,
    [EXTRACTION_STATUS.COMPLETE]: 100,
    [EXTRACTION_STATUS.FAILED]: 0,
    [EXTRACTION_STATUS.ERROR]: 0,
    [EXTRACTION_STATUS.CANCELLED]: 0
}

// Step number for progress display (current step / total steps)
export const STATUS_STEP: Record<string, { current: number; total: number; label: string }> = {
    [EXTRACTION_STATUS.PENDING]: { current: 1, total: 4, label: '준비 중' },
    [EXTRACTION_STATUS.UPLOADING]: { current: 1, total: 4, label: '파일 업로드' },
    [EXTRACTION_STATUS.ANALYZING]: { current: 2, total: 4, label: 'OCR 문서 분석' },
    [EXTRACTION_STATUS.REFINING]: { current: 3, total: 4, label: 'AI 데이터 정제' },
    [EXTRACTION_STATUS.PREVIEW_READY]: { current: 4, total: 4, label: '검토 대기' },
    [EXTRACTION_STATUS.SUCCESS]: { current: 4, total: 4, label: '완료' },
    [EXTRACTION_STATUS.CONFIRMED]: { current: 4, total: 4, label: '확정' },
    [EXTRACTION_STATUS.COMPLETE]: { current: 4, total: 4, label: '완료' }
}

/**
 * Checks if the status represents a successful outcome
 */
export const isSuccessStatus = (status: string): boolean => {
    return [
        EXTRACTION_STATUS.SUCCESS,
        EXTRACTION_STATUS.CONFIRMED,
        EXTRACTION_STATUS.COMPLETE,
        EXTRACTION_STATUS.PREVIEW_READY // Treat legacy P500 as success
    ].includes(status as any)
}

export const isCancelledStatus = (status: string): boolean => {
    return status === EXTRACTION_STATUS.CANCELLED
}

export const isErrorStatus = (status: string): boolean => {
    return [
        EXTRACTION_STATUS.ERROR,
        EXTRACTION_STATUS.FAILED
    ].includes(status as any)
}

export const isProcessingStatus = (status: string): boolean => {
    return [
        EXTRACTION_STATUS.PENDING,
        EXTRACTION_STATUS.UPLOADING,
        EXTRACTION_STATUS.ANALYZING,
        EXTRACTION_STATUS.REFINING
    ].includes(status as any)
}

/**
 * @deprecated Review stage is now part of Success flow
 */
export const isReviewNeededStatus = (_status: string): boolean => {
    return false
}
