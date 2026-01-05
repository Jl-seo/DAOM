/**
 * Date formatting utilities
 */

/**
 * Format ISO date string to localized display format
 */
export function formatDate(isoString: string, locale = 'ko-KR'): string {
    try {
        return new Date(isoString).toLocaleString(locale, {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        })
    } catch {
        return isoString
    }
}

/**
 * Format date for compact display (yy.MM.dd HH:mm)
 */
export function formatDateCompact(isoString: string): string {
    try {
        const date = new Date(isoString)
        const yy = date.getFullYear().toString().slice(-2)
        const MM = (date.getMonth() + 1).toString().padStart(2, '0')
        const dd = date.getDate().toString().padStart(2, '0')
        const HH = date.getHours().toString().padStart(2, '0')
        const mm = date.getMinutes().toString().padStart(2, '0')
        return `${yy}.${MM}.${dd} ${HH}:${mm}`
    } catch {
        return isoString
    }
}

/**
 * Get relative time string (e.g., "3분 전", "2시간 전")
 */
export function formatRelativeTime(isoString: string): string {
    try {
        const date = new Date(isoString)
        const now = new Date()
        const diffMs = now.getTime() - date.getTime()
        const diffMins = Math.floor(diffMs / 60000)
        const diffHours = Math.floor(diffMs / 3600000)
        const diffDays = Math.floor(diffMs / 86400000)

        if (diffMins < 1) return '방금 전'
        if (diffMins < 60) return `${diffMins}분 전`
        if (diffHours < 24) return `${diffHours}시간 전`
        if (diffDays < 7) return `${diffDays}일 전`

        return formatDateCompact(isoString)
    } catch {
        return isoString
    }
}
