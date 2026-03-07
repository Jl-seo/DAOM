import { motion } from 'framer-motion'
import { ArrowLeft, Settings2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { EXTRACTION_TABS } from '../constants'
import type { ViewStep } from '../types'

interface ExtractionTabsHeaderProps {
    activeStep: ViewStep
    modelName: string
    modelId?: string
    onStepChange: (step: ViewStep) => void
    onCancel: () => void
    hasData: boolean // Determines if results tabs are clickable
}

export function ExtractionTabsHeader({
    activeStep,
    modelName,
    modelId,
    onStepChange,
    onCancel,
    hasData
}: ExtractionTabsHeaderProps) {
    const navigate = useNavigate()
    const tabs = EXTRACTION_TABS

    return (
        <div className="bg-card border-b px-6 py-2 shadow-sm z-10 flex flex-col gap-3">
            {/* Top Toolbar */}
            <div className="flex items-center justify-between">
                <Button
                    variant="ghost"
                    onClick={onCancel}
                    className="gap-3 pl-2 pr-4 text-muted-foreground hover:text-foreground h-9 hover:bg-muted/50 transition-colors"
                >
                    <ArrowLeft className="w-4 h-4" />
                    {modelName} 목록으로 나가기
                </Button>

                {modelId && (
                    <Button
                        id="btn-model-settings"
                        variant="outline"
                        size="sm"
                        onClick={() => navigate(`/admin/model-studio?modelId=${modelId}&from=extraction`)}
                        className="gap-2 text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors h-8"
                    >
                        <Settings2 className="w-4 h-4" />
                        모델 설정
                    </Button>
                )}
            </div>

            {/* Tab Navigation */}
            <div className="flex items-center gap-1 bg-muted/30 p-1 rounded-lg self-start">
                {tabs.map((tab) => {
                    const Icon = tab.icon
                    const isActive = activeStep === tab.id
                    // Tabs are clickable if it's the upload tab, or if we have data (for result tabs)
                    const isClickable = tab.id === 'upload' || hasData

                    return (
                        <button
                            key={tab.id}
                            onClick={() => isClickable && onStepChange(tab.id as ViewStep)}
                            disabled={!isClickable}
                            className={cn(
                                'relative flex items-center gap-2 px-4 py-2 rounded-md transition-all duration-200 text-sm font-medium outline-none',
                                isActive
                                    ? 'bg-background text-primary shadow-sm'
                                    : isClickable
                                        ? 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                                        : 'text-muted-foreground/40 cursor-not-allowed hidden md:flex'
                            )}
                            title={tab.description}
                        >
                            <Icon className="w-4 h-4" />
                            <span>{tab.label}</span>

                            {/* Active Indicator Line */}
                            {isActive && (
                                <motion.div
                                    layoutId="activeTabIndicator"
                                    className="absolute bottom-[-5px] left-0 right-0 h-0.5 bg-primary rounded-t-full"
                                    transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                                />
                            )}
                        </button>
                    )
                })}
            </div>
        </div>
    )
}
