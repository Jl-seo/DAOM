import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'

interface AnimatedProgressBarProps {
    value: number
    className?: string
    showGlow?: boolean
    showShimmer?: boolean
    size?: 'sm' | 'md' | 'lg'
}

export function AnimatedProgressBar({
    value,
    className,
    showGlow = true,
    showShimmer = true,
    size = 'md'
}: AnimatedProgressBarProps) {
    const sizeClasses = {
        sm: 'h-1.5',
        md: 'h-2.5',
        lg: 'h-4'
    }

    return (
        <div className={cn("relative w-full rounded-full overflow-hidden", sizeClasses[size], className)}>
            {/* Background track */}
            <div className="absolute inset-0 bg-muted/50" />

            {/* Animated gradient progress */}
            <motion.div
                className="absolute inset-y-0 left-0 rounded-full"
                style={{
                    background: 'linear-gradient(90deg, hsl(var(--primary)) 0%, hsl(var(--chart-4)) 50%, hsl(var(--primary)) 100%)',
                    backgroundSize: '200% 100%',
                }}
                initial={{ width: 0 }}
                animate={{
                    width: `${value}%`,
                    backgroundPosition: ['0% 0%', '100% 0%', '0% 0%']
                }}
                transition={{
                    width: { duration: 0.5, ease: 'easeOut' },
                    backgroundPosition: { duration: 2, repeat: Infinity, ease: 'linear' }
                }}
            />

            {/* Shimmer effect */}
            {showShimmer && value > 0 && value < 100 && (
                <motion.div
                    className="absolute inset-y-0 w-20 opacity-60"
                    style={{
                        background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent)',
                    }}
                    animate={{
                        left: ['-20%', '120%']
                    }}
                    transition={{
                        duration: 1.5,
                        repeat: Infinity,
                        ease: 'easeInOut',
                        repeatDelay: 0.5
                    }}
                />
            )}

            {/* Glow effect */}
            {showGlow && value > 0 && (
                <motion.div
                    className="absolute inset-y-0 left-0 rounded-full blur-sm opacity-50"
                    style={{
                        background: 'hsl(var(--primary))',
                        width: `${value}%`
                    }}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: [0.3, 0.6, 0.3] }}
                    transition={{ duration: 2, repeat: Infinity }}
                />
            )}

            {/* Leading edge glow */}
            {showGlow && value > 0 && value < 100 && (
                <motion.div
                    className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full"
                    style={{
                        left: `calc(${value}% - 6px)`,
                        background: 'hsl(var(--primary))',
                        boxShadow: '0 0 10px hsl(var(--primary)), 0 0 20px hsl(var(--primary)), 0 0 30px hsl(var(--primary))'
                    }}
                    animate={{
                        scale: [1, 1.2, 1],
                        opacity: [0.8, 1, 0.8]
                    }}
                    transition={{ duration: 1, repeat: Infinity }}
                />
            )}
        </div>
    )
}
