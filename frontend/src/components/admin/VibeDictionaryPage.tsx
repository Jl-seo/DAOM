import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Loader2, Plus, Search, Globe, BrainCircuit, Building2, BookOpen, Upload, Trash2, X } from 'lucide-react'
import { toast } from 'sonner'
import apiClient from '@/lib/api'

interface VibeEntry {
    model_id: string
    model_name: string
    field_name: string
    raw_val: string
    standard_val: string
    source: string
    hit_count: number
    is_verified: boolean
}

interface ReferenceCategory {
    category: string
    count: number
}

type TabId = 'global' | 'ai' | 'model'

export function VibeDictionaryPage() {
    const queryClient = useQueryClient()
    const [activeTab, setActiveTab] = useState<TabId>('global')
    const [searchTerm, setSearchTerm] = useState('')
    const [editingEntry, setEditingEntry] = useState<VibeEntry | null>(null)
    const [isEditDialogOpen, setIsEditDialogOpen] = useState(false)
    const [isAddDialogOpen, setIsAddDialogOpen] = useState(false)
    const [newEntry, setNewEntry] = useState({
        model_id: '',
        field_name: 'default',
        raw_val: '',
        standard_val: ''
    })

    // Global tab state
    const [uploadCategory, setUploadCategory] = useState('')
    const [searchQuery, setSearchQuery] = useState('')
    const [searchCategory, setSearchCategory] = useState('')
    const [searchResults, setSearchResults] = useState<any[]>([])
    const [isSearching, setIsSearching] = useState(false)
    const fileInputRef = useRef<HTMLInputElement>(null)

    // Fetch synonym entries (AI + model-specific)
    const { data: entries = [], isLoading } = useQuery({
        queryKey: ['vibe-dictionary'],
        queryFn: async () => {
            const res = await apiClient.get('/vibe-dictionary')
            return res.data as VibeEntry[]
        }
    })

    // Fetch global reference data categories
    const { data: globalCategories = [], isLoading: isLoadingGlobal } = useQuery({
        queryKey: ['global-dictionary-categories'],
        queryFn: async () => {
            const res = await apiClient.get('/dictionaries/categories', { params: { model_id: '__global__' } })
            return (res.data.categories || []) as ReferenceCategory[]
        }
    })

    const { data: availableModels = [] } = useQuery({
        queryKey: ['extraction-models-list'],
        queryFn: async () => {
            const res = await apiClient.get('/models')
            return res.data as { id: string, name: string }[]
        }
    })

    // Upload mutation for global dictionary
    const uploadMutation = useMutation({
        mutationFn: async ({ file, category }: { file: File, category: string }) => {
            const formData = new FormData()
            formData.append('file', file)
            formData.append('model_id', '__global__')
            formData.append('category', category)
            const res = await apiClient.post('/dictionaries/upload', formData)
            return res.data
        },
        onSuccess: (data) => {
            queryClient.invalidateQueries({ queryKey: ['global-dictionary-categories'] })
            toast.success(`${data.count}건 업로드 완료`)
            setUploadCategory('')
            if (fileInputRef.current) fileInputRef.current.value = ''
        },
        onError: () => toast.error('업로드 실패')
    })

    // Delete category mutation
    const deleteCategoryMutation = useMutation({
        mutationFn: async (category: string) => {
            await apiClient.delete(`/dictionaries/${category}`, { params: { model_id: '__global__' } })
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['global-dictionary-categories'] })
            toast.success('카테고리 삭제 완료')
        },
        onError: () => toast.error('삭제 실패')
    })

    const handleUpload = () => {
        const file = fileInputRef.current?.files?.[0]
        if (!file || !uploadCategory.trim()) {
            toast.error('파일과 카테고리명을 입력하세요')
            return
        }
        uploadMutation.mutate({ file, category: uploadCategory.trim().toLowerCase() })
    }

    const handleDeleteCategory = (category: string) => {
        if (!confirm(`'${category}' 카테고리의 모든 항목을 삭제하시겠습니까?`)) return
        deleteCategoryMutation.mutate(category)
    }

    const handleSearch = async () => {
        if (!searchQuery.trim()) return
        setIsSearching(true)
        try {
            const res = await apiClient.get('/dictionaries/search', {
                params: { q: searchQuery, model_id: '__global__', category: searchCategory || undefined }
            })
            setSearchResults(res.data.matches || [])
        } catch {
            toast.error('검색 실패')
        } finally {
            setIsSearching(false)
        }
    }

    const updateMutation = useMutation({
        mutationFn: async ({ model_id, field_name, raw_val, data }: { model_id: string, field_name: string, raw_val: string, data: any }) => {
            await apiClient.put(`/vibe-dictionary/${model_id}/${field_name}/${encodeURIComponent(raw_val)}`, data)
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['vibe-dictionary'] })
            toast.success('수정되었습니다.')
            setIsEditDialogOpen(false)
        },
        onError: () => toast.error('업데이트 실패')
    })

    const deleteMutation = useMutation({
        mutationFn: async ({ model_id, field_name, raw_val }: { model_id: string, field_name: string, raw_val: string }) => {
            await apiClient.delete(`/vibe-dictionary/${model_id}/${field_name}/${encodeURIComponent(raw_val)}`)
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['vibe-dictionary'] })
            toast.success('삭제되었습니다.')
        },
        onError: () => toast.error('삭제 실패')
    })

    const addMutation = useMutation({
        mutationFn: async (data: typeof newEntry) => {
            await apiClient.post('/vibe-dictionary', data)
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['vibe-dictionary'] })
            toast.success('등록되었습니다.')
            setIsAddDialogOpen(false)
            setNewEntry({ model_id: '', field_name: 'default', raw_val: '', standard_val: '' })
        },
        onError: () => toast.error('등록 실패')
    })

    const toggleVerified = (entry: VibeEntry) => {
        updateMutation.mutate({
            model_id: entry.model_id,
            field_name: entry.field_name,
            raw_val: entry.raw_val,
            data: { is_verified: !entry.is_verified }
        })
    }

    const handleDelete = (entry: VibeEntry) => {
        if (!confirm(`'${entry.raw_val}' 치환 항목을 삭제하시겠습니까?`)) return
        deleteMutation.mutate(entry)
    }

    const handleEditClick = (entry: VibeEntry) => {
        setEditingEntry(entry)
        setIsEditDialogOpen(true)
    }

    const handleEditSave = () => {
        if (!editingEntry) return
        updateMutation.mutate({
            model_id: editingEntry.model_id,
            field_name: editingEntry.field_name,
            raw_val: editingEntry.raw_val,
            data: { standard_val: editingEntry.standard_val }
        })
    }

    const handleAddSave = () => {
        addMutation.mutate(newEntry)
    }

    // Filter entries based on active tab
    const filteredEntries = entries.filter(e => {
        const matchesSearch = searchTerm === '' ||
            e.raw_val.toLowerCase().includes(searchTerm.toLowerCase()) ||
            e.standard_val.toLowerCase().includes(searchTerm.toLowerCase()) ||
            e.model_name.toLowerCase().includes(searchTerm.toLowerCase())
        
        if (!matchesSearch) return false
        
        if (activeTab === 'ai') return e.source === 'AI_GENERATED'
        if (activeTab === 'model') return e.source !== 'AI_GENERATED' && e.model_id !== '__global__'
        return false // global tab shows categories, not entries
    })

    const totalGlobalEntries = globalCategories.reduce((sum, c) => sum + c.count, 0)
    const aiEntries = entries.filter(e => e.source === 'AI_GENERATED')
    const modelEntries = entries.filter(e => e.source !== 'AI_GENERATED' && e.model_id !== '__global__')

    const tabs: { id: TabId, label: string, icon: React.ReactNode, count: number, description: string }[] = [
        { id: 'global', label: '글로벌 사전', icon: <Globe className="w-4 h-4" />, count: totalGlobalEntries, description: '전체 모델이 공유하는 참조 데이터 (Port, Carrier, Route)' },
        { id: 'ai', label: 'AI 학습 사전', icon: <BrainCircuit className="w-4 h-4" />, count: aiEntries.length, description: 'LLM이 자동 발견한 동의어/오타 매핑 (승인 대기)' },
        { id: 'model', label: '모델별 수동 사전', icon: <Building2 className="w-4 h-4" />, count: modelEntries.length, description: '관리자가 특정 모델에 수동 등록한 매핑' },
    ]

    return (
        <div className="flex-1 flex flex-col h-full bg-slate-50 relative animate-in fade-in duration-300">
            {/* Header */}
            <div className="p-6 pb-4 bg-white border-b sticky top-0 z-10">
                <h1 className="text-2xl font-bold flex items-center gap-2 text-slate-800">
                    <BookOpen className="w-6 h-6 text-blue-600" />
                    통합 사전 관리
                </h1>
                <p className="text-sm text-slate-500 mt-1">
                    추출 파이프라인에서 사용하는 모든 사전 데이터를 한 곳에서 관리합니다.
                </p>
            </div>

            {/* Tab Bar */}
            <div className="px-6 pt-4 pb-0 bg-white border-b">
                <div className="flex gap-1">
                    {tabs.map(tab => (
                        <button
                            key={tab.id}
                            id={`tab-${tab.id}`}
                            onClick={() => { setActiveTab(tab.id); setSearchTerm('') }}
                            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-t-lg border-b-2 transition-all ${
                                activeTab === tab.id
                                    ? 'bg-blue-50 text-blue-700 border-blue-600'
                                    : 'text-slate-500 border-transparent hover:text-slate-700 hover:bg-slate-50'
                            }`}
                        >
                            {tab.icon}
                            {tab.label}
                            <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                                activeTab === tab.id ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-500'
                            }`}>
                                {tab.count}
                            </span>
                        </button>
                    ))}
                </div>
            </div>

            <div className="flex-1 p-6 overflow-auto">
                {/* Tab Description */}
                <div className="mb-4 p-3 bg-blue-50/50 border border-blue-200/50 rounded-lg">
                    <p className="text-xs text-blue-700">
                        {tabs.find(t => t.id === activeTab)?.description}
                    </p>
                </div>

                {/* GLOBAL TAB — Category overview + Upload + Search */}
                {activeTab === 'global' && (
                    <div className="space-y-4">
                        {/* Upload Section */}
                        <Card className="bg-white shadow-sm border-slate-200 p-5">
                            <h3 className="text-sm font-bold text-slate-800 mb-3 flex items-center gap-2">
                                <Upload className="w-4 h-4 text-blue-600" />
                                Excel/CSV 업로드
                            </h3>
                            <div className="flex items-end gap-3">
                                <div className="flex-1">
                                    <label htmlFor="upload-category" className="block text-xs font-medium text-slate-600 mb-1">카테고리명</label>
                                    <Input
                                        id="upload-category"
                                        name="upload-category"
                                        placeholder="예: port, carrier, route"
                                        value={uploadCategory}
                                        onChange={e => setUploadCategory(e.target.value)}
                                        className="h-9 text-sm"
                                    />
                                </div>
                                <div className="flex-1">
                                    <label htmlFor="upload-file" className="block text-xs font-medium text-slate-600 mb-1">파일 선택</label>
                                    <input
                                        ref={fileInputRef}
                                        id="upload-file"
                                        name="upload-file"
                                        type="file"
                                        accept=".xlsx,.xls,.csv"
                                        className="block w-full text-xs text-slate-500 file:mr-2 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
                                    />
                                </div>
                                <Button
                                    id="upload-btn"
                                    size="sm"
                                    onClick={handleUpload}
                                    disabled={uploadMutation.isPending}
                                    className="h-9 gap-1.5 bg-blue-600 hover:bg-blue-700"
                                >
                                    {uploadMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
                                    업로드
                                </Button>
                            </div>
                            <p className="text-[10px] text-slate-400 mt-2">
                                1열=코드, 2열=이름, 3열~=별칭(alias). 기존 카테고리에 같은 이름으로 올리면 덮어씁니다.
                            </p>
                        </Card>

                        {/* Categories Grid */}
                        <Card className="bg-white shadow-sm border-slate-200 p-5">
                            <div className="flex items-center justify-between mb-4">
                                <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
                                    <Globe className="w-4 h-4 text-blue-600" />
                                    등록된 카테고리
                                </h3>
                                <div className="text-xs text-slate-500">
                                    총 <span className="font-bold text-blue-600">{totalGlobalEntries}</span>개 항목
                                </div>
                            </div>

                            {isLoadingGlobal ? (
                                <div className="h-24 flex items-center justify-center">
                                    <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
                                </div>
                            ) : globalCategories.length === 0 ? (
                                <div className="h-24 flex flex-col items-center justify-center text-slate-400">
                                    <Globe className="w-6 h-6 mb-2 opacity-50" />
                                    <p className="text-sm">등록된 글로벌 사전이 없습니다.</p>
                                    <p className="text-xs mt-1">위에서 Excel 파일을 업로드하세요.</p>
                                </div>
                            ) : (
                                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                                    {globalCategories.map(cat => (
                                        <div key={cat.category} className="p-4 border rounded-xl bg-gradient-to-br from-slate-50 to-white hover:shadow-sm transition-shadow group">
                                            <div className="flex items-center justify-between mb-2">
                                                <span className="text-sm font-bold text-slate-800 uppercase">{cat.category}</span>
                                                <div className="flex items-center gap-2">
                                                    <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">{cat.count}개</span>
                                                    <button
                                                        onClick={() => handleDeleteCategory(cat.category)}
                                                        className="opacity-0 group-hover:opacity-100 transition-opacity text-red-400 hover:text-red-600"
                                                        title="카테고리 삭제"
                                                    >
                                                        <Trash2 className="w-3.5 h-3.5" />
                                                    </button>
                                                </div>
                                            </div>
                                            <p className="text-xs text-slate-500">
                                                {cat.category === 'port' && '항구 코드 (UN/LOCODE 기반)'}
                                                {cat.category === 'carrier' && '선사 코드 (SCAC 기반)'}
                                                {cat.category === 'route' && '항로 코드'}
                                                {!['port', 'carrier', 'route'].includes(cat.category) && '사용자 정의 카테고리'}
                                            </p>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </Card>

                        {/* Search Test */}
                        <Card className="bg-white shadow-sm border-slate-200 p-5">
                            <h3 className="text-sm font-bold text-slate-800 mb-3 flex items-center gap-2">
                                <Search className="w-4 h-4 text-blue-600" />
                                검색 테스트
                            </h3>
                            <div className="flex items-end gap-3">
                                <div className="flex-1">
                                    <label htmlFor="search-query" className="block text-xs font-medium text-slate-600 mb-1">검색어</label>
                                    <Input
                                        id="search-query"
                                        name="search-query"
                                        placeholder="예: busan, MAERSK"
                                        value={searchQuery}
                                        onChange={e => setSearchQuery(e.target.value)}
                                        onKeyDown={e => e.key === 'Enter' && handleSearch()}
                                        className="h-9 text-sm"
                                    />
                                </div>
                                <div className="w-32">
                                    <label htmlFor="search-category" className="block text-xs font-medium text-slate-600 mb-1">카테고리</label>
                                    <select
                                        id="search-category"
                                        name="search-category"
                                        className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                                        value={searchCategory}
                                        onChange={e => setSearchCategory(e.target.value)}
                                    >
                                        <option value="">전체</option>
                                        {globalCategories.map(c => (
                                            <option key={c.category} value={c.category}>{c.category}</option>
                                        ))}
                                    </select>
                                </div>
                                <Button
                                    id="search-btn"
                                    size="sm"
                                    onClick={handleSearch}
                                    disabled={isSearching}
                                    className="h-9 gap-1.5"
                                    variant="outline"
                                >
                                    {isSearching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
                                    검색
                                </Button>
                            </div>
                            {searchResults.length > 0 && (
                                <div className="mt-3 border rounded-lg overflow-hidden">
                                    <table className="w-full text-sm">
                                        <thead className="bg-slate-50">
                                            <tr>
                                                <th className="px-3 py-2 text-left text-xs text-slate-500 font-medium">코드</th>
                                                <th className="px-3 py-2 text-left text-xs text-slate-500 font-medium">이름</th>
                                                <th className="px-3 py-2 text-left text-xs text-slate-500 font-medium">카테고리</th>
                                                <th className="px-3 py-2 text-right text-xs text-slate-500 font-medium">유사도</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {searchResults.map((r, i) => (
                                                <tr key={i} className="border-t">
                                                    <td className="px-3 py-2 font-mono text-blue-700 font-bold">{r.code}</td>
                                                    <td className="px-3 py-2">{r.name}</td>
                                                    <td className="px-3 py-2 text-slate-500">{r.category}</td>
                                                    <td className="px-3 py-2 text-right">
                                                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${r.score >= 0.9 ? 'bg-green-100 text-green-700' : r.score >= 0.6 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'}`}>
                                                            {(r.score * 100).toFixed(0)}%
                                                        </span>
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </Card>
                    </div>
                )}

                {/* AI / MODEL TABS — Entry table */}
                {(activeTab === 'ai' || activeTab === 'model') && (
                    <Card className="flex flex-col h-full bg-white shadow-sm border-slate-200">
                        {/* Toolbar */}
                        <div className="flex items-center justify-between p-4 border-b bg-slate-50/50">
                            <div className="text-sm font-medium text-slate-600">
                                {filteredEntries.length}개 항목
                            </div>

                            <div className="flex items-center gap-2">
                                <div className="relative w-48 sm:w-64">
                                    <Search className="w-4 h-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
                                    <Input
                                        id="dictionary-search-input"
                                        placeholder="용어 검색"
                                        className="h-8 pl-8 text-sm"
                                        value={searchTerm}
                                        onChange={e => setSearchTerm(e.target.value)}
                                    />
                                </div>

                                {activeTab === 'model' && (
                                    <Button
                                        id="add-synonym-btn"
                                        size="sm"
                                        className="h-8 gap-1.5 bg-blue-600 hover:bg-blue-700 ml-2"
                                        onClick={() => setIsAddDialogOpen(true)}
                                    >
                                        <Plus className="w-3.5 h-3.5" /> 수동 등록
                                    </Button>
                                )}
                            </div>
                        </div>

                        {/* Data Table */}
                        <div className="flex-1 overflow-auto rounded-b-xl border-t-0">
                            {isLoading ? (
                                <div className="w-full h-40 flex items-center justify-center">
                                    <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
                                </div>
                            ) : filteredEntries.length === 0 ? (
                                <div className="w-full h-40 flex flex-col items-center justify-center text-slate-400">
                                    <Search className="w-8 h-8 mb-2 opacity-50" />
                                    <p>표시할 딕셔너리 데이터가 없습니다.</p>
                                </div>
                            ) : (
                                <table className="w-full text-sm text-left">
                                    <thead className="text-xs text-slate-500 uppercase bg-slate-50 sticky top-0 z-10 shadow-sm">
                                        <tr>
                                            <th className="px-4 py-3 font-medium text-slate-500">Persona</th>
                                            <th className="px-4 py-3 font-medium text-slate-500">Source (음차/오인식)</th>
                                            <th className="px-4 py-3 font-medium text-slate-500">Target (전문용어)</th>
                                            <th className="px-4 py-3 font-medium text-slate-500 text-center">추출 유형</th>
                                            <th className="px-4 py-3 font-medium text-slate-500 text-center">Hit</th>
                                            <th className="px-4 py-3 font-medium text-slate-500 text-center">상태</th>
                                            <th className="px-4 py-3 font-medium text-slate-500 text-right pr-6">관리</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-100">
                                        {filteredEntries.map((entry, idx) => (
                                            <tr key={`${entry.model_id}-${entry.raw_val}-${idx}`} className="hover:bg-blue-50/30 transition-colors group">
                                                <td className="px-4 py-3 text-slate-500 text-xs">{entry.model_name} <span className="text-slate-300">({entry.field_name})</span></td>
                                                <td className="px-4 py-3 font-medium text-slate-900">{entry.raw_val}</td>
                                                <td className="px-4 py-3 font-bold text-blue-600 flex items-center gap-2">
                                                    <span className="text-slate-300">→</span> {entry.standard_val}
                                                </td>
                                                <td className="px-4 py-3 text-center">
                                                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium ${entry.source === 'AI_GENERATED' ? 'bg-purple-100 text-purple-700' : 'bg-slate-100 text-slate-700'
                                                        }`}>
                                                        {entry.source === 'AI_GENERATED' ? 'LLM 오토' : '수동'}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3 text-center font-medium">{entry.hit_count}회</td>
                                                <td className="px-4 py-3 text-center">
                                                    <div className="flex justify-center">
                                                        <Switch
                                                            checked={entry.is_verified}
                                                            onCheckedChange={() => toggleVerified(entry)}
                                                            title={entry.is_verified ? "활성" : "비활성"}
                                                        />
                                                    </div>
                                                </td>
                                                <td className="px-4 py-3 text-right pr-6 space-x-3 opacity-0 group-hover:opacity-100 transition-opacity">
                                                    <button
                                                        className="text-blue-600 hover:text-blue-800 text-xs font-medium focus:outline-none"
                                                        onClick={() => handleEditClick(entry)}
                                                    >
                                                        수정
                                                    </button>
                                                    <button
                                                        onClick={() => handleDelete(entry)}
                                                        className="text-red-500 hover:text-red-700 text-xs font-medium focus:outline-none"
                                                    >
                                                        삭제
                                                    </button>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            )}
                        </div>
                    </Card>
                )}
            </div>

            {/* Edit Dialog */}
            {isEditDialogOpen && editingEntry && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6 animate-in zoom-in-95 duration-200">
                        <h2 className="text-xl font-bold mb-4">단어 매핑 수정</h2>
                        <div className="space-y-4">
                            <div>
                                <label htmlFor="edit-source" className="block text-sm font-medium text-slate-700 mb-1">Source (음차/오인식)</label>
                                <Input id="edit-source" value={editingEntry.raw_val} disabled className="bg-slate-50 text-slate-500" />
                            </div>
                            <div>
                                <label htmlFor="edit-target" className="block text-sm font-medium text-slate-700 mb-1">Target (전문용어)</label>
                                <Input
                                    id="edit-target"
                                    name="edit-target"
                                    value={editingEntry.standard_val}
                                    onChange={e => setEditingEntry({ ...editingEntry, standard_val: e.target.value })}
                                    placeholder="변경할 표준어를 입력하세요"
                                    autoFocus
                                />
                            </div>
                        </div>
                        <div className="mt-6 flex justify-end gap-2">
                            <Button variant="outline" onClick={() => setIsEditDialogOpen(false)}>취소</Button>
                            <Button
                                id="edit-save-btn"
                                className="bg-blue-600 hover:bg-blue-700"
                                onClick={() => handleEditSave()}
                            >
                                저장
                            </Button>
                        </div>
                    </div>
                </div>
            )}

            {/* Add Dialog */}
            {isAddDialogOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6 animate-in zoom-in-95 duration-200">
                        <h2 className="text-xl font-bold mb-4">수동 단어 등록</h2>
                        <div className="space-y-4">
                            <div>
                                <label htmlFor="add-model" className="block text-sm font-medium text-slate-700 mb-1">Model (Persona)</label>
                                <select
                                    id="add-model"
                                    name="add-model"
                                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                                    value={newEntry.model_id}
                                    onChange={e => setNewEntry({ ...newEntry, model_id: e.target.value })}
                                >
                                    <option value="" disabled>모델을 선택하세요</option>
                                    {availableModels.map(m => (
                                        <option key={m.id} value={m.id}>
                                            {m.name}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label htmlFor="add-field" className="block text-sm font-medium text-slate-700 mb-1">Field Name (Optional)</label>
                                <Input
                                    id="add-field"
                                    name="add-field"
                                    value={newEntry.field_name}
                                    onChange={e => setNewEntry({ ...newEntry, field_name: e.target.value })}
                                    placeholder="적용할 필드명 (전체는 default)"
                                />
                            </div>
                            <div>
                                <label htmlFor="add-source" className="block text-sm font-medium text-slate-700 mb-1">Source (원문/오인식)</label>
                                <Input
                                    id="add-source"
                                    name="add-source"
                                    value={newEntry.raw_val}
                                    onChange={e => setNewEntry({ ...newEntry, raw_val: e.target.value })}
                                    placeholder="변환 전 단어"
                                />
                            </div>
                            <div>
                                <label htmlFor="add-target" className="block text-sm font-medium text-slate-700 mb-1">Target (전문용어/표준어)</label>
                                <Input
                                    id="add-target"
                                    name="add-target"
                                    value={newEntry.standard_val}
                                    onChange={e => setNewEntry({ ...newEntry, standard_val: e.target.value })}
                                    placeholder="변환 후 단어"
                                />
                            </div>
                        </div>
                        <div className="mt-6 flex justify-end gap-2">
                            <Button variant="outline" onClick={() => setIsAddDialogOpen(false)}>취소</Button>
                            <Button
                                id="add-save-btn"
                                className="bg-blue-600 hover:bg-blue-700"
                                onClick={() => handleAddSave()}
                                disabled={!newEntry.model_id || !newEntry.raw_val || !newEntry.standard_val || addMutation.isPending}
                            >
                                {addMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                                등록
                            </Button>
                        </div>
                    </div>
                </div>
            )}

        </div>
    )
}
