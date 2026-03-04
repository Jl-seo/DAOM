import re

def update_model_studio():
    with open('/Users/seojeonglee/.gemini/antigravity/scratch/daom/frontend/src/components/ModelStudio.tsx', 'r') as f:
        content = f.read()

    # 1. Update imports
    content = content.replace(
        "import {\n    Plus, Trash2, Save, ArrowLeft, Wand2,\n    LayoutTemplate, Edit, Sliders, Database, BookOpen, Search, Settings2\n} from 'lucide-react'",
        "import {\n    Plus, Trash2, Save, ArrowLeft, Wand2,\n    LayoutTemplate, Edit, Sliders, Database, BookOpen, Search, Settings2, FileText, TerminalSquare\n} from 'lucide-react'"
    )

    # 2. Update state
    content = content.replace(
        "const [activeStudioTab, setActiveStudioTab] = useState<'extraction' | 'transformation'>('extraction')",
        "const [activeStudioTab, setActiveStudioTab] = useState<'schema' | 'reference' | 'settings' | 'transformation'>('schema')"
    )

    # 3. Update tabs rendering
    old_tabs = """                    {/* Tabs */}
                    <div className="flex gap-1 bg-muted p-1 rounded-lg shrink-0">
                        <button
                            onClick={() => setActiveStudioTab('extraction')}
                            className={clsx(
                                "flex-1 px-4 py-2 rounded-md text-xs font-bold transition-all",
                                activeStudioTab === 'extraction'
                                    ? "bg-card text-foreground shadow-sm"
                                    : "text-muted-foreground hover:text-foreground"
                            )}
                        >
                            📋 추출 설정
                        </button>
                        <button
                            onClick={() => setActiveStudioTab('transformation')}
                            className={clsx(
                                "flex-1 px-4 py-2 rounded-md text-xs font-bold transition-all",
                                activeStudioTab === 'transformation'
                                    ? "bg-card text-foreground shadow-sm"
                                    : "text-muted-foreground hover:text-foreground"
                            )}
                        >
                            🔄 변환 규칙 (Transformation)
                        </button>
                    </div>"""
    
    new_tabs = """                    {/* Tabs */}
                    <div className="flex gap-1 bg-muted p-1 rounded-lg shrink-0 overflow-x-auto custom-scrollbar">
                        <button
                            onClick={() => setActiveStudioTab('schema')}
                            className={clsx(
                                "whitespace-nowrap flex-1 px-4 py-2 rounded-md text-xs font-bold transition-all flex items-center justify-center gap-2",
                                activeStudioTab === 'schema'
                                    ? "bg-card text-foreground shadow-sm"
                                    : "text-muted-foreground hover:text-foreground"
                            )}
                        >
                            <FileText className="w-4 h-4" /> 추출 스키마
                        </button>
                        <button
                            onClick={() => setActiveStudioTab('reference')}
                            className={clsx(
                                "whitespace-nowrap flex-1 px-4 py-2 rounded-md text-xs font-bold transition-all flex items-center justify-center gap-2",
                                activeStudioTab === 'reference'
                                    ? "bg-card text-foreground shadow-sm"
                                    : "text-muted-foreground hover:text-foreground"
                            )}
                        >
                            <Database className="w-4 h-4" /> 데이터 & 딕셔너리
                        </button>
                        <button
                            onClick={() => setActiveStudioTab('settings')}
                            className={clsx(
                                "whitespace-nowrap flex-1 px-4 py-2 rounded-md text-xs font-bold transition-all flex items-center justify-center gap-2",
                                activeStudioTab === 'settings'
                                    ? "bg-card text-foreground shadow-sm"
                                    : "text-muted-foreground hover:text-foreground"
                            )}
                        >
                            <Settings2 className="w-4 h-4" /> 모델 전역 설정
                        </button>
                        {editingModel?.id && (
                        <button
                            onClick={() => setActiveStudioTab('transformation')}
                            className={clsx(
                                "whitespace-nowrap flex-1 px-4 py-2 rounded-md text-xs font-bold transition-all flex items-center justify-center gap-2",
                                activeStudioTab === 'transformation'
                                    ? "bg-card text-foreground shadow-sm"
                                    : "text-muted-foreground hover:text-foreground"
                            )}
                        >
                            <TerminalSquare className="w-4 h-4" /> 후처리 스크립트
                        </button>
                        )}
                    </div>"""
    content = content.replace(old_tabs, new_tabs)

    # 4. Extract blocks to reorder
    # Let's split using known comments
    
    part_schema_start = content.find("{/* Tab Content */}")
    part_transformation = content.find("{/* Transformation Rules Tab Content */}")
    end_of_divs = content.find("                </div>\n            </div>\n        )\n    }")

    base_before_tabs = content[:part_schema_start]
    tabs_content = content[part_schema_start:part_transformation]
    base_after_tabs = content[part_transformation:]

    # Now let's extract sections from tabs_content
    # SampleAnalysisPanel to Natural Language Command Center -> schema
    # Model Type Selection -> settings
    # AdvancedSchemaEditor & Add Field -> schema
    # SubFieldEditorModal -> schema
    # Comparison Settings, ExcelColumnEditor -> settings
    # Reference Data, Dictionary Panel -> reference
    # Advanced Settings, Model Active toggle -> settings

    # We can do regex or simple splitting
    def extract_section(text, start_marker, end_marker=None):
        start_idx = text.find(start_marker)
        if start_idx == -1: return ""
        if end_marker:
            end_idx = text.find(end_marker, start_idx)
            if end_idx == -1: return ""
            return text[start_idx:end_idx]
        return text[start_idx:]

    s_model_type = extract_section(tabs_content, "{/* Model Type Selection */}", "<div className=\"mt-4 flex flex-col gap-3\">")
    s_advanced_schema = extract_section(tabs_content, "<div className=\"mt-4 flex flex-col gap-3\">\n                            <div className=\"flex items-center gap-2 px-1\">", "{/* Sub-Field Editor UI (Dialog) */}")
    s_sub_field_modal = extract_section(tabs_content, "{/* Sub-Field Editor UI (Dialog) */}", "{/* Comparison Settings - Only show for Comparison Models */}")
    
    s_comparison = extract_section(tabs_content, "{/* Comparison Settings - Only show for Comparison Models */}", "{/* Data Structure — DEPRECATED: auto-detected from field types")
    if not s_comparison:
         s_comparison = extract_section(tabs_content, "{/* Comparison Settings - Only show for Comparison Models */}", "{/* Reference Data (Phase 1) */}")
    
    s_reference = extract_section(tabs_content, "{/* Reference Data (Phase 1) */}", "{/* Dictionary Engine */}")
    s_dictionary = extract_section(tabs_content, "{/* Dictionary Engine */}", "{/* Advanced Settings */}")
    s_advanced = extract_section(tabs_content, "{/* Advanced Settings */}", "                        </div>\n                    )}")

    # Remove these from the original tabs_content so we have the top part (Command center etc) left
    top_schema = tabs_content.replace(s_model_type, "").replace(s_advanced_schema, "").replace(s_sub_field_modal, "").replace(s_comparison, "").replace(s_reference, "").replace(s_dictionary, "").replace(s_advanced, "")

    # Top schema usually contains {activeStudioTab === 'extraction' && (...)} wrapper. We will replace 'extraction' with 'schema'
    top_schema = top_schema.replace("activeStudioTab === 'extraction'", "activeStudioTab === 'schema'")
    
    # We must properly close and open divs for each tab.
    # New Tab: Schema
    # top_schema currently has:
    # {activeStudioTab === 'schema' && (
    #    <div className="flex-1 overflow-y-auto space-y-5 custom-scrollbar pr-2 pb-20">
    #      ... SampleAnalysis ... Command Center ...
    # Wait, top_schema also has the closing `</div> )}` if we didn't extract it out.
    # We extracted EVERYTHING up to `</div> )}`.
    # Let's rebuild the content.
    
    # Extract the stuff inside the extraction wrapper
    wrapper_start = "{/* Tab Content */}\n                    {activeStudioTab === 'extraction' && (\n                        <div className=\"flex-1 overflow-y-auto space-y-5 custom-scrollbar pr-2 pb-20\">\n"
    wrapper_start_new = "{/* Tab Content */}\n                    {activeStudioTab === 'schema' && (\n                        <div className=\"flex-1 overflow-y-auto space-y-5 custom-scrollbar pr-2 pb-20\">\n"
    
    # Find what's inside the wrapper initially
    start_body = tabs_content.find('pb-20">') + len('pb-20">\n')
    end_body = tabs_content.rfind('                        </div>\n                    )}')
    
    body_content = tabs_content[start_body:end_body]
    
    s_model_type = extract_section(body_content, "{/* Model Type Selection */}", "<div className=\"mt-4 flex flex-col gap-3\">")
    s_advanced_schema = extract_section(body_content, "<div className=\"mt-4 flex flex-col gap-3\">\n                                <div className=\"flex items-center gap-2 px-1\">", "{/* Sub-Field Editor UI (Dialog) */}")
    # Fix indent variations:
    s_advanced_schema = extract_section(body_content, "<div className=\"mt-4 flex flex-col gap-3\">", "{/* Sub-Field Editor UI (Dialog) */}")
    s_sub_field_modal = extract_section(body_content, "{/* Sub-Field Editor UI (Dialog) */}", "{/* Comparison Settings - Only show for Comparison Models */}")
    
    s_comparison = extract_section(body_content, "{/* Comparison Settings - Only show for Comparison Models */}", "{/* Data Structure — DEPRECATED")
    if not s_comparison:
        s_comparison = extract_section(body_content, "{/* Comparison Settings - Only show for Comparison Models */}", "{/* Reference Data (Phase 1) */}")
        
    s_reference = extract_section(body_content, "{/* Reference Data (Phase 1) */}", "{/* Dictionary Engine */}")
    s_dictionary = extract_section(body_content, "{/* Dictionary Engine */}", "{/* Advanced Settings */}")
    s_advanced = extract_section(body_content, "{/* Advanced Settings */}")

    s_top_schema = body_content.replace(s_model_type, "").replace(s_advanced_schema, "").replace(s_sub_field_modal, "").replace(s_comparison, "").replace(s_reference, "").replace(s_dictionary, "").replace(s_advanced, "")

    # Reconstruct blocks
    schema_block = f'''
                    {{/* Schema Tab Content */}}
                    {{activeStudioTab === 'schema' && (
                        <div className="flex-1 overflow-y-auto space-y-5 custom-scrollbar pr-2 pb-20">
{s_top_schema}{s_advanced_schema}{s_sub_field_modal}                        </div>
                    )}}'''

    reference_block = f'''
                    {{/* Reference Tab Content */}}
                    {{activeStudioTab === 'reference' && (
                        <div className="flex-1 overflow-y-auto space-y-5 custom-scrollbar pr-2 pb-20">
{s_reference}{s_dictionary}                        </div>
                    )}}'''

    settings_block = f'''
                    {{/* Settings Tab Content */}}
                    {{activeStudioTab === 'settings' && (
                        <div className="flex-1 overflow-y-auto space-y-5 custom-scrollbar pr-2 pb-20">
{s_model_type}{s_comparison}{s_advanced}                        </div>
                    )}}'''

    new_tabs_content = schema_block + reference_block + settings_block + "\n"
    
    final_content = base_before_tabs + new_tabs_content + base_after_tabs
    
    with open('/Users/seojeonglee/.gemini/antigravity/scratch/daom/frontend/src/components/ModelStudio.tsx', 'w') as f:
        f.write(final_content)

if __name__ == '__main__':
    update_model_studio()
