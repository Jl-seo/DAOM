
import { Card } from '@/components/ui/icon-card'
// import { Button } from '@/components/ui/button' -> Removed unused import
import { Switch } from '@/components/ui/switch'
import { FileSpreadsheet, GripVertical } from 'lucide-react'
import type { ExcelExportColumn } from '../ModelStudio'

interface ExcelColumnEditorProps {
    columns: ExcelExportColumn[] | undefined;
    onChange: (columns: ExcelExportColumn[]) => void;
    disabled?: boolean;
}

export function ExcelColumnEditor({ columns, onChange, disabled }: ExcelColumnEditorProps) {
    // Default columns if undefined
    const currentColumns = columns || [
        { key: 'category', label: '카테고리', width: 15, enabled: true },
        { key: 'page_number', label: '페이지', width: 10, enabled: true },
        { key: 'description', label: '차이점 설명', width: 60, enabled: true },
        { key: 'confidence', label: '신뢰도', width: 10, enabled: true },
        { key: 'candidate', label: '후보 파일', width: 20, enabled: true }
    ]

    const handleColumnChange = (index: number, field: keyof ExcelExportColumn, value: any) => {
        const newColumns = [...currentColumns]
        newColumns[index] = { ...newColumns[index], [field]: value }
        onChange(newColumns)
    }

    // Unused functions removed
    // const handleAddColumn...

    // const handleDeleteColumn...

    return (
        <Card icon={FileSpreadsheet} title="Excel 내보내기 설정">
            <div className="space-y-4">
                <p className="text-xs text-muted-foreground mb-4">
                    비교/추출 결과를 엑셀로 내보낼 때 포함될 열을 정의합니다. 순서대로 엑셀에 출력됩니다.
                </p>

                <div className="space-y-2">
                    {currentColumns.map((col, idx) => (
                        <div key={idx} className="flex items-center gap-2 p-2 bg-muted/30 rounded-lg border group">
                            <GripVertical className="w-4 h-4 text-muted-foreground cursor-grab" />

                            <div className="flex-1 grid grid-cols-12 gap-2">
                                <div className="col-span-4">
                                    <input
                                        type="text"
                                        value={col.label}
                                        onChange={(e) => handleColumnChange(idx, 'label', e.target.value)}
                                        placeholder="열 이름"
                                        disabled={disabled}
                                        className="w-full px-2 py-1 text-sm bg-transparent border-b border-transparent focus:border-primary focus:outline-none"
                                    />
                                </div>
                                <div className="col-span-4">
                                    <input
                                        type="text"
                                        value={col.key}
                                        readOnly
                                        disabled
                                        className="w-full px-2 py-1 text-xs font-mono text-muted-foreground bg-muted/50 border-b border-transparent cursor-not-allowed"
                                        title="시스템 키는 수정할 수 없습니다"
                                    />
                                </div>
                                <div className="col-span-2 flex items-center">
                                    <span className="text-xs text-muted-foreground mr-1">W:</span>
                                    <input
                                        type="number"
                                        value={col.width}
                                        onChange={(e) => handleColumnChange(idx, 'width', parseInt(e.target.value))}
                                        disabled={disabled}
                                        className="w-12 px-1 py-1 text-xs bg-transparent border-b border-transparent focus:border-primary focus:outline-none text-right"
                                    />
                                </div>
                                <div className="col-span-2 flex items-center justify-end gap-2">
                                    <Switch
                                        checked={col.enabled}
                                        onCheckedChange={(checked: boolean) => handleColumnChange(idx, 'enabled', checked)}
                                        disabled={disabled}
                                        className="scale-75"
                                    />
                                    {/* 삭제 버튼 비활성화 (필요 시 enabled로 제어) */}
                                    {/* 
                                    <button
                                        onClick={() => handleDeleteColumn(idx)}
                                        disabled={disabled}
                                        className="p-1 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-opacity"
                                    >
                                        <Trash2 className="w-3.5 h-3.5" />
                                    </button>
                                    */}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>

                {/* 열 추가 비활성화 - 데이터 소스가 고정되어 있으므로 임의 키 추가 불가 */}
                {/* 
                <Button
                    variant="outline"
                    size="sm"
                    className="w-full border-dashed"
                    onClick={handleAddColumn}
                    disabled={disabled}
                >
                    <Plus className="w-3.5 h-3.5 mr-1" />
                    열 추가
                </Button>
                */}
            </div>
        </Card>
    )
}
