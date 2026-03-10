import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Loader2, Download, Upload, Plus, Search } from 'lucide-react'
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

export function VibeDictionaryPage() {
    const queryClient = useQueryClient()
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

    const { data: entries = [], isLoading } = useQuery({
        queryKey: ['vibe-dictionary'],
        queryFn: async () => {
            const res = await apiClient.get('/vibe-dictionary')
            return res.data as VibeEntry[]
        }
    })

    const { data: availableModels = [] } = useQuery({
        queryKey: ['extraction-models-list'],
        queryFn: async () => {
            const res = await apiClient.get('/models')
            return res.data as { id: string, name: string }[]
        }
    })

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

    const filtered = entries.filter(e =>
        e.raw_val.toLowerCase().includes(searchTerm.toLowerCase()) ||
        e.standard_val.toLowerCase().includes(searchTerm.toLowerCase()) ||
        e.model_name.toLowerCase().includes(searchTerm.toLowerCase())
    )

    return (
        <div className="flex-1 flex flex-col h-full bg-slate-50 relative animate-in fade-in duration-300">
            {/* Header */}
            <div className="p-6 pb-4 bg-white border-b sticky top-0 z-10">
                <h1 className="text-2xl font-bold flex items-center gap-2 text-slate-800">
                    Vibe Dictionary
                </h1>
                <p className="text-sm text-slate-500 mt-1">
                    LLM 기능 교정을 통해 시스템에 적립된 용어 치환 내역(음차 대응 등)을 조회 및 관리합니다.
                </p>
            </div>

            <div className="flex-1 p-6 overflow-auto">
                <Card className="flex flex-col h-full bg-white shadow-sm border-slate-200">

                    {/* Toolbar */}
                    <div className="flex items-center justify-between p-4 border-b bg-slate-50/50">
                        <div className="text-sm font-medium text-slate-600">
                            선택된 항목: {filtered.length}개
                        </div>

                        <div className="flex items-center gap-2">
                            <Button variant="outline" size="sm" className="h-8 gap-1.5 hidden sm:flex">
                                <Download className="w-3.5 h-3.5" /> CSV 다운로드
                            </Button>
                            <Button variant="outline" size="sm" className="h-8 gap-1.5 hidden sm:flex mr-2">
                                <Upload className="w-3.5 h-3.5" /> 업로드
                            </Button>

                            <div className="relative w-48 sm:w-64">
                                <Search className="w-4 h-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
                                <Input
                                    placeholder="용어 검색"
                                    className="h-8 pl-8 text-sm"
                                    value={searchTerm}
                                    onChange={e => setSearchTerm(e.target.value)}
                                />
                            </div>

                            <Button
                                size="sm"
                                className="h-8 gap-1.5 bg-blue-600 hover:bg-blue-700 ml-2"
                                onClick={() => setIsAddDialogOpen(true)}
                            >
                                <Plus className="w-3.5 h-3.5" /> 수동 등록
                            </Button>
                        </div>
                    </div>

                    {/* Data Table */}
                    <div className="flex-1 overflow-auto rounded-b-xl border-t-0">
                        {isLoading ? (
                            <div className="w-full h-40 flex items-center justify-center">
                                <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
                            </div>
                        ) : filtered.length === 0 ? (
                            <div className="w-full h-40 flex flex-col items-center justify-center text-slate-400">
                                <Search className="w-8 h-8 mb-2 opacity-50" />
                                <p>표시할 딕셔너리 데이터가 없습니다.</p>
                            </div>
                        ) : (
                            <table className="w-full text-sm text-left">
                                <thead className="text-xs text-slate-500 uppercase bg-slate-50 sticky top-0 z-10 shadow-sm">
                                    <tr>
                                        <th className="px-4 py-3 font-medium w-10 text-center"><input type="checkbox" className="rounded border-slate-300" /></th>
                                        <th className="px-4 py-3 font-medium text-slate-500">Persona</th>
                                        <th className="px-4 py-3 font-medium text-slate-500">Source (음차/오인식)</th>
                                        <th className="px-4 py-3 font-medium text-slate-500">Target (전문용어)</th>
                                        <th className="px-4 py-3 font-medium text-slate-500 text-center">추출 유형</th>
                                        <th className="px-4 py-3 font-medium text-slate-500 text-center">적용 카운트(Hit)</th>
                                        <th className="px-4 py-3 font-medium text-slate-500 text-center">상태</th>
                                        <th className="px-4 py-3 font-medium text-slate-500 text-right pr-6">관리</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100">
                                    {filtered.map((entry, idx) => (
                                        <tr key={`${entry.model_id}-${entry.raw_val}-${idx}`} className="hover:bg-blue-50/30 transition-colors group">
                                            <td className="px-4 py-3 text-center"><input type="checkbox" className="rounded border-slate-300" /></td>
                                            <td className="px-4 py-3 text-slate-500 text-xs">{entry.model_name} <span className="text-slate-300">({entry.field_name})</span></td>
                                            <td className="px-4 py-3 font-medium text-slate-900">{entry.raw_val}</td>
                                            <td className="px-4 py-3 font-bold text-blue-600 flex items-center gap-2">
                                                <span className="text-slate-300">→</span> {entry.standard_val}
                                            </td>
                                            <td className="px-4 py-3 text-center">
                                                <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium ${entry.source === 'AI_GENERATED' ? 'bg-purple-100 text-purple-700' : 'bg-slate-100 text-slate-700'
                                                    }`}>
                                                    {entry.source === 'AI_GENERATED' ? 'LLM 오토 적립' : '수동 등록'}
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
            </div>

            {/* Edit Dialog */}
            {isEditDialogOpen && editingEntry && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6 animate-in zoom-in-95 duration-200">
                        <h2 className="text-xl font-bold mb-4">단어 매핑 수정</h2>
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Source (음차/오인식)</label>
                                <Input value={editingEntry.raw_val} disabled className="bg-slate-50 text-slate-500" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Target (전문용어)</label>
                                <Input
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
                                <label className="block text-sm font-medium text-slate-700 mb-1">Model ID (Persona)</label>
                                <select
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
                                <label className="block text-sm font-medium text-slate-700 mb-1">Field Name (Optional)</label>
                                <Input
                                    value={newEntry.field_name}
                                    onChange={e => setNewEntry({ ...newEntry, field_name: e.target.value })}
                                    placeholder="적용할 필드명 (전체는 default)"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Source (원문/오인식)</label>
                                <Input
                                    value={newEntry.raw_val}
                                    onChange={e => setNewEntry({ ...newEntry, raw_val: e.target.value })}
                                    placeholder="변환 전 단어"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Target (전문용어/표준어)</label>
                                <Input
                                    value={newEntry.standard_val}
                                    onChange={e => setNewEntry({ ...newEntry, standard_val: e.target.value })}
                                    placeholder="변환 후 단어"
                                />
                            </div>
                        </div>
                        <div className="mt-6 flex justify-end gap-2">
                            <Button variant="outline" onClick={() => setIsAddDialogOpen(false)}>취소</Button>
                            <Button
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
