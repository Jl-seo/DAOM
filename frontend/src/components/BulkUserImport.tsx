/**
 * BulkUserImport - CSV/JSON bulk user import component
 * Connects to POST /users/bulk-import endpoint
 */
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Upload, Loader2, CheckCircle, Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { toast } from 'sonner'
import apiClient from '@/lib/api'

interface BulkUserEntry {
    email: string
    name: string
    groups: string[]
}

interface BulkImportResult {
    total: number
    created: number
    updated: number
    failed: number
    errors: string[]
}

export function BulkUserImport({ onSuccess }: { onSuccess?: () => void }) {
    const [users, setUsers] = useState<BulkUserEntry[]>([])
    const [isDragging, setIsDragging] = useState(false)

    const importMutation = useMutation({
        mutationFn: async (userList: BulkUserEntry[]) => {
            const res = await apiClient.post<BulkImportResult>('/users/bulk-import', { users: userList })
            return res.data
        },
        onSuccess: (result) => {
            toast.success(`${result.created}명 생성, ${result.updated}명 업데이트 완료`)
            if (result.errors.length > 0) {
                toast.warning(`${result.failed}명 실패`, {
                    description: result.errors.slice(0, 3).join('\n')
                })
            }
            setUsers([])
            onSuccess?.()
        },
        onError: (error) => {
            toast.error('일괄 등록 실패', { description: String(error) })
        }
    })

    const handleFileUpload = (file: File) => {
        const reader = new FileReader()
        reader.onload = (e) => {
            const text = e.target?.result as string
            try {
                // Try JSON first
                const data = JSON.parse(text)
                if (Array.isArray(data)) {
                    setUsers(data)
                    toast.success(`${data.length}명 로드됨`)
                    return
                }
            } catch {
                // Try CSV
                const lines = text.split('\n').filter(l => l.trim())
                if (lines.length > 1) {
                    const headers = lines[0].split(',').map(h => h.trim().toLowerCase())
                    const emailIdx = headers.indexOf('email')
                    const nameIdx = headers.indexOf('name')
                    const groupsIdx = headers.indexOf('groups')

                    if (emailIdx === -1 || nameIdx === -1) {
                        toast.error('CSV에 email, name 컬럼이 필요합니다')
                        return
                    }

                    const parsed = lines.slice(1).map(line => {
                        const cols = line.split(',').map(c => c.trim())
                        return {
                            email: cols[emailIdx] || '',
                            name: cols[nameIdx] || '',
                            groups: groupsIdx >= 0 ? cols[groupsIdx]?.split(';').map(g => g.trim()).filter(Boolean) : []
                        }
                    }).filter(u => u.email && u.name)

                    setUsers(parsed)
                    toast.success(`${parsed.length}명 로드됨`)
                    return
                }
            }
            toast.error('파일 형식을 확인해주세요 (JSON 또는 CSV)')
        }
        reader.readAsText(file)
    }

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault()
        setIsDragging(false)
        const file = e.dataTransfer.files[0]
        if (file) handleFileUpload(file)
    }

    const downloadTemplate = () => {
        const csv = 'email,name,groups\nuser@example.com,홍길동,Sales Team;Dev Team'
        const blob = new Blob([csv], { type: 'text/csv' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'bulk_users_template.csv'
        a.click()
        URL.revokeObjectURL(url)
    }

    return (
        <Card className="p-6">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold">사용자 일괄 등록</h3>
                <Button variant="outline" size="sm" onClick={downloadTemplate}>
                    <Download className="w-4 h-4 mr-2" />
                    템플릿 다운로드
                </Button>
            </div>

            {/* Drop Zone */}
            <div
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={handleDrop}
                className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${isDragging ? 'border-primary bg-primary/5' : 'border-muted-foreground/30'
                    }`}
            >
                <Upload className="w-8 h-8 mx-auto mb-2 text-muted-foreground" />
                <p className="text-muted-foreground">CSV 또는 JSON 파일을 드래그하거나</p>
                <label className="mt-2 inline-block">
                    <input
                        type="file"
                        accept=".csv,.json"
                        className="hidden"
                        onChange={(e) => e.target.files?.[0] && handleFileUpload(e.target.files[0])}
                    />
                    <span className="text-primary cursor-pointer hover:underline">파일 선택</span>
                </label>
            </div>

            {/* Preview */}
            {users.length > 0 && (
                <div className="mt-4">
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-muted-foreground">{users.length}명 준비됨</span>
                        <Button
                            onClick={() => importMutation.mutate(users)}
                            disabled={importMutation.isPending}
                        >
                            {importMutation.isPending ? (
                                <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> 처리 중...</>
                            ) : (
                                <><CheckCircle className="w-4 h-4 mr-2" /> 일괄 등록</>
                            )}
                        </Button>
                    </div>

                    <div className="max-h-40 overflow-y-auto border rounded text-sm">
                        <table className="w-full">
                            <thead className="bg-muted/50 sticky top-0">
                                <tr>
                                    <th className="px-2 py-1 text-left">이메일</th>
                                    <th className="px-2 py-1 text-left">이름</th>
                                    <th className="px-2 py-1 text-left">그룹</th>
                                </tr>
                            </thead>
                            <tbody>
                                {users.slice(0, 10).map((user, i) => (
                                    <tr key={i} className="border-t">
                                        <td className="px-2 py-1">{user.email}</td>
                                        <td className="px-2 py-1">{user.name}</td>
                                        <td className="px-2 py-1 text-muted-foreground">{user.groups.join(', ') || '-'}</td>
                                    </tr>
                                ))}
                                {users.length > 10 && (
                                    <tr className="border-t">
                                        <td colSpan={3} className="px-2 py-1 text-center text-muted-foreground">
                                            ... 외 {users.length - 10}명
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </Card>
    )
}
