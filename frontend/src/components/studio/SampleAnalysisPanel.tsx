import { useState, useEffect } from 'react'
import { Upload, Loader2, Sparkles, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useModels } from '../../hooks/useModels'
import { toast } from 'sonner'
import type { Field } from '../../types/model'

interface SampleAnalysisPanelProps {
    onFieldsFound: (fields: Field[]) => void
    disabled?: boolean
}

interface AnalyzerOption {
    id: string
    name: string
}

export function SampleAnalysisPanel({ onFieldsFound, disabled }: SampleAnalysisPanelProps) {
    const { fetchOptions, analyzeSample } = useModels()
    const [options, setOptions] = useState<AnalyzerOption[]>([])
    const [selectedOption, setSelectedOption] = useState<string>('prebuilt-layout')
    const [file, setFile] = useState<File | null>(null)
    const [isAnalyzing, setIsAnalyzing] = useState(false)
    const [resultCount, setResultCount] = useState<number | null>(null)

    useEffect(() => {
        // Load options on mount
        fetchOptions().then(data => {
            if (data && data.length > 0) {
                setOptions(data)
            }
        })
    }, [fetchOptions])

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files[0]) {
            setFile(e.target.files[0])
            setResultCount(null)
        }
    }

    const handleAnalyze = async () => {
        if (!file) return

        setIsAnalyzing(true)
        try {
            const result = await analyzeSample(file, selectedOption)
            if (result && result.fields) {
                const foundFields = result.fields
                setResultCount(foundFields.length)

                if (foundFields.length > 0) {
                    onFieldsFound(foundFields)
                    toast.success(`${foundFields.length}개의 필드를 찾았습니다!`)
                } else {
                    toast.info('추출 가능한 필드를 찾지 못했습니다.')
                }
            } else {
                toast.error('분석 결과가 유효하지 않습니다.')
            }
        } catch (e) {
            console.error(e)
            toast.error('분석 요청 실패')
        } finally {
            setIsAnalyzing(false)
        }
    }

    if (disabled) return null

    return (
        <div className="p-4 rounded-xl bg-gradient-to-br from-muted/50 to-muted border border-border/50 mb-4">
            <div className="flex items-center gap-2 mb-3">
                <div className="p-1.5 bg-primary/10 rounded-lg">
                    <Sparkles className="w-4 h-4 text-primary" />
                </div>
                <div>
                    <h4 className="font-bold text-sm text-foreground">샘플 문서로 자동 완성</h4>
                    <p className="text-[10px] text-muted-foreground">문서를 업로드하면 AI가 구조를 분석해 필드를 제안합니다.</p>
                </div>
            </div>

            <div className="flex flex-col gap-3">
                <div className="flex gap-2">
                    <select
                        value={selectedOption}
                        onChange={(e) => setSelectedOption(e.target.value)}
                        className="h-9 rounded-md border border-input bg-background px-3 py-1 text-xs font-medium shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                        disabled={isAnalyzing}
                    >
                        {options.map(opt => (
                            <option key={opt.id} value={opt.id}>{opt.name}</option>
                        ))}
                    </select>

                    <div className="flex-1 relative">
                        <input
                            type="file"
                            accept=".pdf,.png,.jpg,.jpeg"
                            onChange={handleFileChange}
                            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
                            disabled={isAnalyzing}
                        />
                        <div className="h-9 px-3 border border-dashed border-input bg-background/50 hover:bg-accent rounded-md flex items-center gap-2 text-xs text-muted-foreground transition-colors overflow-hidden">
                            <Upload className="w-3.5 h-3.5 shrink-0" />
                            <span className="truncate">
                                {file ? file.name : "샘플 파일 선택 (PDF, 이미지)"}
                            </span>
                        </div>
                    </div>

                    <Button
                        size="sm"
                        onClick={handleAnalyze}
                        disabled={!file || isAnalyzing}
                        className="shrink-0"
                    >
                        {isAnalyzing ? (
                            <>
                                <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" />
                                분석 중...
                            </>
                        ) : (
                            "분석 & 적용"
                        )}
                    </Button>
                </div>

                {/* Analysis Feedback Area */}
                <div className="flex items-center justify-between px-1">
                    <div className="text-[10px] text-muted-foreground">
                        * 분석 시 Azure 비용이 발생할 수 있습니다.
                    </div>
                </div>
            </div>
        </div>
    )
}
