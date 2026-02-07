/* eslint-disable @typescript-eslint/no-explicit-any */

/**
 * Utility functions for extracting values from rich objects (AI/OCR metadata)
 * and deep flattening nested JSON data for table display.
 */

/**
 * Extracts the raw value from a potentially rich object.
 * Handles cases where the value is wrapped in { value: ..., confidence: ... }
 */
export function extractValue(data: any): any {
    // Handle null/undefined
    if (data === null || data === undefined) return data

    // If it's a primitive, return as-is
    if (typeof data !== 'object') return data

    // Case 1: Standard rich object { value: "xxx", confidence: 0.9, ... }
    if ('value' in data) {
        return data.value
    }

    // Case 2: OpenAI sometimes returns arrays of rich objects - don't unwrap these
    if (Array.isArray(data)) {
        return data
    }

    // Case 3: Single-key object where the key might be a header OpenAI added
    // e.g., { "graduation_date": "2024" } - just return the whole object
    return data
}

/**
 * Extracts confidence score from a rich object if present.
 */
export function extractConfidence(data: any): number | null {
    if (data && typeof data === 'object' && 'confidence' in data) {
        return data.confidence
    }
    return null
}

/**
 * Helper to extract all unique keys from an array of objects for table headers
 */
export function getAllKeys(data: any[]): string[] {
    const keys = new Set<string>()
    data.forEach(item => {
        if (typeof item === 'object' && item !== null) {
            Object.keys(item).forEach(k => keys.add(k))
        }
    })
    return Array.from(keys)
}

export type DeepFlattenResult = {
    normalizedData: any[]
    paths: Map<number, Record<string, any[]>>
}

/**
 * Deep Flattening Logic with Array Zipping and Path Tracking
 * 
 * Features:
 * 1. Deep Recursion: Handles unlimited nesting levels
 * 2. Array Zipping: Expands rows for arrays (List-in-Row)
 * 3. Path Tracking: Maps flattened cells back to original object paths for bi-directional editing
 * 
 * @param data Array of nested objects
 * @returns { normalizedData: flattened array, paths: mapping for edits }
 */
export function deepFlattenData(data: any[]): DeepFlattenResult {
    if (!Array.isArray(data) || data.length === 0) return { normalizedData: [], paths: new Map() }

    // Initial state: Each item has data and its base path
    let currentLevel = data.map((item, idx) => ({
        data: item,
        paths: (() => {
            const p: Record<string, any[]> = {}
            if (typeof item === 'object' && item !== null) {
                Object.keys(item).forEach(k => p[k] = [idx, k])
            }
            return p
        })()
    }))

    let hasChanges = true
    const MAX_ITERATIONS = 10
    let iterations = 0

    while (hasChanges && iterations < MAX_ITERATIONS) {
        hasChanges = false
        iterations++
        const nextLevel: typeof currentLevel = []

        currentLevel.forEach(({ data: row, paths }) => {
            if (typeof row !== 'object' || row === null) {
                nextLevel.push({ data: row, paths })
                return
            }

            const arrayFields: string[] = []
            const objectFields: string[] = []

            Object.entries(row).forEach(([key, value]) => {
                const val = extractValue(value)
                if (Array.isArray(val) && val.length > 0) {
                    arrayFields.push(key)
                } else if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
                    objectFields.push(key)
                }
            })

            // Case A: Row expansion (Arrays)
            if (arrayFields.length > 0) {
                hasChanges = true
                const maxLen = Math.max(...arrayFields.map(k => {
                    const val = extractValue(row[k])
                    return Array.isArray(val) ? val.length : 0
                }))

                for (let i = 0; i < maxLen; i++) {
                    const newRow: any = { ...row }
                    const newPaths: Record<string, any[]> = { ...paths }

                    arrayFields.forEach(key => {
                        const arr = extractValue(row[key])
                        newRow[key] = arr[i] !== undefined ? arr[i] : null

                        const existingPath = paths[key]
                        if (existingPath) {
                            newPaths[key] = [...existingPath, i]
                        }
                    })

                    nextLevel.push({ data: newRow, paths: newPaths })
                }
            }
            // Case B: Key flattening (Objects)
            else if (objectFields.length > 0) {
                hasChanges = true
                const newRow: any = { ...row }
                const newPaths: Record<string, any[]> = { ...paths }

                objectFields.forEach(parentKey => {
                    const childObj = extractValue(row[parentKey])
                    delete newRow[parentKey]
                    const parentPath = paths[parentKey]
                    delete newPaths[parentKey]

                    if (typeof childObj === 'object' && childObj !== null) {
                        Object.entries(childObj).forEach(([childKey, childValue]) => {
                            const combinedKey = `${parentKey}.${childKey}`
                            newRow[combinedKey] = childValue
                            if (parentPath) {
                                newPaths[combinedKey] = [...parentPath, childKey]
                            }
                        })
                    }
                })
                nextLevel.push({ data: newRow, paths: newPaths })
            }
            else {
                nextLevel.push({ data: row, paths })
            }
        })

        currentLevel = nextLevel
    }

    // Convert back to simple array and separate paths map
    const normalizedData = currentLevel.map(item => item.data)
    const pathsMap = new Map<number, Record<string, any[]>>()
    currentLevel.forEach((item, idx) => {
        pathsMap.set(idx, item.paths)
    })

    return { normalizedData, paths: pathsMap }
}
