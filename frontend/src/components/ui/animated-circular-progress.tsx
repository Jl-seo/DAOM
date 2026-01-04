'use client'

import { useEffect, useState } from 'react'
import { motion, useSpring } from 'framer-motion'
import { cn } from '@/lib/utils'

interface AnimatedCircularProgressProps {
    value: number
    max?: number
    min?: number
    size?: number
    strokeWidth?: number
    className?: string
    gaugePrimaryColor?: string
    gaugeSecondaryColor?: string
    showValue?: boolean
    children?: React.ReactNode
}

export function AnimatedCircularProgress({
    value,
    max = 100,
    min = 0,
    size = 120,
    strokeWidth = 10,
    className,
    gaugePrimaryColor,
    _gaugeSecondaryColor,
    showValue = true,
    children
}: AnimatedCircularProgressProps) {
    const [mounted, setMounted] = useState(false)
    const [displayValue, setDisplayValue] = useState(0)

    useEffect(() => {
        setMounted(true)
    }, [])

    const normalizedValue = Math.min(Math.max(value, min), max)
    const percentage = ((normalizedValue - min) / (max - min)) * 100

    const radius = (size - strokeWidth) / 2
    const circumference = 2 * Math.PI * radius

    // Spring animation for smooth progress
    const springValue = useSpring(0, { damping: 30, stiffness: 100 })

    useEffect(() => {
        springValue.set(percentage)
        const unsubscribe = springValue.on('change', (v) => {
            setDisplayValue(Math.round(v))
        })
        return unsubscribe
    }, [percentage, springValue])

    // Calculate stroke-dashoffset based on percentage
    const strokeDashoffset = circumference - (circumference * percentage) / 100

    if (!mounted) return null

    return (
        <div
            className={cn("relative inline-flex items-center justify-center", className)}
            style={{ width: size, height: size }}
        >
            {/* Background circle */}
            <div
                className="absolute inset-0 rounded-full border-4 border-muted opacity-30"
                style={{ borderWidth: strokeWidth }}
            />

            {/* Spinning ring - always rotating! */}
            <div
                className="absolute inset-0 rounded-full border-4 border-primary border-t-transparent animate-spin"
                style={{ borderWidth: strokeWidth }}
            />

            {/* Progress arc SVG overlay */}
            <svg
                width={size}
                height={size}
                viewBox={`0 0 ${size} ${size}`}
                className="absolute inset-0 transform -rotate-90"
            >
                {/* Progress circle with glow */}
                <motion.circle
                    cx={size / 2}
                    cy={size / 2}
                    r={radius}
                    fill="none"
                    stroke={gaugePrimaryColor || 'hsl(var(--primary))'}
                    strokeWidth={strokeWidth}
                    strokeLinecap="round"
                    strokeDasharray={circumference}
                    initial={{ strokeDashoffset: circumference }}
                    animate={{
                        strokeDashoffset,
                        opacity: [0.6, 1, 0.6] // Pulse opacity
                    }}
                    transition={{
                        strokeDashoffset: { duration: 0.8, ease: 'easeOut' },
                        opacity: { duration: 1.5, repeat: Infinity, ease: 'easeInOut' }
                    }}
                    className="drop-shadow-[0_0_12px_hsl(var(--primary)/0.7)]"
                />
            </svg>

            {/* Center content with subtle pulse */}
            <motion.div
                className="absolute inset-0 flex flex-col items-center justify-center z-10"
                animate={{
                    scale: [1, 1.02, 1]
                }}
                transition={{
                    duration: 2,
                    repeat: Infinity,
                    ease: 'easeInOut'
                }}
            >
                {children || (showValue && (
                    <span className="text-2xl font-bold text-foreground">
                        {displayValue}
                        <span className="text-lg text-muted-foreground">%</span>
                    </span>
                ))}
            </motion.div>
        </div>
    )
}
