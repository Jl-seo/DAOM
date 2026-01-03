import { useState, useRef, useEffect } from 'react'
import { Send, Loader2, Sparkles } from 'lucide-react'
import type { ChatMessage, TemplateConfig } from '../../types/template'

interface TemplateChatProps {
    onConfigUpdate: (config: Partial<TemplateConfig>) => void
    modelFields: Array<{ key: string; label: string; type: string }>
    currentConfig: Partial<TemplateConfig>
}

export function TemplateChat({ onConfigUpdate, modelFields, currentConfig }: TemplateChatProps) {
    const [messages, setMessages] = useState<ChatMessage[]>([
        {
            id: '1',
            role: 'assistant',
            content: '안녕하세요! 어떤 형태로 데이터를 출력하고 싶으신가요? 예: "테이블 형태로 만들어줘", "헤더에 제목 추가해줘"',
            timestamp: new Date()
        }
    ])
    const [input, setInput] = useState('')
    const [isLoading, setIsLoading] = useState(false)
    const messagesEndRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, [messages])

    const handleSend = async () => {
        if (!input.trim() || isLoading) return

        const userMessage: ChatMessage = {
            id: Date.now().toString(),
            role: 'user',
            content: input,
            timestamp: new Date()
        }

        setMessages(prev => [...prev, userMessage])
        setInput('')
        setIsLoading(true)

        try {
            const response = await fetch('http://localhost:8000/api/v1/templates/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: input,
                    currentConfig,
                    modelFields
                })
            })

            if (response.ok) {
                const data = await response.json()

                const assistantMessage: ChatMessage = {
                    id: (Date.now() + 1).toString(),
                    role: 'assistant',
                    content: data.message,
                    config: data.config,
                    timestamp: new Date()
                }

                setMessages(prev => [...prev, assistantMessage])

                if (data.config) {
                    onConfigUpdate(data.config)
                }
            } else {
                throw new Error('API error')
            }
        } catch {
            const assistantMessage = processLocalCommand(input, currentConfig, modelFields)
            setMessages(prev => [...prev, assistantMessage])
            if (assistantMessage.config) {
                onConfigUpdate(assistantMessage.config)
            }
        } finally {
            setIsLoading(false)
        }
    }

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            handleSend()
        }
    }

    return (
        <div className="flex flex-col h-full bg-sidebar rounded-xl overflow-hidden">
            {/* Header */}
            <div className="px-4 py-3 border-b border-sidebar-border flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-chart-5" />
                <span className="text-sm font-bold text-sidebar-foreground">AI 템플릿 어시스턴트</span>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {messages.map(msg => (
                    <div
                        key={msg.id}
                        className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                    >
                        <div
                            className={`max-w-[85%] px-4 py-2.5 rounded-2xl text-sm ${msg.role === 'user'
                                ? 'bg-primary text-primary-foreground rounded-br-md'
                                : 'bg-sidebar-accent text-sidebar-accent-foreground rounded-bl-md'
                                }`}
                        >
                            {msg.role === 'assistant' && (
                                <span className="text-chart-5 text-xs font-medium block mb-1">🤖 AI</span>
                            )}
                            {msg.content}
                        </div>
                    </div>
                ))}
                {isLoading && (
                    <div className="flex justify-start">
                        <div className="bg-sidebar-accent text-sidebar-accent-foreground px-4 py-2.5 rounded-2xl rounded-bl-md">
                            <Loader2 className="w-4 h-4 animate-spin" />
                        </div>
                    </div>
                )}
                <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="p-3 border-t border-sidebar-border">
                <div className="flex gap-2">
                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="템플릿 수정 요청..."
                        className="flex-1 bg-sidebar-accent text-sidebar-foreground px-4 py-2.5 rounded-xl text-sm placeholder:text-muted-foreground outline-none focus:ring-2 focus:ring-primary"
                    />
                    <button
                        onClick={handleSend}
                        disabled={isLoading || !input.trim()}
                        className="px-4 py-2.5 bg-primary hover:bg-primary/90 disabled:bg-muted disabled:text-muted-foreground text-primary-foreground rounded-xl transition-colors"
                    >
                        <Send className="w-4 h-4" />
                    </button>
                </div>
            </div>
        </div>
    )
}

function processLocalCommand(
    input: string,
    currentConfig: Partial<TemplateConfig>,
    modelFields: Array<{ key: string; label: string; type: string }>
): ChatMessage {
    const lowerInput = input.toLowerCase()
    let config: Partial<TemplateConfig> = { ...currentConfig }
    let message = ''

    if (lowerInput.includes('테이블') || lowerInput.includes('표')) {
        config.layout = 'table'
        config.columns = modelFields.map(f => ({
            field: f.key,
            label: f.label || f.key,
            align: f.type === 'number' ? 'right' : 'left',
            format: f.type === 'number' ? 'number' : 'text'
        }))
        message = `테이블 형태로 변경했어요! ${modelFields.length}개 컬럼을 포함했습니다. 컬럼 순서나 스타일을 조정할까요?`
    } else if (lowerInput.includes('헤더') || lowerInput.includes('제목')) {
        const titleMatch = input.match(/['""'](.+?)['""']/)
        config.header = {
            ...config.header,
            title: titleMatch ? titleMatch[1] : '데이터 보고서'
        }
        message = `헤더에 제목을 추가했어요! 부제목이나 로고도 넣을까요?`
    } else if (lowerInput.includes('합계') || lowerInput.includes('총')) {
        config.aggregation = { ...config.aggregation, showTotal: true }
        message = '합계 행을 추가했어요! 평균이나 개수도 표시할까요?'
    } else if (lowerInput.includes('색') || lowerInput.includes('컬러')) {
        if (lowerInput.includes('빨간') || lowerInput.includes('red')) {
            config.style = { ...config.style, primaryColor: '#ef4444' } as any
            message = '주요 색상을 빨간색으로 변경했어요!'
        } else if (lowerInput.includes('파란') || lowerInput.includes('blue')) {
            config.style = { ...config.style, primaryColor: '#3b82f6' } as any
            message = '주요 색상을 파란색으로 변경했어요!'
        } else {
            message = '어떤 색상을 원하시나요? 예: "빨간색으로 해줘"'
        }
    } else if (lowerInput.includes('크게') || lowerInput.includes('폰트')) {
        const currentSize = config.style?.fontSize || 14
        config.style = { ...config.style, fontSize: currentSize + 2 } as any
        message = `폰트 크기를 ${currentSize + 2}pt로 키웠어요!`
    } else {
        message = '죄송해요, 잘 이해하지 못했어요. "테이블로 만들어줘", "헤더 추가해줘", "합계 보여줘" 같이 말씀해주세요!'
        config = currentConfig
    }

    return {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: message,
        config,
        timestamp: new Date()
    }
}
