/**
 * Dictionary Panel — Model Studio sub-component
 * Upload Excel/CSV dictionaries, search, manage categories.
 */
import { useState, useEffect, useCallback } from 'react'
import { Upload, Search, Trash2, Plus, BookOpen, Loader2, Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { apiClient } from '@/lib/api'

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
    modelId: string
    disabled?: boolean
}

export function DictionaryPanel({ modelId, disabled }: DictionaryPanelProps) {
    const [categories, setCategories] = useState<DictionaryCategory[]>([])
    const [loading, setLoading] = useState(false)
    const [uploading, setUploading] = useState(false)
    const [searchQuery, setSearchQuery] = useState('')
    const [searchCategory, setSearchCategory] = useState('')
    const [searchResults, setSearchResults] = useState<SearchResult[]>([])
    const [newCategoryName, setNewCategoryName] = useState('')
    const [showAddForm, setShowAddForm] = useState(false)

    const fetchCategories = useCallback(async () => {
        if (!modelId) return
        try {
            setLoading(true)
            const res = await apiClient.get('/dictionaries/categories', { params: { model_id: modelId } })
            setCategories(res.data.categories || [])
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
            formData.append('model_id', modelId)

            const res = await apiClient.post('/dictionaries/upload', formData)

            toast.success(`딕셔너리 '${category}' 생성 완료 (항목: ${res.data.count}개)`)
            setNewCategoryName('')
            setShowAddForm(false)
            fetchCategories()
        } catch (e: any) {
            const message = e.response?.data?.detail || e.message || 'Upload failed'
            toast.error(message)
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
            const params: Record<string, string> = { q: searchQuery, top_k: '5', model_id: modelId }
            if (searchCategory) params.category = searchCategory
            const res = await apiClient.get('/dictionaries/search', { params })
            setSearchResults(res.data.matches || [])
        } catch {
            toast.error('검색 실패')
        }
    }

    const handleDeleteCategory = async (category: string) => {
        if (!confirm(`'${category}' 딕셔너리를 삭제하시겠습니까?`)) return
        // Optimistic UI update to handle Azure AI Search index drop propagation delay
        setCategories(prev => prev.filter(c => c.category !== category))
        try {
            await apiClient.delete(`/dictionaries/${category}`, { params: { model_id: modelId } })
            toast.success(`딕셔너리 '${category}' 삭제 완료`)
            // Delay the strict refetch to allow Azure search to actually drop the index
            setTimeout(() => {
                fetchCategories()
            }, 3000)
        } catch (err: any) {
            toast.error('삭제 실패: ' + (err.response?.data?.detail || err.message))
            // Revert on failure
            fetchCategories()
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

    const handleDownloadTemplate = () => {
        const csvContent = "\uFEFF표준코드(Code),표시명(Name),동의어1(Alias1),동의어2(Alias2)\nKRPUS,부산항,Busan,Pusan\nAEJEA,제벨알리,Jebel Ali,JEA\nNLRTM,로테르담,Rotterdam,RTM"
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.setAttribute('download', 'synonym_dictionary_template.csv')
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
        URL.revokeObjectURL(url)
    }

    return (
        <div className="space-y-4">
            {/* Usage Guide */}
            <div className="bg-blue-50/50 p-3 rounded-lg border border-blue-100 dark:bg-blue-900/10 dark:border-blue-800">
                <div className="flex items-start justify-between mb-2">
                    <h3 className="text-xs font-semibold text-blue-800 dark:text-blue-300 flex items-center gap-1.5 mt-1">
                        <BookOpen className="w-3.5 h-3.5" />
                        동의어 사전(Synonym Dictionary) 연동 가이드
                    </h3>
                    <Button
                        size="sm"
                        variant="outline"
                        className="h-6 text-[10px] px-2 bg-white dark:bg-black/20 hover:bg-blue-50 dark:hover:bg-blue-900/40 border-blue-200 dark:border-blue-800"
                        onClick={handleDownloadTemplate}
                    >
                        <Download className="w-3 h-3 mr-1" /> 템플릿 다운로드
                    </Button>
                </div>

                <div className="text-[11px] text-blue-700/80 dark:text-blue-400/80 space-y-1.5">
                    <p>추출된 다양한 유사 텍스트를 하나의 <b className="font-semibold">표준 코드</b>로 통일(정규화)할 때 사용합니다.</p>

                    <div className="bg-white/60 dark:bg-black/20 p-2 rounded border border-blue-100/50 dark:border-blue-800/50 mt-2">
                        <p className="font-semibold text-blue-900 dark:text-blue-200 mb-1 flex items-center gap-1">
                            ⚠️ 엑셀/CSV 데이터 작성 규칙 <span className="text-xs font-normal text-blue-600/70 dark:text-blue-400/60">(열 순서가 매우 중요합니다!)</span>
                        </p>
                        <ul className="list-none space-y-0.5 ml-1">
                            <li><span className="inline-block w-4 bg-blue-100 dark:bg-blue-900/50 text-blue-800 dark:text-blue-300 text-center rounded mr-1">1</span><b>1열 (필수):</b> 정규화된 <b>표준 코드</b> <span className="text-muted-foreground">(예: KRPUS)</span></li>
                            <li><span className="inline-block w-4 bg-blue-100 dark:bg-blue-900/50 text-blue-800 dark:text-blue-300 text-center rounded mr-1">2</span><b>2열 (필수):</b> 표기 명칭 <span className="text-muted-foreground">(예: 부산항)</span></li>
                            <li><span className="inline-block w-4 bg-muted text-muted-foreground text-center rounded mr-1">3</span><b>3열 이후 (선택):</b> 각종 유사어 나열 <span className="text-muted-foreground">(예: Busan, Pusan)</span></li>
                        </ul>
                    </div>

                    <p className="text-[10px] mt-2 text-blue-600/60 dark:text-blue-400/50 pt-1 border-t border-blue-100 dark:border-blue-800/50">
                        * 유효한 조합인지 검사하는 <b>마스터 데이터</b>(예: 특정 선사 & 특정 포트 필터링)는 우측 <b>'참조 데이터'</b> 탭을 이용해주세요.
                    </p>
                </div>
            </div>

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
                            return (
                                <div
                                    key={cat.category}
                                    className={`flex items-center justify-between px-3 py-2 rounded-lg border text-xs bg-muted/30 border-transparent`}
                                >
                                    <div className="flex items-center gap-2">
                                        <BookOpen className="w-3.5 h-3.5 text-blue-500/70" />
                                        <span className="font-medium text-foreground">
                                            {cat.category}
                                        </span>
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
