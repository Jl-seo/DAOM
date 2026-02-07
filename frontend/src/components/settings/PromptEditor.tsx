/* eslint-disable react-hooks/exhaustive-deps */
import { useState, useEffect } from 'react'
import { FileText, RefreshCw, Save, RotateCcw, Info, GitCompareArrows } from 'lucide-react'
import { toast } from 'sonner'
import axios from 'axios'
import { API_CONFIG } from '../../constants'
import { Button } from '@/components/ui/button'
import { clsx } from 'clsx'

const API_BASE = API_CONFIG.BASE_URL

interface Prompt {
    id: string
    content: string
    description: string
    variables: string[]
    is_default: boolean
    updated_at?: string
    updated_by?: string
}

export function PromptEditor() {
    const [prompts, setPrompts] = useState<Prompt[]>([])
    const [selectedPrompt, setSelectedPrompt] = useState<Prompt | null>(null)
    const [editedContent, setEditedContent] = useState('')
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)

    // Site Settings: Comparison Prompt
    const [comparisonPrompt, setComparisonPrompt] = useState('')
    const [originalComparisonPrompt, setOriginalComparisonPrompt] = useState('')
    const [savingComparison, setSavingComparison] = useState(false)

    useEffect(() => {
        fetchPrompts()
        fetchComparisonPrompt()
    }, [])

    const fetchComparisonPrompt = async () => {
        try {
            const res = await axios.get(`${API_BASE}/settings/site`)
            setComparisonPrompt(res.data.comparisonSystemPrompt || '')
            setOriginalComparisonPrompt(res.data.comparisonSystemPrompt || '')
        } catch (error) {
            console.error('Failed to load site settings:', error)
        }
    }

    const handleSaveComparisonPrompt = async () => {
        setSavingComparison(true)
        try {
            // Get current site settings first
            const currentRes = await axios.get(`${API_BASE}/settings/site`)
            const currentSettings = currentRes.data

            // Update with new comparison prompt
            await axios.put(`${API_BASE}/settings/site`, {
                ...currentSettings,
                comparisonSystemPrompt: comparisonPrompt || null
            })
            setOriginalComparisonPrompt(comparisonPrompt)
            toast.success('비교 프롬프트가 저장되었습니다')
        } catch (error) {
            console.error('Failed to save comparison prompt:', error)
            toast.error('비교 프롬프트 저장 실패')
        } finally {
            setSavingComparison(false)
        }
    }

    const handleResetComparisonPrompt = () => {
        setComparisonPrompt('')
        // Will save as null to use default
    }

    const fetchPrompts = async () => {
        try {
            setLoading(true)
            const res = await axios.get(`${API_BASE}/settings/prompts`)
            const fetchedPrompts = res.data.prompts || []
            setPrompts(fetchedPrompts)

            if (fetchedPrompts.length > 0 && !selectedPrompt) {
                setSelectedPrompt(fetchedPrompts[0])
                setEditedContent(fetchedPrompts[0].content)
            }
        } catch (error) {
            console.error('Failed to load prompts:', error)
            toast.error('프롬프트를 불러올 수 없습니다')
        } finally {
            setLoading(false)
        }
    }

    const handleSelectPrompt = (prompt: Prompt) => {
        setSelectedPrompt(prompt)
        setEditedContent(prompt.content)
    }

    const handleSave = async () => {
        if (!selectedPrompt) return

        setSaving(true)
        try {
            await axios.put(`${API_BASE}/settings/prompts/${selectedPrompt.id}`, {
                content: editedContent,
                description: selectedPrompt.description
            })
            toast.success('프롬프트가 저장되었습니다')
            fetchPrompts()
        } catch (error) {
            console.error('Failed to save:', error)
            toast.error('프롬프트 저장 실패')
        } finally {
            setSaving(false)
        }
    }

    const handleReset = async () => {
        if (!selectedPrompt) return

        if (!confirm('기본값으로 초기화하시겠습니까? 커스텀 내용이 삭제됩니다.')) {
            return
        }

        setSaving(true)
        try {
            await axios.post(`${API_BASE}/settings/prompts/${selectedPrompt.id}/reset`)
            toast.success('프롬프트가 초기화되었습니다')
            fetchPrompts()
        } catch (error) {
            console.error('Failed to reset:', error)
            toast.error('프롬프트 초기화 실패')
        } finally {
            setSaving(false)
        }
    }

    const hasChanges = selectedPrompt && editedContent !== selectedPrompt.content

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <RefreshCw className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
        )
    }

    return (
        <div className="bg-card rounded-xl shadow-sm border border-border">
            {/* Header */}
            <div className="p-4 border-b border-border">
                <div className="flex items-center gap-2 mb-2">
                    <div className="bg-gradient-to-r from-primary to-chart-5 p-2 rounded-lg">
                        <FileText className="w-4 h-4 text-primary-foreground" />
                    </div>
                    <h3 className="font-bold text-base text-foreground">시스템 프롬프트 편집</h3>
                </div>
                <p className="text-sm text-muted-foreground">
                    LLM에게 보내는 시스템 프롬프트를 커스터마이징합니다. 변경 사항은 즉시 적용됩니다.
                </p>
            </div>

            <div className="flex flex-col md:flex-row">
                {/* Prompt List */}
                <div className="w-full md:w-64 border-b md:border-b-0 md:border-r border-border">
                    <div className="p-2">
                        {prompts.map(prompt => (
                            <button
                                key={prompt.id}
                                onClick={() => handleSelectPrompt(prompt)}
                                className={clsx(
                                    "w-full text-left px-3 py-2 rounded-lg text-sm transition-colors mb-1",
                                    selectedPrompt?.id === prompt.id
                                        ? "bg-primary/10 text-primary font-medium"
                                        : "text-muted-foreground hover:bg-muted hover:text-foreground"
                                )}
                            >
                                <div className="font-medium">{prompt.id}</div>
                                <div className="text-xs opacity-70 truncate">{prompt.description}</div>
                                {!prompt.is_default && (
                                    <div className="text-xs text-chart-2 mt-1">✓ 커스텀</div>
                                )}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Editor */}
                <div className="flex-1 p-4">
                    {selectedPrompt ? (
                        <>
                            {/* Variables Info */}
                            {selectedPrompt.variables.length > 0 && (
                                <div className="mb-4 p-3 bg-primary/5 border border-primary/20 rounded-lg">
                                    <div className="flex items-center gap-2 text-sm font-medium text-primary mb-1">
                                        <Info className="w-4 h-4" />
                                        사용 가능한 변수
                                    </div>
                                    <div className="text-xs text-muted-foreground">
                                        {selectedPrompt.variables.map(v => (
                                            <code key={v} className="bg-muted px-1.5 py-0.5 rounded mr-2">
                                                {`{${v}}`}
                                            </code>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Textarea */}
                            <textarea
                                value={editedContent}
                                onChange={(e) => setEditedContent(e.target.value)}
                                className="w-full h-80 px-3 py-2 border border-border rounded-lg text-sm font-mono bg-background focus:outline-none focus:ring-2 focus:ring-ring resize-none"
                                placeholder="프롬프트 내용..."
                            />

                            {/* Actions */}
                            <div className="flex gap-2 mt-4">
                                <Button
                                    onClick={handleSave}
                                    disabled={!hasChanges || saving}
                                    className="flex-1"
                                >
                                    {saving ? (
                                        <RefreshCw className="w-4 h-4 animate-spin mr-2" />
                                    ) : (
                                        <Save className="w-4 h-4 mr-2" />
                                    )}
                                    {saving ? '저장 중...' : hasChanges ? '변경 사항 저장' : '변경 없음'}
                                </Button>

                                <Button
                                    variant="outline"
                                    onClick={handleReset}
                                    disabled={saving || selectedPrompt.is_default}
                                >
                                    <RotateCcw className="w-4 h-4 mr-2" />
                                    기본값 복원
                                </Button>
                            </div>

                            {/* Meta info */}
                            {selectedPrompt.updated_at && (
                                <div className="mt-4 text-xs text-muted-foreground">
                                    마지막 수정: {new Date(selectedPrompt.updated_at).toLocaleString()}
                                    {selectedPrompt.updated_by && ` (${selectedPrompt.updated_by})`}
                                </div>
                            )}
                        </>
                    ) : (
                        <div className="flex items-center justify-center h-64 text-muted-foreground">
                            프롬프트를 선택하세요
                        </div>
                    )}
                </div>
            </div>

            {/* Comparison Prompt Editor Section */}
            <div className="border-t border-border mt-4 pt-4">
                <div className="p-4">
                    <div className="flex items-center gap-2 mb-3">
                        <div className="bg-gradient-to-r from-chart-2 to-chart-3 p-2 rounded-lg">
                            <GitCompareArrows className="w-4 h-4 text-primary-foreground" />
                        </div>
                        <div>
                            <h4 className="font-bold text-base text-foreground">비교 시스템 프롬프트</h4>
                            <p className="text-xs text-muted-foreground">
                                이미지 비교 시 LLM에 전달되는 시스템 프롬프트입니다. 비워두면 기본 프롬프트가 사용됩니다.
                            </p>
                        </div>
                    </div>

                    <textarea
                        value={comparisonPrompt}
                        onChange={(e) => setComparisonPrompt(e.target.value)}
                        className="w-full h-48 px-3 py-2 border border-border rounded-lg text-sm font-mono bg-background focus:outline-none focus:ring-2 focus:ring-ring resize-none"
                        placeholder="예: You are an expert QA and Visual Inspection AI. Compare the two provided images..."
                    />

                    <div className="flex gap-2 mt-3">
                        <Button
                            onClick={handleSaveComparisonPrompt}
                            disabled={comparisonPrompt === originalComparisonPrompt || savingComparison}
                            className="flex-1"
                        >
                            {savingComparison ? (
                                <RefreshCw className="w-4 h-4 animate-spin mr-2" />
                            ) : (
                                <Save className="w-4 h-4 mr-2" />
                            )}
                            {savingComparison ? '저장 중...' : comparisonPrompt !== originalComparisonPrompt ? '비교 프롬프트 저장' : '변경 없음'}
                        </Button>

                        <Button
                            variant="outline"
                            onClick={handleResetComparisonPrompt}
                            disabled={savingComparison || !comparisonPrompt}
                        >
                            <RotateCcw className="w-4 h-4 mr-2" />
                            기본값으로
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    )
}
