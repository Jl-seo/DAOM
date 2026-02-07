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
    tooltip?: string
}

export function SidebarItem({
    icon,
    label,
    isActive,
    hasSubmenu,
    isExpanded,
    onClick,
    className,
    tooltip
}: SidebarItemProps) {
    // Determine if icon is a React Element (already instantiated) or a Component (needs instantiation)
    const isElement = isValidElement(icon)
    const IconComponent = !isElement ? (icon as ElementType) : null
    const isCollapsed = !label && !!tooltip

    return (
        <button
            onClick={onClick}
            title={tooltip}
            className={clsx(
                "w-full flex items-center rounded-lg transition-all",
                isCollapsed ? "justify-center px-2 py-2.5" : "gap-3 px-3 py-2.5",
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

            {label && <span className="flex-1 text-left font-medium">{label}</span>}

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
