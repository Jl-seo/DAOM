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
    ERROR: 'E200'
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
    [EXTRACTION_STATUS.ERROR]: '오류'
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
    [EXTRACTION_STATUS.ERROR]: 'text-destructive'
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
