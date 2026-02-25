/**
 * File Type Detection Utilities
 * Safely detects file types from File objects and URLs,
 * handling SAS tokens and query parameters.
 */

export type DocumentFileType = 'pdf' | 'excel' | 'image'

const PDF_EXTENSIONS = ['.pdf']
const EXCEL_EXTENSIONS = ['.xlsx', '.xls', '.csv']

/**
 * Extract the pathname from a URL, stripping query parameters.
 * Falls back to simple string split for malformed URLs.
 */
function getPathname(url: string): string {
    try {
        return new URL(url).pathname.toLowerCase()
    } catch {
        return url.toLowerCase().split('?')[0]
    }
}

function hasExtension(pathname: string, extensions: string[]): boolean {
    return extensions.some(ext => pathname.endsWith(ext))
}

/**
 * Check if a file/URL points to a PDF document.
 */
export function checkIsPdf(file: File | null, fileUrl: string | null, filename?: string | null): boolean {
    if (file?.name && hasExtension(file.name.toLowerCase(), PDF_EXTENSIONS)) return true
    if (file?.type?.includes('pdf')) return true
    if (filename && hasExtension(filename.toLowerCase(), PDF_EXTENSIONS)) return true
    if (!fileUrl) return false
    return hasExtension(getPathname(fileUrl), PDF_EXTENSIONS)
}

/**
 * Check if a file/URL points to an Excel/CSV document.
 */
export function checkIsExcel(file: File | null, fileUrl: string | null, filename?: string | null): boolean {
    if (file?.name && hasExtension(file.name.toLowerCase(), EXCEL_EXTENSIONS)) return true
    if (file?.type) {
        const t = file.type
        if (t.includes('spreadsheet') || t.includes('excel') || t === 'text/csv') return true
    }
    if (filename && hasExtension(filename.toLowerCase(), EXCEL_EXTENSIONS)) return true
    if (!fileUrl) return false
    return hasExtension(getPathname(fileUrl), EXCEL_EXTENSIONS)
}

/**
 * Determine the document type from file or URL.
 */
export function getFileType(file: File | null, fileUrl: string | null, filename?: string | null): DocumentFileType {
    if (checkIsPdf(file, fileUrl, filename)) return 'pdf'
    if (checkIsExcel(file, fileUrl, filename)) return 'excel'
    return 'image'
}
