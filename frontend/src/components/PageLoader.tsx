import { Loader2 } from 'lucide-react'

/**
 * Loading fallback component for lazy-loaded routes.
 * Shows a centered spinner with skeleton pulse animation
 * and descriptive loading message.
 */
export function PageLoader() {
    return (
        <div className="min-h-screen flex items-center justify-center bg-background animate-in fade-in duration-300">
            <div className="text-center space-y-6">
                {/* Animated spinner */}
                <div className="relative">
                    <div className="w-16 h-16 rounded-full border-4 border-muted" />
                    <Loader2 className="w-16 h-16 absolute inset-0 animate-spin text-primary" />
                </div>

                {/* Text */}
                <div className="space-y-2">
                    <p className="text-sm font-medium text-foreground">페이지를 불러오는 중...</p>
                    <p className="text-xs text-muted-foreground">잠시만 기다려주세요</p>
                </div>

                {/* Skeleton preview */}
                <div className="w-64 space-y-3 mx-auto">
                    <div className="h-3 bg-muted rounded-full animate-pulse" />
                    <div className="h-3 bg-muted rounded-full animate-pulse w-4/5" />
                    <div className="h-3 bg-muted rounded-full animate-pulse w-3/5" />
                </div>
            </div>
        </div>
    )
}
