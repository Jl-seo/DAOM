import * as React from 'react'
import type { LucideIcon } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'

interface IconCardProps {
    icon: LucideIcon
    title: string
    children: React.ReactNode
}

export function IconCard({ icon: Icon, title, children }: IconCardProps) {
    return (
        <Card>
            <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-sm font-bold">
                    <Icon className="w-4 h-4 text-primary" />
                    {title}
                </CardTitle>
            </CardHeader>
            <CardContent>
                {children}
            </CardContent>
        </Card>
    )
}

// Alias for backwards compatibility
export { IconCard as Card }
