/**
 * Dictionary Panel — Model Studio sub-component
 * Upload Excel/CSV dictionaries, search, manage categories.
 */
import { useState, useEffect, useCallback } from 'react'
import { Upload, Search, Trash2, Plus, BookOpen, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'

const API_BASE = import.meta.env.VITE_API_URL || ''

interface DictionaryCategory {
    category: string
    count: number
}

interface SearchResult {
    code: string
    name: string
    category: string
    score: number
}

interface DictionaryPanelProps {
    modelDictionaries: string[]
    onDictionariesChange: (dictionaries: string[]) => void
    disabled?: boolean
}

export function DictionaryPanel({ modelDictionaries, onDictionariesChange, disabled }: DictionaryPanelProps) {
    const [categories, setCategories] = useState<DictionaryCategory[]>([])
    const [loading, setLoading] = useState(false)
    const [uploading, setUploading] = useState(false)
    const [searchQuery, setSearchQuery] = useState('')
    const [searchCategory, setSearchCategory] = useState('')
    const [searchResults, setSearchResults] = useState<SearchResult[]>([])
    const [newCategoryName, setNewCategoryName] = useState('')
    const [showAddForm, setShowAddForm] = useState(false)

    const fetchCategories = useCallback(async () => {
        try {
            setLoading(true)
            const res = await fetch(`${API_BASE}/api/v1/dictionaries/categories`)
            if (res.ok) {
                const data = await res.json()
                setCategories(data.categories || [])
            }
        } catch {
            // Service not configured — silently ignore
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        fetchCategories()
    }, [fetchCategories])

    const handleUpload = async (category: string, file: File) => {
        setUploading(true)
        try {
            const formData = new FormData()
            formData.append('file', file)
            formData.append('category', category)

            const res = await fetch(`${API_BASE}/api/v1/dictionaries/upload`, {
                method: 'POST',
                body: formData,
            })

            if (!res.ok) {
                const err = await res.json()
                throw new Error(err.detail || 'Upload failed')
            }

            const data = await res.json()
            toast.success(`${data.count}건 업로드 완료 (${category})`)

            // Auto-add to model dictionaries if not already
            if (!modelDictionaries.includes(category)) {
                onDictionariesChange([...modelDictionaries, category])
            }

            await fetchCategories()
        } catch (e: any) {
            toast.error(e.message || 'Upload failed')
        } finally {
            setUploading(false)
        }
    }

    const handleFileSelect = (category: string) => {
        const input = document.createElement('input')
        input.type = 'file'
        input.accept = '.xlsx,.xls,.csv'
        input.onchange = (e) => {
            const file = (e.target as HTMLInputElement).files?.[0]
            if (file) handleUpload(category, file)
        }
        input.click()
    }

    const handleSearch = async () => {
        if (!searchQuery.trim()) return
        try {
            const params = new URLSearchParams({ q: searchQuery, top_k: '5' })
            if (searchCategory) params.set('category', searchCategory)
            const res = await fetch(`${API_BASE}/api/v1/dictionaries/search?${params}`)
            if (res.ok) {
                const data = await res.json()
                setSearchResults(data.matches || [])
            }
        } catch {
            toast.error('검색 실패')
        }
    }

    const handleDeleteCategory = async (category: string) => {
        if (!confirm(`'${category}' 딕셔너리를 삭제하시겠습니까?`)) return
        try {
            const res = await fetch(`${API_BASE}/api/v1/dictionaries/${category}`, { method: 'DELETE' })
            if (res.ok) {
                toast.success(`${category} 삭제됨`)
                onDictionariesChange(modelDictionaries.filter(d => d !== category))
                await fetchCategories()
            }
        } catch {
            toast.error('삭제 실패')
        }
    }

    const handleAddCategory = () => {
        const name = newCategoryName.trim().toLowerCase()
        if (!name) return
        if (categories.some(c => c.category === name)) {
            toast.error('이미 등록된 카테고리입니다')
            return
        }
        // Keep form visible — open file dialog, close form only after upload succeeds
        const input = document.createElement('input')
        input.type = 'file'
        input.accept = '.xlsx,.xls,.csv'
        input.onchange = async (e) => {
            const file = (e.target as HTMLInputElement).files?.[0]
            if (file) {
                await handleUpload(name, file)
                setShowAddForm(false)
                setNewCategoryName('')
            }
            // If user cancelled file dialog, form stays open
        }
        input.click()
    }

    const toggleCategory = (category: string) => {
        if (modelDictionaries.includes(category)) {
            onDictionariesChange(modelDictionaries.filter(d => d !== category))
        } else {
            onDictionariesChange([...modelDictionaries, category])
        }
    }

    return (
        <div className="space-y-4">
            {/* Registered Dictionaries */}
            <div>
                <div className="flex items-center justify-between mb-2">
                    <h4 className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                        <BookOpen className="w-3 h-3" /> 등록된 딕셔너리
                    </h4>
                    <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setShowAddForm(true)}
                        disabled={disabled}
                        className="h-6 text-[10px] px-2"
                    >
                        <Plus className="w-3 h-3 mr-1" /> 딕셔너리 추가
                    </Button>
                </div>

                {showAddForm && (
                    <div className="flex gap-2 mb-2 p-2 bg-muted/50 rounded-lg">
                        <input
                            id="new-dictionary-name"
                            name="new-dictionary-name"
                            type="text"
                            placeholder="카테고리명 (예: port, charge)"
                            value={newCategoryName}
                            onChange={(e) => setNewCategoryName(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && handleAddCategory()}
                            className="flex-1 text-xs px-2 py-1 rounded border bg-background"
                            autoFocus
                        />
                        <Button size="sm" onClick={handleAddCategory} className="h-6 text-[10px]">
                            <Upload className="w-3 h-3 mr-1" /> 엑셀 업로드
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setShowAddForm(false)} className="h-6 text-[10px]">
                            취소
                        </Button>
                    </div>
                )}

                {loading ? (
                    <div className="flex items-center gap-2 text-xs text-muted-foreground py-4">
                        <Loader2 className="w-3 h-3 animate-spin" /> 로딩 중...
                    </div>
                ) : categories.length === 0 ? (
                    <p className="text-xs text-muted-foreground py-2">
                        등록된 딕셔너리가 없습니다. 엑셀 파일을 업로드하여 딕셔너리를 생성하세요.
                    </p>
                ) : (
                    <div className="space-y-1">
                        {categories.map((cat) => {
                            const isLinked = modelDictionaries.includes(cat.category)
                            return (
                                <div
                                    key={cat.category}
                                    className={`flex items-center justify-between px-3 py-2 rounded-lg border text-xs transition-colors ${isLinked ? 'bg-primary/5 border-primary/20' : 'bg-muted/30 border-transparent'}`}
                                >
                                    <div className="flex items-center gap-2">
                                        <input
                                            id={`dict-toggle-${cat.category}`}
                                            name={`dict-toggle-${cat.category}`}
                                            type="checkbox"
                                            checked={isLinked}
                                            onChange={() => toggleCategory(cat.category)}
                                            disabled={disabled}
                                            className="rounded"
                                        />
                                        <label htmlFor={`dict-toggle-${cat.category}`} className="font-medium cursor-pointer">
                                            {cat.category}
                                        </label>
                                        <span className="text-muted-foreground">({cat.count}건)</span>
                                    </div>
                                    <div className="flex gap-1">
                                        <Button
                                            size="sm"
                                            variant="ghost"
                                            onClick={() => handleFileSelect(cat.category)}
                                            disabled={disabled || uploading}
                                            className="h-5 text-[10px] px-1"
                                        >
                                            {uploading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Upload className="w-3 h-3" />}
                                        </Button>
                                        <Button
                                            size="sm"
                                            variant="ghost"
                                            onClick={() => handleDeleteCategory(cat.category)}
                                            disabled={disabled}
                                            className="h-5 text-[10px] px-1 text-destructive hover:text-destructive"
                                        >
                                            <Trash2 className="w-3 h-3" />
                                        </Button>
                                    </div>
                                </div>
                            )
                        })}
                    </div>
                )}
            </div>

            {/* Search Test */}
            <div>
                <h4 className="text-xs font-medium text-muted-foreground mb-2 flex items-center gap-1">
                    <Search className="w-3 h-3" /> 검색 테스트
                </h4>
                <div className="flex gap-2">
                    <select
                        id="dict-search-category"
                        name="dict-search-category"
                        value={searchCategory}
                        onChange={(e) => setSearchCategory(e.target.value)}
                        className="text-xs px-2 py-1.5 rounded border bg-background w-24"
                    >
                        <option value="">전체</option>
                        {categories.map(c => (
                            <option key={c.category} value={c.category}>{c.category}</option>
                        ))}
                    </select>
                    <input
                        id="dict-search-query"
                        name="dict-search-query"
                        type="text"
                        placeholder="검색어 입력 (예: Jebel Ali)"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                        className="flex-1 text-xs px-2 py-1.5 rounded border bg-background"
                    />
                    <Button size="sm" onClick={handleSearch} className="h-7 text-[10px]">
                        <Search className="w-3 h-3 mr-1" /> 검색
                    </Button>
                </div>

                {searchResults.length > 0 && (
                    <div className="mt-2 border rounded-lg overflow-hidden">
                        <table className="w-full text-xs">
                            <thead>
                                <tr className="bg-muted/50">
                                    <th className="text-left px-2 py-1 font-medium">코드</th>
                                    <th className="text-left px-2 py-1 font-medium">이름</th>
                                    <th className="text-left px-2 py-1 font-medium">카테고리</th>
                                    <th className="text-right px-2 py-1 font-medium">점수</th>
                                </tr>
                            </thead>
                            <tbody>
                                {searchResults.map((r, i) => (
                                    <tr key={i} className="border-t">
                                        <td className="px-2 py-1 font-mono text-primary">{r.code}</td>
                                        <td className="px-2 py-1">{r.name}</td>
                                        <td className="px-2 py-1 text-muted-foreground">{r.category}</td>
                                        <td className="px-2 py-1 text-right">{r.score.toFixed(2)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    )
}
