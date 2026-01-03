// Template configuration types

export interface TemplateColumn {
    field: string
    label: string
    width?: string
    align?: 'left' | 'center' | 'right'
    format?: 'text' | 'currency' | 'date' | 'percent' | 'number'
    style?: {
        color?: string
        bold?: boolean
        fontSize?: number
    }
}

export interface TemplateHeader {
    logo?: boolean
    title?: string
    subtitle?: string
    backgroundColor?: string
    textColor?: string
}

export interface TemplateFooter {
    showDate?: boolean
    pageNumbers?: boolean
    customText?: string
}

export interface TemplateAggregation {
    showTotal?: boolean
    showAverage?: boolean
    showCount?: boolean
    groupBy?: string
}

export interface TemplateStyle {
    theme: 'modern' | 'classic' | 'minimal'
    primaryColor: string
    fontSize: number
    fontFamily?: string
}

export interface TemplateConfig {
    id: string
    modelId: string
    name: string
    description?: string

    // Layout
    layout: 'table' | 'card' | 'report' | 'summary'

    // Components
    header?: TemplateHeader
    footer?: TemplateFooter
    columns: TemplateColumn[]
    aggregation?: TemplateAggregation

    // Styling
    style: TemplateStyle

    // Metadata
    createdAt?: string
    updatedAt?: string
}

// Chat message types
export interface ChatMessage {
    id: string
    role: 'user' | 'assistant'
    content: string
    config?: Partial<TemplateConfig>
    timestamp: Date
}

// Default template config
export const defaultTemplateConfig: Omit<TemplateConfig, 'id' | 'modelId'> = {
    name: '새 템플릿',
    layout: 'table',
    columns: [],
    style: {
        theme: 'modern',
        primaryColor: '#3b82f6',
        fontSize: 14
    }
}
