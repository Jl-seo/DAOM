// API Configuration
export const API_CONFIG = {
    BASE_URL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1',
    TIMEOUT: 10000
} as const

// Data Structure Types
export const DATA_STRUCTURES = [
    {
        id: 'table' as const,
        iconName: 'FileSpreadsheet',
        label: '표',
        desc: '행/열 구조'
    },
    {
        id: 'data' as const,
        iconName: 'FileJson',
        label: '데이터',
        desc: '객체 형태'
    },
    {
        id: 'report' as const,
        iconName: 'FileText',
        label: '보고서',
        desc: '문서 형태'
    }
] as const

export type DataStructureType = typeof DATA_STRUCTURES[number]['id']

// Field Types
export const FIELD_TYPES = [
    { value: 'string' as const, label: 'Text' },
    { value: 'number' as const, label: 'Number' },
    { value: 'date' as const, label: 'Date' },
    { value: 'array' as const, label: 'Table' }
] as const

export type FieldType = typeof FIELD_TYPES[number]['value']

// Default Values
export const DEFAULTS = {
    DATA_STRUCTURE: 'data' as DataStructureType,
    FIELD_TYPE: 'string' as FieldType,
    NEW_FIELD: {
        key: '',
        label: '',
        description: '',
        rules: '',
        type: 'string' as FieldType
    },
    NEW_MODEL: {
        name: '',
        description: '',
        global_rules: '',
        data_structure: 'data' as DataStructureType,
        fields: [{
            key: '',
            label: '',
            description: '',
            rules: '',
            type: 'string' as FieldType
        }]
    }
}

// Synonyms for Smart Suggestions
export const SYNONYMS: Record<string, string[]> = {
    '구매자': ['Client', 'Customer', 'Purchaser', 'Bill To', '받는 사람'],
    '공급자': ['Seller', 'Supplier', 'Merchant', 'Payee', '보내는 사람'],
    '금액': ['Grand Total', 'Amount Due', 'Balance', '합계', '최종 금액'],
    '날짜': ['Invoice Date', 'Issue Date', '작성일', '청구일']
} as const

// Messages
export const MESSAGES = {
    CONFIRM_DELETE: '정말 이 모델을 삭제하시겠습니까?',
    SAVE_SUCCESS: '모델이 성공적으로 저장되었습니다.',
    SAVE_ERROR: '저장에 실패했습니다.'
} as const
