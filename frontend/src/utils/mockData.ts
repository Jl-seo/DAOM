import type { Model } from '../types/model'

export function generateMockData(model: Model): Record<string, any>[] {
    const mockRow: Record<string, any> = {}

    model.fields.forEach(field => {
        mockRow[field.key] = getMockValueForType(field.type)
    })

    // Return 3 sample rows
    return [mockRow, { ...mockRow }, { ...mockRow }]
}

function getMockValueForType(type: string): any {
    switch (type) {
        case 'string':
            return '샘플 텍스트'
        case 'number':
            return 12345
        case 'date':
            return '2024-01-01'
        case 'array':
            return ['항목1', '항목2', '항목3']
        default:
            return 'N/A'
    }
}
