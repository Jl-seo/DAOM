import { Upload, FileCheck, CheckCircle2, type LucideIcon } from 'lucide-react'

// ==========================================
// EXTRACTION TABS
// ==========================================
export interface ExtractionTab {
    id: 'upload' | 'raw_data' | 'refined_data'
    label: string
    description: string
    icon: LucideIcon
}

export const EXTRACTION_TABS: ExtractionTab[] = [
    { id: 'upload', label: '문서 업로드', description: '분석할 문서 추가 및 스캔', icon: Upload },
    { id: 'raw_data', label: '추출 원본 (Raw Data)', description: 'AI가 원문에서 추출한 1차 데이터', icon: FileCheck },
    { id: 'refined_data', label: '최종 가공 결과', description: '정규화 및 후처리 규칙이 적용된 완성 데이터', icon: CheckCircle2 }
]

// ==========================================
// REVIEW TABS
// ==========================================
export interface ReviewTab {
    id: string
    label: string
    icon?: LucideIcon
}

export const REVIEW_TABS: ReviewTab[] = [
    { id: 'fields', label: '추출 필드' },
    { id: 'table', label: '상세 테이블' },
    { id: 'raw', label: 'Raw Data' }
]

// ==========================================
// STATUS LABELS
// ==========================================
export const STATUS_LABELS: Record<string, string> = {
    idle: '대기 중',
    uploading: '업로드 중',
    refining: '분석 중',
    previewing: '미리보기',
    complete: '완료',
    error: '오류'
}

export const STATUS_COLORS: Record<string, string> = {
    idle: 'text-muted-foreground',
    uploading: 'text-blue-500',
    refining: 'text-yellow-500',
    previewing: 'text-primary',
    complete: 'text-green-500',
    error: 'text-destructive'
}

// ==========================================
// FILE TYPES
// ==========================================
export const ACCEPTED_FILE_TYPES = ['.pdf', '.jpg', '.jpeg', '.png']
export const ACCEPTED_MIME_TYPES = ['application/pdf', 'image/jpeg', 'image/png']

// ==========================================
// POLLING CONFIG
// ==========================================
export const POLLING_INTERVAL_MS = 2000
export const MAX_POLLING_ATTEMPTS = 60 // 2 minutes max

// ==========================================
// CONFIDENCE THRESHOLDS
// ==========================================
export const CONFIDENCE_THRESHOLDS = {
    HIGH: 0.9,
    MEDIUM: 0.7,
    LOW: 0.5
}

export const getConfidenceColor = (confidence: number): string => {
    if (confidence >= CONFIDENCE_THRESHOLDS.HIGH) return 'text-chart-2'
    if (confidence >= CONFIDENCE_THRESHOLDS.MEDIUM) return 'text-chart-4'
    return 'text-destructive'
}

export const getConfidenceBadgeVariant = (confidence: number): 'secondary' | 'destructive' => {
    return confidence >= CONFIDENCE_THRESHOLDS.MEDIUM ? 'secondary' : 'destructive'
}
