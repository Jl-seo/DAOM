import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Copy } from 'lucide-react'
import { useState } from 'react'

interface DebugInfoModalProps {
    isOpen: boolean
    onClose: () => void
    data: any
}

export function DebugInfoModal({ isOpen, onClose, data }: DebugInfoModalProps) {
    const [copied, setCopied] = useState(false)

    const handleCopy = () => {
        navigator.clipboard.writeText(JSON.stringify(data, null, 2))
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
    }

    if (!data) return null

    return (
        <Dialog open={isOpen} onOpenChange={onClose}>
            <DialogContent className="max-w-3xl max-h-[80vh] flex flex-col">
                <DialogHeader>
                    <DialogTitle>Extraction Debug Info</DialogTitle>
                    <DialogDescription>
                        Raw data used for debugging extraction issues.
                    </DialogDescription>
                </DialogHeader>

                <div className="flex justify-end mb-2">
                    <Button variant="outline" size="sm" onClick={handleCopy}>
                        <Copy className="w-4 h-4 mr-2" />
                        {copied ? 'Copied!' : 'Copy JSON'}
                    </Button>
                </div>

                <div className="flex-1 overflow-auto bg-slate-950 text-slate-50 p-4 rounded-md font-mono text-xs">
                    <pre>
                        {JSON.stringify(data, null, 2)}
                    </pre>
                </div>
            </DialogContent>
        </Dialog>
    )
}
