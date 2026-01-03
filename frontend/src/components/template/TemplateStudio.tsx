import { useState } from 'react'
import { X, Download, Printer } from 'lucide-react'
import { TemplateChat } from './TemplateChat'
import { TemplatePreview } from './TemplatePreview'
import type { TemplateConfig } from '../../types/template'
import { defaultTemplateConfig } from '../../types/template'
import { Button } from '@/components/ui/button'

interface TemplateStudioProps {
    modelId: string
    modelName: string
    modelFields: Array<{ key: string; label: string; type: string }>
    onClose: () => void
    onSave?: (template: TemplateConfig) => void
}

export function TemplateStudio({
    modelId,
    modelName,
    modelFields,
    onClose,
    onSave
}: TemplateStudioProps) {
    const [config, setConfig] = useState<Partial<TemplateConfig>>({
        ...defaultTemplateConfig,
        modelId,
        name: `${modelName} 템플릿`
    })

    const handleConfigUpdate = (newConfig: Partial<TemplateConfig>) => {
        setConfig(prev => ({ ...prev, ...newConfig }))
    }

    const handleSave = () => {
        const fullConfig: TemplateConfig = {
            id: crypto.randomUUID(),
            modelId,
            name: config.name || '새 템플릿',
            layout: config.layout || 'table',
            columns: config.columns || [],
            style: config.style || defaultTemplateConfig.style,
            header: config.header,
            footer: config.footer,
            aggregation: config.aggregation,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString()
        }
        onSave?.(fullConfig)
        onClose()
    }

    const handlePrint = () => {
        window.print()
    }

    return (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-muted rounded-2xl w-full max-w-6xl h-[85vh] flex flex-col overflow-hidden shadow-2xl">
                {/* Header */}
                <div className="px-6 py-4 bg-card border-b border-border flex items-center justify-between">
                    <div>
                        <h2 className="text-lg font-bold text-foreground">🎨 템플릿 스튜디오</h2>
                        <p className="text-sm text-muted-foreground">{modelName} 모델의 출력 형태를 디자인하세요</p>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button variant="ghost" onClick={handlePrint}>
                            <Printer className="w-4 h-4 mr-2" />
                            인쇄
                        </Button>
                        <Button onClick={handleSave}>
                            <Download className="w-4 h-4 mr-2" />
                            저장
                        </Button>
                        <Button variant="ghost" size="icon" onClick={onClose}>
                            <X className="w-5 h-5" />
                        </Button>
                    </div>
                </div>

                {/* Main Content */}
                <div className="flex-1 flex gap-4 p-4 overflow-hidden">
                    {/* Left: Chat */}
                    <div className="w-[360px] shrink-0">
                        <TemplateChat
                            onConfigUpdate={handleConfigUpdate}
                            modelFields={modelFields}
                            currentConfig={config}
                        />
                    </div>

                    {/* Right: Preview */}
                    <div className="flex-1 print:absolute print:inset-0 print:bg-white">
                        <TemplatePreview config={config} />
                    </div>
                </div>

                {/* Footer - Template Name */}
                <div className="px-6 py-3 bg-card border-t border-border flex items-center gap-4">
                    <label className="text-sm font-medium text-muted-foreground">템플릿 이름:</label>
                    <input
                        type="text"
                        value={config.name || ''}
                        onChange={(e) => setConfig(prev => ({ ...prev, name: e.target.value }))}
                        className="flex-1 max-w-md px-3 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-ring bg-background"
                        placeholder="템플릿 이름 입력"
                    />
                </div>
            </div>
        </div>
    )
}
