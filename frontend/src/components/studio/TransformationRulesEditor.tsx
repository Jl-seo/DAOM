/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Play, Sparkles, CheckCircle2, RotateCcw } from 'lucide-react'
import type { Model } from '@/types/model'
import { API_CONFIG } from '@/constants'
import { useAuth } from '@/auth/AuthContext'

interface TransformationRulesEditorProps {
    model: Model
    onUpdate: (model: Model) => void
}

export function TransformationRulesEditor({ model, onUpdate }: TransformationRulesEditorProps) {
    const [naturalInput, setNaturalInput] = useState(model.transformation_config?.natural_language_rule || '')
    const [parsing, setParsing] = useState(false)
    const [parsedRules, setParsedRules] = useState<any[]>(model.transformation_config?.parsed_rules || [])
    const [testResult, setTestResult] = useState<any>(null)
    const [testing, setTesting] = useState(false)
    const [activeTab, setActiveTab] = useState('editor')

    const textareaRef = useRef<HTMLTextAreaElement>(null)
    const { getAccessToken } = useAuth()

    const availableFields = model.fields.map(f => f.key)

    const insertVariable = (fieldKey: string) => {
        if (!textareaRef.current) return

        const start = textareaRef.current.selectionStart
        const end = textareaRef.current.selectionEnd
        const text = naturalInput
        const newText = text.substring(0, start) + `@{${fieldKey}}` + text.substring(end)

        setNaturalInput(newText)

        // Restore cursor position after insert
        setTimeout(() => {
            if (textareaRef.current) {
                const newPos = start + fieldKey.length + 3
                textareaRef.current.focus()
                textareaRef.current.setSelectionRange(newPos, newPos)
            }
        }, 0)
    }

    const handleParse = async () => {
        if (!naturalInput.trim()) return
        setParsing(true)
        try {
            const token = await getAccessToken()
            const response = await fetch(`${API_CONFIG.BASE_URL}/transformation/parse`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    text: naturalInput,
                    available_fields: availableFields
                })
            })

            if (response.ok) {
                const data = await response.json()
                setParsedRules(data.rules)
                setActiveTab('preview')

                // Update model locally
                onUpdate({
                    ...model,
                    transformation_config: {
                        natural_language_rule: naturalInput,
                        parsed_rules: data.rules,
                        last_updated: new Date().toISOString()
                    }
                })
            }
        } catch (error) {
            console.error('Failed to parse rules:', error)
        } finally {
            setParsing(false)
        }
    }

    const handleTest = async () => {
        if (parsedRules.length === 0) return
        setTesting(true)
        try {
            const token = await getAccessToken()
            // In a real app, we would fetch recent extraction data here
            // For MVP, we use some dummy data based on fields
            const dummyData: Record<string, any> = {
                "Base_Rate": 1000,
                "POL": "Incheon",
                "POL_List": ["Busan", "Incheon", "Gwangyang"],
                "POD_List": ["LA", "NYC"]
            }

            // Populate dummy data based on available fields to make it realistic
            availableFields.forEach(f => {
                if (!dummyData[f]) dummyData[f] = `Sample ${f}`
            })

            const response = await fetch(`${API_CONFIG.BASE_URL}/transformation/test`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    rules: parsedRules,
                    sample_data: dummyData
                })
            })

            if (response.ok) {
                const data = await response.json()
                setTestResult(data)
            }
        } catch (error) {
            console.error('Test failed:', error)
        } finally {
            setTesting(false)
        }
    }

    return (
        <div className="flex flex-col h-full space-y-4 p-1">
            <div className="bg-blue-50/50 p-4 rounded-lg border border-blue-100 dark:bg-blue-900/10 dark:border-blue-800">
                <h3 className="text-sm font-semibold mb-2 text-blue-800 dark:text-blue-300">사용 가능한 변수 (클릭하여 삽입)</h3>
                <div className="flex flex-wrap gap-2">
                    {availableFields.map(field => (
                        <Badge
                            key={field}
                            variant="secondary"
                            className="cursor-pointer hover:bg-blue-100 hover:text-blue-700 transition-colors px-2 py-1 text-xs"
                            onClick={() => insertVariable(field)}
                        >
                            @{field}
                        </Badge>
                    ))}
                    {availableFields.length === 0 && (
                        <span className="text-muted-foreground text-xs italic">정의된 모델 필드가 없습니다. 먼저 추출 필드를 설정해주세요.</span>
                    )}
                </div>
            </div>

            <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col">
                <TabsList className="grid w-full grid-cols-2">
                    <TabsTrigger value="editor">✏️ 규칙 작성</TabsTrigger>
                    <TabsTrigger value="preview" disabled={parsedRules.length === 0}>👀 해석 결과 & 테스트</TabsTrigger>
                </TabsList>

                <TabsContent value="editor" className="flex-1 flex flex-col space-y-4 mt-4">
                    <div className="flex-1 relative">
                        <Textarea
                            ref={textareaRef}
                            value={naturalInput}
                            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setNaturalInput(e.target.value)}
                            placeholder="예: @{POL_List}와 @{POD_List}의 모든 조합을 만들어줘. 인천 출발은 +50 추가해."
                            className="h-full min-h-[300px] resize-none p-4 font-mono text-sm leading-relaxed"
                        />
                        <div className="absolute bottom-4 right-4">
                            <Button onClick={handleParse} disabled={parsing || !naturalInput.trim()}>
                                {parsing ? (
                                    <>
                                        <Sparkles className="w-4 h-4 mr-2 animate-spin" />
                                        해석 중...
                                    </>
                                ) : (
                                    <>
                                        <Sparkles className="w-4 h-4 mr-2" />
                                        규칙 해석하기
                                    </>
                                )}
                            </Button>
                        </div>
                    </div>
                </TabsContent>

                <TabsContent value="preview" className="flex-1 flex flex-col mt-4 overflow-hidden">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 h-full">
                        {/* Processed Rules View */}
                        <Card className="h-full overflow-hidden flex flex-col">
                            <div className="p-3 border-b bg-muted/30 font-semibold text-sm flex justify-between items-center">
                                <span>기계가 이해한 규칙 ({parsedRules.length}개)</span>
                                <Button variant="ghost" size="sm" onClick={handleParse}>
                                    <RotateCcw className="w-3 h-3 mr-1" /> 재해석
                                </Button>
                            </div>
                            <CardContent className="p-0 overflow-auto flex-1 bg-slate-50 dark:bg-slate-950">
                                <pre className="p-4 text-xs font-mono whitespace-pre-wrap">
                                    {JSON.stringify(parsedRules, null, 2)}
                                </pre>
                            </CardContent>
                        </Card>

                        {/* Test Panel */}
                        <Card className="h-full overflow-hidden flex flex-col">
                            <div className="p-3 border-b bg-muted/30 font-semibold text-sm flex justify-between items-center">
                                <span>테스트 실행</span>
                                <Button size="sm" onClick={handleTest} disabled={testing}>
                                    {testing ? '실행 중...' : <><Play className="w-3 h-3 mr-1" /> 테스트 실행</>}
                                </Button>
                            </div>
                            <CardContent className="p-0 overflow-auto flex-1">
                                {testResult ? (
                                    <div className="p-4 space-y-4">
                                        <div className="space-y-2">
                                            <div className="flex items-center gap-2">
                                                <CheckCircle2 className="w-4 h-4 text-green-500" />
                                                <h4 className="font-semibold text-sm">변환 결과</h4>
                                            </div>
                                            <pre className="p-2 bg-slate-100 dark:bg-slate-900 rounded text-xs font-mono overflow-auto max-h-[300px]">
                                                {JSON.stringify(testResult.result, null, 2)}
                                            </pre>
                                        </div>

                                        {testResult.audit && testResult.audit.length > 0 && (
                                            <div className="space-y-2">
                                                <h4 className="font-semibold text-sm">실행 로그</h4>
                                                <div className="space-y-1">
                                                    {testResult.audit.map((log: any, idx: number) => (
                                                        <div key={idx} className={`text-xs p-1 rounded flex gap-2 ${log.status === 'failed' ? 'bg-red-100 text-red-700' : 'bg-green-50/50 text-green-700'}`}>
                                                            <span className="font-bold">[{log.type}]</span>
                                                            <span>{log.status === 'failed' ? log.error : 'Success'}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                ) : (
                                    <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
                                        테스트를 실행하여 결과를 확인하세요
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    </div>
                </TabsContent>
            </Tabs>
        </div>
    )
}
