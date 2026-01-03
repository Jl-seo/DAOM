import React from 'react'
import { X, CheckCircle, Download, Send, ChevronLeft, ChevronRight, FileText, Table as TableIcon, Save } from 'lucide-react'
import { clsx } from 'clsx'
import { toast } from 'sonner'
import { downloadAsExcel } from '../../../utils/excel'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'

interface FileItem {
    id: string
    file: File
    status: 'pending' | 'uploading' | 'processing' | 'complete' | 'error'
    result?: Record<string, any>
    fileUrl?: string
    error?: string
}

interface VerificationModalProps {
    isOpen: boolean
    onClose: () => void
    files: FileItem[]
    onConfirm: () => void
}

type TabType = 'document' | 'data' | 'export'

export function VerificationModal({ isOpen, onClose, files, onConfirm }: VerificationModalProps) {
    const completedFiles = files.filter(f => f.status === 'complete' && f.result)
    const [currentIndex, setCurrentIndex] = React.useState(0)
    const [activeTab, setActiveTab] = React.useState<TabType>('document')

    if (!isOpen || completedFiles.length === 0) return null

    const currentFile = completedFiles[currentIndex]
    const result = currentFile?.result || {}

    const downloadAll = () => {
        const results = completedFiles.map(f => ({
            filename: f.file.name,
            ...Object.fromEntries(Object.entries(f.result!).map(([k, v]) => [k, typeof v === 'object' && v?.value ? v.value : v]))
        }))
        downloadAsExcel(results, `extracted_${completedFiles.length}_files`)
        toast.success('Excel로 받았어요!')
    }

    const goNext = () => setCurrentIndex(i => Math.min(i + 1, completedFiles.length - 1))
    const goPrev = () => setCurrentIndex(i => Math.max(i - 1, 0))

    const tabs = [
        { id: 'document' as TabType, label: '📄 문서 확인', icon: FileText },
        { id: 'data' as TabType, label: '📊 데이터 검토', icon: TableIcon },
        { id: 'export' as TabType, label: '💾 저장하기', icon: Save }
    ]

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
            <Card className="w-[95vw] h-[90vh] flex flex-col overflow-hidden">
                {/* Header */}
                <div className="px-6 py-4 border-b border-border flex items-center justify-between bg-gradient-to-r from-chart-2/10 to-chart-2/5">
                    <div className="flex items-center gap-4">
                        <div className="w-10 h-10 bg-chart-2 text-chart-2-foreground rounded-full flex items-center justify-center">
                            <CheckCircle className="w-5 h-5" />
                        </div>
                        <div>
                            <h2 className="text-xl font-bold text-foreground">내용이 정확한가요?</h2>
                            <p className="text-sm text-muted-foreground">추출된 정보를 확인하고 수정할 수 있어요</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-accent rounded-lg transition-colors">
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {/* File Navigation (for batch) */}
                {completedFiles.length > 1 && (
                    <div className="px-6 py-3 bg-muted border-b border-border flex items-center justify-between">
                        <button
                            onClick={goPrev}
                            disabled={currentIndex === 0}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-lg hover:bg-card disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                            <ChevronLeft className="w-4 h-4" /> 이전 문서
                        </button>
                        <span className="text-sm font-medium text-muted-foreground">
                            {currentIndex + 1} / {completedFiles.length}: <span className="text-foreground">{currentFile.file.name}</span>
                        </span>
                        <button
                            onClick={goNext}
                            disabled={currentIndex === completedFiles.length - 1}
                            className="flex items-center gap-1 px-3 py-1.5 rounded-lg hover:bg-card disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                            다음 문서 <ChevronRight className="w-4 h-4" />
                        </button>
                    </div>
                )}

                {/* Tabs */}
                <div className="border-b border-border bg-card">
                    <div className="flex px-6">
                        {tabs.map(tab => (
                            <button
                                key={tab.id}
                                onClick={() => setActiveTab(tab.id)}
                                className={clsx(
                                    "flex items-center gap-2 px-6 py-4 font-medium border-b-2 transition-all",
                                    activeTab === tab.id
                                        ? "border-primary text-primary bg-primary/5"
                                        : "border-transparent text-muted-foreground hover:text-foreground hover:bg-accent"
                                )}
                            >
                                <tab.icon className="w-5 h-5" />
                                {tab.label}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Tab Content */}
                <div className="flex-1 overflow-hidden">
                    {/* Document Tab */}
                    {activeTab === 'document' && (
                        <div className="h-full overflow-auto bg-muted flex items-center justify-center p-6">
                            {currentFile.fileUrl ? (
                                currentFile.file.type.includes('pdf') ? (
                                    <iframe src={currentFile.fileUrl} className="w-full h-full rounded-xl shadow-lg" />
                                ) : (
                                    <img src={currentFile.fileUrl} className="max-w-full max-h-full object-contain rounded-xl shadow-lg" alt="Document" />
                                )
                            ) : (
                                <div className="text-center text-muted-foreground">
                                    <FileText className="w-16 h-16 mx-auto mb-4" />
                                    <p className="text-lg">미리보기를 사용할 수 없어요</p>
                                    <p className="text-sm">{currentFile.file.name}</p>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Data Tab */}
                    {activeTab === 'data' && (
                        <div className="h-full overflow-auto p-6">
                            <div className="max-w-5xl mx-auto">
                                <Card className="overflow-hidden">
                                    <table className="w-full">
                                        <thead className="bg-gradient-to-r from-muted to-muted/50 sticky top-0">
                                            <tr>
                                                <th className="px-6 py-4 text-left text-sm font-semibold text-muted-foreground w-1/3">필드</th>
                                                <th className="px-6 py-4 text-left text-sm font-semibold text-muted-foreground">추출된 값</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-border">
                                            {Object.entries(result).map(([key, value], i) => (
                                                <tr key={i} className="hover:bg-accent/50 transition-colors">
                                                    <td className="px-6 py-4 font-medium text-foreground">{key}</td>
                                                    <td className="px-6 py-4">
                                                        <Input
                                                            type="text"
                                                            defaultValue={typeof value === 'object' ? (value?.value || JSON.stringify(value)) : String(value || '')}
                                                            placeholder="값을 입력하세요"
                                                        />
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </Card>
                            </div>
                        </div>
                    )}

                    {/* Export Tab */}
                    {activeTab === 'export' && (
                        <div className="h-full overflow-auto p-6 bg-muted">
                            <div className="max-w-2xl mx-auto space-y-6">
                                {/* Summary */}
                                <Card className="p-6">
                                    <h3 className="font-semibold text-foreground mb-4">작업 요약</h3>
                                    <div className="space-y-2 text-sm">
                                        <div className="flex justify-between">
                                            <span className="text-muted-foreground">처리된 문서</span>
                                            <span className="font-medium text-foreground">{completedFiles.length}개</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-muted-foreground">추출된 필드</span>
                                            <span className="font-medium text-foreground">{Object.keys(result).length}개</span>
                                        </div>
                                    </div>
                                </Card>

                                {/* Export Options */}
                                <div className="space-y-4">
                                    <h3 className="font-semibold text-foreground">내보내기 방법을 선택하세요</h3>

                                    <button
                                        onClick={downloadAll}
                                        className="w-full p-6 bg-gradient-to-r from-chart-2/10 to-chart-2/5 border-2 border-chart-2/20 rounded-xl hover:from-chart-2/20 hover:to-chart-2/10 hover:border-chart-2/40 transition-all group"
                                    >
                                        <div className="flex items-center gap-4">
                                            <div className="w-12 h-12 bg-chart-2 rounded-xl flex items-center justify-center group-hover:scale-110 transition-transform">
                                                <Download className="w-6 h-6 text-primary-foreground" />
                                            </div>
                                            <div className="flex-1 text-left">
                                                <p className="font-semibold text-foreground mb-1">Excel로 받기</p>
                                                <p className="text-sm text-muted-foreground">표 형식으로 저장하고 편집할 수 있어요</p>
                                            </div>
                                        </div>
                                    </button>

                                    <button
                                        onClick={() => toast.info('Power Automate 연동 준비 중이에요')}
                                        className="w-full p-6 bg-gradient-to-r from-chart-5/10 to-chart-5/5 border-2 border-chart-5/20 rounded-xl hover:from-chart-5/20 hover:to-chart-5/10 hover:border-chart-5/40 transition-all group"
                                    >
                                        <div className="flex items-center gap-4">
                                            <div className="w-12 h-12 bg-chart-5 rounded-xl flex items-center justify-center group-hover:scale-110 transition-transform">
                                                <Send className="w-6 h-6 text-primary-foreground" />
                                            </div>
                                            <div className="flex-1 text-left">
                                                <p className="font-semibold text-foreground mb-1">시스템에 연결</p>
                                                <p className="text-sm text-muted-foreground">Power Automate로 자동화 워크플로우 실행</p>
                                            </div>
                                        </div>
                                    </button>
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="px-6 py-4 bg-muted border-t border-border flex items-center justify-between">
                    <Button variant="ghost" onClick={onClose}>
                        닫기
                    </Button>
                    <Button onClick={onConfirm} className="gap-2">
                        <CheckCircle className="w-5 h-5" />
                        확인 완료
                    </Button>
                </div>
            </Card>
        </div>
    )
}
