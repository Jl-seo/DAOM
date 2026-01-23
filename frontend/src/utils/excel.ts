import * as XLSX from 'xlsx'

/**
 * Helper to recursively extract value from { value, confidence } wrapper
 * Returns the inner value or the original if not wrapped
 * Filters out internal fields like bbox, confidence, source_text, page_number, page
 */
const INTERNAL_FIELDS = new Set([
    'bbox', 'bounding_box', 'confidence', 'source_text',
    'page_number', 'page', 'ocr_text', 'raw_text', 'debug_data',
    'other_data', 'sub_documents', 'field_meta', 'extraction_meta'
])

/**
 * Check if a key is an internal/debug field that should be excluded from Excel
 */
function isInternalField(key: string): boolean {
    // Keys starting with underscore are internal
    if (key.startsWith('_')) return true
    // Check against known internal fields
    return INTERNAL_FIELDS.has(key)
}

function extractValue(val: any): any {
    if (val === null || val === undefined) return val

    // If it's a wrapper object with 'value' property, extract just the value
    if (typeof val === 'object' && !Array.isArray(val) && 'value' in val) {
        return extractValue(val.value) // Recursive unwrapping
    }

    // If it's an object that only contains internal fields + value, extract value
    if (typeof val === 'object' && !Array.isArray(val)) {
        const keys = Object.keys(val)
        const nonInternalKeys = keys.filter(k => !isInternalField(k))

        // If all non-internal keys are just 'value', extract it
        if (nonInternalKeys.length === 1 && nonInternalKeys[0] === 'value') {
            return extractValue(val.value)
        }

        // If object contains internal fields mixed with other data, filter them out
        if (keys.some(k => isInternalField(k))) {
            const filtered: Record<string, any> = {}
            for (const k of keys) {
                if (!isInternalField(k)) {
                    filtered[k] = extractValue(val[k])
                }
            }
            // If filtered object only has one key 'value', extract it
            if (Object.keys(filtered).length === 1 && 'value' in filtered) {
                return filtered.value
            }
            // If empty after filtering, return empty string
            if (Object.keys(filtered).length === 0) {
                return ''
            }
            return filtered
        }
    }

    return val
}

/**
 * Truncate cell value to Excel's max character limit (32767)
 * Leave some room for safety
 */
const MAX_CELL_LENGTH = 32000

function truncateCellValue(value: any): any {
    if (typeof value === 'string' && value.length > MAX_CELL_LENGTH) {
        return value.substring(0, MAX_CELL_LENGTH) + '... (truncated)'
    }
    return value
}

/**
 * Flattens a single data object into multiple rows (Master-Detail)
 * - Single values (Head) are repeated on every row
 * - Array values (Line Items) create new rows
 */
function flattenDataToRows(data: Record<string, any>): Record<string, any>[] {
    const singleData: Record<string, any> = {}
    const arrayData: Record<string, any[]> = {}

    // 1. Analyze and Separate Data
    Object.entries(data).forEach(([key, rawVal]) => {
        // Skip internal/debug fields entirely
        if (isInternalField(key)) return

        const val = extractValue(rawVal)

        if (Array.isArray(val) && val.length > 0) {
            arrayData[key] = val
        } else if (Array.isArray(val) && val.length === 0) {
            // Empty array -> treat as empty single value to ensure column header exists
            singleData[key] = ""
        } else {
            // Single value (or object that isn't an array)
            // Flatten objects if needed, but for now stringify complex objects
            if (val !== null && val !== undefined) {
                singleData[key] = truncateCellValue(typeof val === 'object' ? JSON.stringify(val) : val)
            } else {
                singleData[key] = ""
            }
        }
    })

    // 2. Determine Row Count (Max length of any array)
    const arrayKeys = Object.keys(arrayData)
    const maxRows = arrayKeys.reduce((max, key) => Math.max(max, arrayData[key].length), 0) || 1

    // 3. Generate Rows
    const rows: Record<string, any>[] = []

    for (let i = 0; i < maxRows; i++) {
        const row: Record<string, any> = { ...singleData }

        arrayKeys.forEach(key => {
            const list = arrayData[key]
            // Get item safely (arrays might have different lengths)
            const rawItem = list[i]

            if (rawItem !== undefined && rawItem !== null) {
                const item = extractValue(rawItem)

                if (typeof item === 'object' && item !== null) {
                    // Flatten object properties: listKey.subKey
                    Object.entries(item).forEach(([subKey, subVal]) => {
                        const extractedSubVal = extractValue(subVal)
                        const cellValue = typeof extractedSubVal === 'object'
                            ? JSON.stringify(extractedSubVal)
                            : extractedSubVal

                        row[`${key}.${subKey}`] = truncateCellValue(cellValue)
                    })
                } else {
                    // Primitive value
                    row[key] = truncateCellValue(item)
                }
            }
        })

        rows.push(row)
    }

    return rows
}

/**
 * 추출된 데이터를 Excel 파일로 다운로드
 * Supports Master-Detail flattening for arrays (e.g. Line Items)
 */
export function downloadAsExcel(
    data: Record<string, any> | Record<string, any>[],
    filename: string = 'extracted_data'
): void {
    try {
        // Input parsing: Ensure array of objects
        const inputData = Array.isArray(data) ? data : [data]

        // Process each input object and flatten
        let allRows: Record<string, any>[] = []
        inputData.forEach(item => {
            allRows = allRows.concat(flattenDataToRows(item))
        })

        if (allRows.length === 0) {
            console.warn('No data to download')
            return
        }

        // 워크북 생성
        const worksheet = XLSX.utils.json_to_sheet(allRows)
        const workbook = XLSX.utils.book_new()
        XLSX.utils.book_append_sheet(workbook, worksheet, '추출 데이터')

        // 컬럼 너비 자동 조정
        const maxWidths: number[] = []
        // Get all unique keys from all rows to ensure headers are covered
        const allKeys = Array.from(new Set(allRows.flatMap(r => Object.keys(r))))

        // Sorting keys for better UX: Single keys first, then Array keys
        // Heuristic: keys with dots typically are array sub-keys
        allKeys.sort((a, b) => {
            const aHasDot = a.includes('.')
            const bHasDot = b.includes('.')
            if (aHasDot === bHasDot) return a.localeCompare(b)
            return aHasDot ? 1 : -1
        })

        allKeys.forEach((h, i) => {
            const maxContentWidth = Math.max(
                h.length,
                ...allRows.map(r => String(r[h] || '').length)
            )
            // Limit width between 5 and 50 chars
            maxWidths[i] = Math.max(5, Math.min(maxContentWidth + 2, 50))
        })
        worksheet['!cols'] = maxWidths.map(w => ({ wch: w }))

        // 파일 다운로드
        const timestamp = new Date().toISOString().slice(0, 10)
        // Ensure filename doesn't already have extension
        const cleanFilename = filename.replace(/\.xlsx$/, '')
        XLSX.writeFile(workbook, `${cleanFilename}_${timestamp}.xlsx`)
    } catch (error) {
        console.error('Excel download failed:', error)
        throw new Error('Excel 다운로드에 실패했습니다')
    }
}

/**
 * 다운로드 가능한 데이터인지 확인
 */
export function canDownload(data: Record<string, any> | null | undefined): boolean {
    if (!data) return false
    if (Array.isArray(data) && data.length === 0) return false
    if (typeof data === 'object' && Object.keys(data).length === 0) return false
    return true
}

