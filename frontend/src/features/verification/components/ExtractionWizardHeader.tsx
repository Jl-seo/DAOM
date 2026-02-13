import { motion } from 'framer-motion'
import { ArrowLeft, Settings2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { WIZARD_STEPS } from '../constants'
import type { ViewStep } from '../types'

interface ExtractionWizardHeaderProps {
    activeStep: ViewStep
    modelName: string
    modelId?: string
    onStepChange: (step: ViewStep) => void
    onCancel: () => void
}

export function ExtractionWizardHeader({
    activeStep,
    modelName,
    modelId,
    onStepChange,
    onCancel
}: ExtractionWizardHeaderProps) {
    const navigate = useNavigate()
    const steps = WIZARD_STEPS

    const currentStepIndex = steps.findIndex(s => s.id === activeStep)

    return (
        <div className="bg-card border-b px-6 py-4 shadow-sm z-10">
            <div className="flex items-center justify-between mb-4">
                <Button
                    variant="ghost"
                    onClick={onCancel}
                    className="gap-3 pl-6 pr-4 text-muted-foreground hover:text-foreground h-10 hover:bg-muted/50 transition-colors"
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
                        className="gap-2 text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
                    >
                        <Settings2 className="w-4 h-4" />
                        모델 설정
                    </Button>
                )}
            </div>

            <div className="flex items-center justify-between relative max-w-3xl mx-auto px-4">
                {steps.map((step, index) => {
                    const Icon = step.icon
                    const isActive = activeStep === step.id
                    const isCompleted = index < currentStepIndex
                    const isClickable = index <= currentStepIndex

                    return (
                        <div key={step.id} className="flex-1 flex items-center relative">
                            <button
                                onClick={() => isClickable && onStepChange(step.id)}
                                disabled={!isClickable}
                                className={cn(
                                    'relative z-10 flex flex-col items-center gap-2 transition-all duration-300 group',
                                    isClickable ? 'cursor-pointer' : 'cursor-not-allowed opacity-50'
                                )}
                            >
                                <motion.div
                                    className={cn(
                                        'w-12 h-12 rounded-full flex items-center justify-center border-2 transition-all duration-300 shadow-sm',
                                        isCompleted
                                            ? 'bg-primary border-primary text-primary-foreground'
                                            : isActive
                                                ? 'bg-card border-primary text-primary ring-4 ring-primary/10'
                                                : 'bg-muted border-border text-muted-foreground'
                                    )}
                                    whileHover={isClickable ? { scale: 1.05 } : {}}
                                    whileTap={isClickable ? { scale: 0.95 } : {}}
                                >
                                    <Icon className="w-5 h-5" />
                                </motion.div>
                                <span className={cn(
                                    'text-sm font-medium transition-colors',
                                    isActive ? 'text-primary' : isCompleted ? 'text-foreground' : 'text-muted-foreground'
                                )}>
                                    {step.label}
                                </span>
                            </button>

                            {index < steps.length - 1 && (
                                <div className="flex-1 h-1 bg-muted-foreground/20 relative mx-4 rounded-full overflow-hidden">
                                    <motion.div
                                        className="absolute inset-0 bg-primary origin-left"
                                        initial={{ scaleX: 0 }}
                                        animate={{
                                            scaleX: index < currentStepIndex ? 1 : 0
                                        }}
                                        transition={{
                                            duration: 0.5,
                                            ease: "easeInOut"
                                        }}
                                    />
                                </div>
                            )}
                        </div>
                    )
                })}
            </div>
        </div>
    )
}
