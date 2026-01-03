import { CheckCircle2 } from 'lucide-react'
import { clsx } from 'clsx'
import { DATA_STRUCTURES } from '../../constants'
import { getIconComponent } from '../../utils/iconMapper'
import type { DataStructureType } from '../../types/model'

interface DataStructureSelectorProps {
    value: DataStructureType
    onChange: (value: DataStructureType) => void
    disabled?: boolean
}

export function DataStructureSelector({ value, onChange, disabled = false }: DataStructureSelectorProps) {
    return (
        <div className="grid grid-cols-3 gap-2">
            {DATA_STRUCTURES.map((structure) => {
                const IconComponent = getIconComponent(structure.iconName)
                const isSelected = value === structure.id

                return (
                    <button
                        key={structure.id}
                        onClick={() => !disabled && onChange(structure.id)}
                        disabled={disabled}
                        className={clsx(
                            "flex flex-col items-center gap-2 p-3 rounded-lg border-2 transition-all relative",
                            isSelected
                                ? "border-primary bg-primary/10 shadow-sm scale-[1.02]"
                                : "border-border hover:border-primary/50 hover:bg-accent",
                            disabled && "cursor-not-allowed opacity-60"
                        )}
                    >
                        <IconComponent className={clsx(
                            "w-6 h-6",
                            isSelected ? "text-primary" : "text-muted-foreground"
                        )} />
                        <div className="flex flex-col items-center">
                            <span className={clsx(
                                "text-xs font-bold",
                                isSelected ? "text-primary" : "text-foreground"
                            )}>{structure.label}</span>
                            <span className={clsx(
                                "text-[10px]",
                                isSelected ? "text-primary/80" : "text-muted-foreground"
                            )}>{structure.desc}</span>
                        </div>
                        {isSelected && (
                            <div className="absolute top-1.5 right-1.5">
                                <CheckCircle2 className="w-3 h-3 text-primary" />
                            </div>
                        )}
                    </button>
                )
            })}
        </div>
    )
}
