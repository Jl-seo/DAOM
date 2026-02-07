import { Loader2 } from 'lucide-react'

/**
 * Loading fallback component for lazy-loaded routes
 * Provides better UX during code splitting
 */
export function PageLoader() {
    return (
        <div className="min-h-screen flex items-center justify-center bg-background">
            <div className="text-center">
                <Loader2 className="w-12 h-12 mx-auto mb-4 animate-spin text-primary" />
                <p className="text-muted-foreground">페이지를 불러오는 중...</p>
            </div>
        </div>
    )
}
