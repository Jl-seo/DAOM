import { FileSpreadsheet, FileJson, FileText, type LucideIcon } from 'lucide-react'

const ICON_MAP: Record<string, LucideIcon> = {
    FileSpreadsheet,
    FileJson,
    FileText
}

export function getIconComponent(iconName: string): LucideIcon {
    return ICON_MAP[iconName] || FileText
}
