import { type LucideIcon, ChevronDown, ChevronRight } from 'lucide-react'
import { clsx } from 'clsx'
import { type ReactNode, isValidElement, type ElementType } from 'react'

interface SidebarItemProps {
    icon: LucideIcon | ReactNode | ElementType
    label: string
    isActive: boolean
    hasSubmenu?: boolean
    isExpanded?: boolean
    onClick: () => void
    className?: string
}

export function SidebarItem({
    icon,
    label,
    isActive,
    hasSubmenu,
    isExpanded,
    onClick,
    className
}: SidebarItemProps) {
    // Determine if icon is a React Element (already instantiated) or a Component (needs instantiation)
    const isElement = isValidElement(icon)
    const IconComponent = !isElement ? (icon as ElementType) : null

    return (
        <button
            onClick={onClick}
            className={clsx(
                "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all",
                isActive
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-sidebar-foreground/60 hover:bg-sidebar-accent hover:text-sidebar-foreground",
                className
            )}
        >
            {isElement ? (
                <span className="w-5 h-5 flex items-center justify-center">
                    {icon}
                </span>
            ) : (
                IconComponent && <IconComponent className="w-5 h-5" />
            )}

            <span className="flex-1 text-left font-medium">{label}</span>

            {hasSubmenu && (
                isExpanded ? (
                    <ChevronDown className="w-4 h-4 ml-auto" />
                ) : (
                    <ChevronRight className="w-4 h-4 ml-auto" />
                )
            )}
        </button>
    )
}
