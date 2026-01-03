import { useState, useEffect, useCallback } from 'react'
import {
    Shield, Search, X, Building,
    Loader2, RefreshCw, FolderPlus, Trash2, Plus, UserPlus, Globe, ChevronDown, ChevronRight
} from 'lucide-react'
import { groupsApi, modelsApi, menusApi, type GroupInfo, type ModelPermission, type MenuInfo } from '../lib/api'
import { useGraphApi, type EntraUser, type EntraGroup } from '../hooks/useGraphApi'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card } from '@/components/ui/card'

type SearchType = 'user' | 'entra_group'

export function UserManagement() {
    const [groups, setGroups] = useState<GroupInfo[]>([])
    const [models, setModels] = useState<{ id: string, name: string }[]>([])
    const [menus, setMenus] = useState<MenuInfo[]>([])
    const [loading, setLoading] = useState(true)
    const [searchTerm, setSearchTerm] = useState('')
    const [expandedGroup, setExpandedGroup] = useState<string | null>(null)

    const { searchUsers: searchEntraUsers, searchGroups: searchEntraGroups, loading: graphLoading, error: graphError } = useGraphApi()

    const [showGroupModal, setShowGroupModal] = useState(false)
    const [groupName, setGroupName] = useState('')
    const [groupDesc, setGroupDesc] = useState('')
    const [isSuperAdmin, setIsSuperAdmin] = useState(false)
    const [creatingGroup, setCreatingGroup] = useState(false)

    const [showAddMemberModal, setShowAddMemberModal] = useState(false)
    const [selectedGroup, setSelectedGroup] = useState<GroupInfo | null>(null)
    const [memberSearchType, setMemberSearchType] = useState<SearchType>('user')
    const [memberSearchTerm, setMemberSearchTerm] = useState('')
    const [entraSearchResults, setEntraSearchResults] = useState<(EntraUser | EntraGroup)[]>([])
    const [addingMember, setAddingMember] = useState(false)

    const [showPermissionsModal, setShowPermissionsModal] = useState(false)
    const [editingGroupPermissions, setEditingGroupPermissions] = useState<GroupInfo | null>(null)
    const [permSuperAdmin, setPermSuperAdmin] = useState(false)
    const [permModels, setPermModels] = useState<ModelPermission[]>([])
    const [permMenus, setPermMenus] = useState<string[]>([])

    const fetchData = useCallback(async () => {
        setLoading(true)
        try {
            const [groupsRes, modelsRes, menusRes] = await Promise.all([
                groupsApi.getAll(),
                modelsApi.getAll(),
                menusApi.getAll()
            ])
            setGroups(groupsRes.data)
            setModels(modelsRes.data.map(m => ({ id: m.id, name: m.name })))
            setMenus(menusRes.data)
        } catch (error) {
            console.error('Failed to fetch data:', error)
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        fetchData()
    }, [fetchData])

    useEffect(() => {
        if (!showAddMemberModal || memberSearchTerm.length < 2) {
            setEntraSearchResults([])
            return
        }

        const doSearch = async () => {
            if (memberSearchType === 'user') {
                const results = await searchEntraUsers(memberSearchTerm)
                setEntraSearchResults(results)
            } else {
                const results = await searchEntraGroups(memberSearchTerm)
                setEntraSearchResults(results)
            }
        }

        const timer = setTimeout(doSearch, 300)
        return () => clearTimeout(timer)
    }, [memberSearchTerm, memberSearchType, showAddMemberModal, searchEntraUsers, searchEntraGroups])

    const filteredGroups = groups.filter(group =>
        group.name.toLowerCase().includes(searchTerm.toLowerCase())
    )

    const handleCreateGroup = async () => {
        if (!groupName.trim()) return
        setCreatingGroup(true)
        try {
            await groupsApi.create(groupName, groupDesc, isSuperAdmin)
            toast.success('권한 그룹이 생성되었습니다')
            setShowGroupModal(false)
            setGroupName('')
            setGroupDesc('')
            setIsSuperAdmin(false)
            fetchData()
        } catch {
            toast.error('그룹 생성에 실패했습니다')
        } finally {
            setCreatingGroup(false)
        }
    }

    const handleDeleteGroup = async (groupId: string) => {
        if (!confirm('이 권한 그룹을 삭제하시겠습니까?')) return
        try {
            await groupsApi.deleteGroup(groupId)
            toast.success('그룹이 삭제되었습니다')
            fetchData()
        } catch {
            toast.error('그룹 삭제에 실패했습니다')
        }
    }

    const handleAddMember = async (item: EntraUser | EntraGroup) => {
        if (!selectedGroup) return
        setAddingMember(true)
        try {
            await groupsApi.addMember(selectedGroup.id, memberSearchType, item.id, item.displayName)
            toast.success('멤버가 추가되었습니다')
            fetchData()
            setMemberSearchTerm('')
            setEntraSearchResults([])
        } catch {
            toast.error('멤버 추가에 실패했습니다')
        } finally {
            setAddingMember(false)
        }
    }

    const handleRemoveMember = async (groupId: string, memberId: string) => {
        try {
            await groupsApi.removeMember(groupId, memberId)
            toast.success('멤버가 제거되었습니다')
            fetchData()
        } catch {
            toast.error('멤버 제거에 실패했습니다')
        }
    }

    const openPermissionsModal = (group: GroupInfo) => {
        setEditingGroupPermissions(group)
        setPermSuperAdmin(group.permissions?.superAdmin || false)
        setPermModels(group.permissions?.models || [])
        setPermMenus(group.permissions?.menus || [])
        setShowPermissionsModal(true)
    }

    const handleSavePermissions = async () => {
        if (!editingGroupPermissions) return
        try {
            await groupsApi.setPermissions(editingGroupPermissions.id, permSuperAdmin, permModels, permMenus)
            toast.success('권한이 저장되었습니다')
            setShowPermissionsModal(false)
            fetchData()
        } catch {
            toast.error('권한 저장에 실패했습니다')
        }
    }

    const toggleMenuPermission = (menuId: string) => {
        setPermMenus(prev =>
            prev.includes(menuId)
                ? prev.filter(id => id !== menuId)
                : [...prev, menuId]
        )
    }

    const toggleModelPermission = (modelId: string, modelName: string) => {
        const existing = permModels.find(m => m.modelId === modelId)
        if (existing) {
            if (existing.role === 'User') {
                setPermModels(prev => prev.map(m => m.modelId === modelId ? { ...m, role: 'Admin' as const } : m))
            } else {
                setPermModels(prev => prev.filter(m => m.modelId !== modelId))
            }
        } else {
            setPermModels(prev => [...prev, { modelId, modelName, role: 'User' as const }])
        }
    }

    const toggleExpand = (groupId: string) => {
        setExpandedGroup(prev => prev === groupId ? null : groupId)
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-primary/10 rounded-xl">
                        <Shield className="w-5 h-5 text-primary" />
                    </div>
                    <div>
                        <h2 className="text-xl font-bold text-foreground">권한 그룹 관리</h2>
                        <p className="text-sm text-muted-foreground">그룹을 만들고 Entra 사용자/그룹을 추가하여 권한을 관리합니다</p>
                    </div>
                </div>
                <div className="flex gap-2">
                    <Button variant="ghost" size="icon" onClick={fetchData}>
                        <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
                    </Button>
                    <Button onClick={() => setShowGroupModal(true)}>
                        <FolderPlus className="w-4 h-4 mr-2" />
                        권한 그룹 생성
                    </Button>
                </div>
            </div>

            {/* Search */}
            <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
                <Input
                    type="text"
                    placeholder="권한 그룹 검색..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-10"
                />
            </div>

            {/* Permission Groups List */}
            <div className="space-y-4">
                {loading ? (
                    <div className="flex items-center justify-center py-12">
                        <Loader2 className="w-8 h-8 animate-spin text-primary" />
                    </div>
                ) : groups.length === 0 ? (
                    <div className="bg-gradient-to-br from-primary/10 to-chart-5/10 rounded-2xl border-2 border-dashed border-primary/20 text-center py-16 px-4">
                        <div className="bg-card w-20 h-20 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg">
                            <Shield className="w-10 h-10 text-primary" />
                        </div>
                        <h3 className="text-lg font-bold text-foreground mb-2">권한 그룹이 없습니다</h3>
                        <p className="text-sm text-muted-foreground mb-6 max-w-md mx-auto">
                            권한 그룹을 생성하고 Entra ID의 사용자나 보안 그룹을 추가하여<br />
                            모델과 메뉴에 대한 접근 권한을 관리하세요
                        </p>
                        <Button onClick={() => setShowGroupModal(true)} className="bg-gradient-to-r from-primary to-chart-5">
                            <FolderPlus className="w-5 h-5 mr-2" />
                            첫 권한 그룹 만들기
                        </Button>
                    </div>
                ) : (
                    filteredGroups.map(group => (
                        <Card key={group.id} className="overflow-hidden hover:shadow-lg transition-all duration-200">
                            {/* Group Header */}
                            <div
                                className="flex items-center justify-between p-5 cursor-pointer hover:bg-accent/50 transition-colors"
                                onClick={() => toggleExpand(group.id)}
                            >
                                <div className="flex items-center gap-4 flex-1">
                                    {expandedGroup === group.id ?
                                        <ChevronDown className="w-5 h-5 text-primary" /> :
                                        <ChevronRight className="w-5 h-5 text-muted-foreground" />
                                    }

                                    <div className="flex-1">
                                        <div className="flex items-center gap-3 mb-1">
                                            <h3 className="font-bold text-foreground text-lg">{group.name}</h3>
                                            {group.permissions?.superAdmin && (
                                                <span className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold bg-gradient-to-r from-destructive to-chart-5 text-white rounded-full shadow-sm">
                                                    <Shield className="w-3 h-3" />
                                                    SuperAdmin
                                                </span>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-4 text-sm text-muted-foreground">
                                            <span className="flex items-center gap-1.5">
                                                <div className="flex -space-x-2">
                                                    {group.members?.slice(0, 3).map((_, i) => (
                                                        <div key={i} className="w-6 h-6 rounded-full bg-gradient-to-br from-primary to-chart-5 border-2 border-card" />
                                                    ))}
                                                </div>
                                                <span className="font-medium">{group.members?.length || 0}</span> 멤버
                                            </span>
                                            <span className="text-border">•</span>
                                            <span className="font-medium">{group.permissions?.models?.length || 0}</span> 모델 권한
                                            <span className="text-border">•</span>
                                            <span className="font-medium">{group.permissions?.menus?.length || 0}</span> 메뉴 권한
                                        </div>
                                    </div>
                                </div>

                                <div className="flex gap-2" onClick={e => e.stopPropagation()}>
                                    <Button variant="secondary" size="sm" onClick={() => openPermissionsModal(group)}>
                                        권한 설정
                                    </Button>
                                    <Button variant="outline" size="sm" onClick={() => { setSelectedGroup(group); setShowAddMemberModal(true); setMemberSearchTerm(''); setEntraSearchResults([]) }}>
                                        <UserPlus className="w-4 h-4 mr-1" />
                                        멤버 추가
                                    </Button>
                                    <Button variant="ghost" size="icon" onClick={() => handleDeleteGroup(group.id)} className="text-destructive hover:text-destructive hover:bg-destructive/10">
                                        <Trash2 className="w-4 h-4" />
                                    </Button>
                                </div>
                            </div>

                            {/* Expanded Content */}
                            {expandedGroup === group.id && (
                                <div className="px-5 pb-5 pt-0 border-t border-border bg-muted/50">
                                    <div className="grid grid-cols-2 gap-6 mt-5">
                                        {/* Members Section */}
                                        <Card className="p-4">
                                            <h4 className="text-sm font-bold text-foreground mb-3 flex items-center gap-2">
                                                <div className="w-1.5 h-4 bg-primary rounded-full" />
                                                멤버 목록
                                            </h4>
                                            {group.members?.length === 0 ? (
                                                <div className="text-center py-6">
                                                    <p className="text-sm text-muted-foreground">아직 멤버가 없습니다</p>
                                                    <button
                                                        onClick={() => { setSelectedGroup(group); setShowAddMemberModal(true); setMemberSearchTerm(''); setEntraSearchResults([]) }}
                                                        className="mt-2 text-xs text-primary hover:text-primary/80"
                                                    >
                                                        + 멤버 추가하기
                                                    </button>
                                                </div>
                                            ) : (
                                                <div className="space-y-2">
                                                    {group.members?.map((member) => (
                                                        <div
                                                            key={member.id}
                                                            className={`flex items-center justify-between p-3 rounded-lg transition-colors ${member.type === 'entra_group'
                                                                ? 'bg-chart-1/10 hover:bg-chart-1/20'
                                                                : 'bg-primary/10 hover:bg-primary/20'
                                                                }`}
                                                        >
                                                            <div className="flex items-center gap-3">
                                                                {member.type === 'entra_group' ? (
                                                                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-chart-1 to-chart-3 flex items-center justify-center">
                                                                        <Globe className="w-4 h-4 text-white" />
                                                                    </div>
                                                                ) : (
                                                                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary to-chart-5 flex items-center justify-center text-white text-xs font-bold">
                                                                        {member.displayName?.slice(0, 2).toUpperCase()}
                                                                    </div>
                                                                )}
                                                                <div>
                                                                    <div className="text-sm font-medium text-foreground">{member.displayName}</div>
                                                                    <div className="text-xs text-muted-foreground">
                                                                        {member.type === 'entra_group' ? 'Entra 보안 그룹' : 'Entra 사용자'}
                                                                    </div>
                                                                </div>
                                                            </div>
                                                            <button
                                                                onClick={() => handleRemoveMember(group.id, member.id)}
                                                                className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-card rounded-lg transition-colors"
                                                            >
                                                                <X className="w-4 h-4" />
                                                            </button>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </Card>

                                        {/* Permissions Section */}
                                        <Card className="p-4">
                                            <h4 className="text-sm font-bold text-foreground mb-3 flex items-center gap-2">
                                                <div className="w-1.5 h-4 bg-chart-1 rounded-full" />
                                                권한 요약
                                            </h4>
                                            {group.permissions?.superAdmin ? (
                                                <div className="p-4 bg-gradient-to-br from-destructive/10 to-chart-5/10 rounded-lg border-2 border-destructive/20">
                                                    <div className="flex items-center gap-2 mb-2">
                                                        <Shield className="w-5 h-5 text-destructive" />
                                                        <span className="font-bold text-destructive">슈퍼 관리자</span>
                                                    </div>
                                                    <p className="text-sm text-destructive/80">모든 모델과 메뉴에 대한 전체 접근 권한</p>
                                                </div>
                                            ) : (
                                                <div className="space-y-3">
                                                    {group.permissions?.models?.length === 0 && group.permissions?.menus?.length === 0 ? (
                                                        <div className="text-center py-6">
                                                            <p className="text-sm text-muted-foreground">설정된 권한이 없습니다</p>
                                                            <button
                                                                onClick={() => openPermissionsModal(group)}
                                                                className="mt-2 text-xs text-chart-1 hover:text-chart-1/80"
                                                            >
                                                                + 권한 설정하기
                                                            </button>
                                                        </div>
                                                    ) : (
                                                        <>
                                                            {group.permissions?.models && group.permissions.models.length > 0 && (
                                                                <div>
                                                                    <div className="text-xs font-semibold text-muted-foreground mb-2">모델 권한</div>
                                                                    <div className="space-y-1.5">
                                                                        {group.permissions.models.map((perm) => (
                                                                            <div key={perm.modelId} className="flex items-center justify-between p-2 bg-muted rounded-lg">
                                                                                <span className="text-sm text-foreground">{perm.modelName}</span>
                                                                                <span className={`inline-flex items-center gap-1 text-xs font-medium px-2.5 py-1 rounded-full ${perm.role === 'Admin'
                                                                                    ? 'bg-primary/10 text-primary'
                                                                                    : 'bg-chart-1/10 text-chart-1'
                                                                                    }`}>
                                                                                    {perm.role === 'Admin' ? '⚡ 관리자' : '👁️ 사용자'}
                                                                                </span>
                                                                            </div>
                                                                        ))}
                                                                    </div>
                                                                </div>
                                                            )}
                                                            {group.permissions?.menus && group.permissions.menus.length > 0 && (
                                                                <div>
                                                                    <div className="text-xs font-semibold text-muted-foreground mb-2">메뉴 접근</div>
                                                                    <div className="flex flex-wrap gap-1.5">
                                                                        {group.permissions.menus.slice(0, 5).map((menuId) => {
                                                                            const menu = menus.find(m => m.id === menuId)
                                                                            return menu ? (
                                                                                <span key={menuId} className="inline-flex items-center gap-1 text-xs bg-chart-2/10 text-chart-2 px-2 py-1 rounded-full">
                                                                                    ✓ {menu.name}
                                                                                </span>
                                                                            ) : null
                                                                        })}
                                                                        {group.permissions.menus.length > 5 && (
                                                                            <span className="text-xs text-muted-foreground">+{group.permissions.menus.length - 5} 더보기</span>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                            )}
                                                        </>
                                                    )}
                                                </div>
                                            )}
                                        </Card>
                                    </div>
                                </div>
                            )}
                        </Card>
                    ))
                )}
            </div>

            {/* Create Group Modal */}
            {showGroupModal && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <Card className="p-6 w-full max-w-md">
                        <h3 className="text-lg font-bold text-foreground mb-4">권한 그룹 생성</h3>
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-foreground mb-1">그룹 이름</label>
                                <Input type="text" value={groupName} onChange={(e) => setGroupName(e.target.value)} placeholder="마케팅팀" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-foreground mb-1">설명</label>
                                <Input type="text" value={groupDesc} onChange={(e) => setGroupDesc(e.target.value)} placeholder="설명" />
                            </div>
                            <label className="flex items-center gap-2 p-3 bg-destructive/10 rounded-lg cursor-pointer">
                                <input type="checkbox" checked={isSuperAdmin} onChange={(e) => setIsSuperAdmin(e.target.checked)} className="rounded" />
                                <div>
                                    <div className="font-semibold text-destructive">SuperAdmin</div>
                                    <div className="text-xs text-destructive/80">모든 모델에 대한 전체 권한</div>
                                </div>
                            </label>
                        </div>
                        <div className="flex justify-end gap-2 mt-6">
                            <Button variant="ghost" onClick={() => setShowGroupModal(false)}>취소</Button>
                            <Button onClick={handleCreateGroup} disabled={creatingGroup}>
                                {creatingGroup ? '생성 중...' : '생성'}
                            </Button>
                        </div>
                    </Card>
                </div>
            )}

            {/* Add Member Modal */}
            {showAddMemberModal && selectedGroup && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <Card className="p-6 w-full max-w-lg">
                        <h3 className="text-lg font-bold text-foreground mb-4">"{selectedGroup.name}" 멤버 추가</h3>

                        <div className="flex gap-2 mb-4">
                            <Button
                                variant={memberSearchType === 'user' ? 'default' : 'outline'}
                                className="flex-1"
                                onClick={() => setMemberSearchType('user')}
                            >
                                Entra 사용자
                            </Button>
                            <Button
                                variant={memberSearchType === 'entra_group' ? 'default' : 'outline'}
                                className="flex-1"
                                onClick={() => setMemberSearchType('entra_group')}
                            >
                                Entra 보안 그룹
                            </Button>
                        </div>

                        <div className="relative mb-4">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                            <Input
                                type="text"
                                value={memberSearchTerm}
                                onChange={(e) => setMemberSearchTerm(e.target.value)}
                                placeholder={memberSearchType === 'user' ? "이름 또는 이메일 검색..." : "그룹 이름 검색..."}
                                className="pl-9"
                            />
                        </div>

                        {graphError && <p className="text-sm text-destructive mb-2">{graphError}</p>}

                        <div className="max-h-64 overflow-auto space-y-1">
                            {graphLoading ? (
                                <div className="flex justify-center py-4"><Loader2 className="w-6 h-6 animate-spin text-primary" /></div>
                            ) : entraSearchResults.length === 0 ? (
                                <p className="text-center text-muted-foreground py-4">{memberSearchTerm.length >= 2 ? '검색 결과 없음' : '2자 이상 입력하세요'}</p>
                            ) : (
                                entraSearchResults.map((item) => (
                                    <div key={item.id} className="flex items-center justify-between p-2 hover:bg-accent rounded-lg">
                                        <div className="flex items-center gap-2">
                                            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white font-bold text-xs ${memberSearchType === 'entra_group' ? 'bg-chart-1' : 'bg-gradient-to-br from-primary to-chart-5'}`}>
                                                {memberSearchType === 'entra_group' ? <Globe className="w-4 h-4" /> : item.displayName?.slice(0, 2)}
                                            </div>
                                            <div>
                                                <div className="text-sm font-medium">{item.displayName}</div>
                                                <div className="text-xs text-muted-foreground">
                                                    {memberSearchType === 'user' ? (item as EntraUser).mail : (item as EntraGroup).description || 'Entra 보안 그룹'}
                                                </div>
                                            </div>
                                        </div>
                                        <Button variant="ghost" size="icon" onClick={() => handleAddMember(item)} disabled={addingMember} className="text-primary">
                                            <Plus className="w-4 h-4" />
                                        </Button>
                                    </div>
                                ))
                            )}
                        </div>
                        <div className="flex justify-end mt-4">
                            <Button variant="ghost" onClick={() => setShowAddMemberModal(false)}>닫기</Button>
                        </div>
                    </Card>
                </div>
            )}

            {/* Permissions Modal */}
            {showPermissionsModal && editingGroupPermissions && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <Card className="p-6 w-full max-w-lg max-h-[80vh] overflow-auto">
                        <h3 className="text-lg font-bold text-foreground mb-4">"{editingGroupPermissions.name}" 권한 설정</h3>

                        <label className="flex items-center gap-2 mb-4 p-3 bg-destructive/10 rounded-lg cursor-pointer">
                            <input type="checkbox" checked={permSuperAdmin} onChange={(e) => setPermSuperAdmin(e.target.checked)} className="rounded" />
                            <div>
                                <div className="font-semibold text-destructive">SuperAdmin</div>
                                <div className="text-xs text-destructive/80">모든 모델에 대한 전체 권한</div>
                            </div>
                        </label>

                        {!permSuperAdmin && (
                            <div>
                                <h4 className="font-medium text-foreground mb-2">모델별 권한 (클릭: 없음 → 사용자 → 관리자)</h4>
                                <div className="space-y-2">
                                    {models.length === 0 ? (
                                        <p className="text-sm text-muted-foreground">모델이 없습니다</p>
                                    ) : (
                                        models.map(model => {
                                            const perm = permModels.find(m => m.modelId === model.id)
                                            return (
                                                <div key={model.id} className="flex items-center justify-between p-2 bg-muted rounded-lg">
                                                    <span className="text-sm">{model.name}</span>
                                                    <Button
                                                        variant={perm ? 'default' : 'outline'}
                                                        size="sm"
                                                        onClick={() => toggleModelPermission(model.id, model.name)}
                                                        className={perm?.role === 'Admin' ? 'bg-primary' : perm ? 'bg-chart-1' : ''}
                                                    >
                                                        {perm ? (perm.role === 'Admin' ? '관리자' : '사용자') : '권한 없음'}
                                                    </Button>
                                                </div>
                                            )
                                        })
                                    )}
                                </div>

                                <h4 className="font-medium text-foreground mb-2 mt-4">메뉴 접근 권한</h4>
                                <div className="space-y-2">
                                    {menus.filter(m => !m.parent).map(menu => (
                                        <div key={menu.id} className="space-y-1">
                                            <div className="flex items-center justify-between p-2 bg-muted rounded-lg">
                                                <span className="text-sm font-medium">{menu.name}</span>
                                                <Button
                                                    variant={permMenus.includes(menu.id) ? 'default' : 'outline'}
                                                    size="sm"
                                                    onClick={() => toggleMenuPermission(menu.id)}
                                                    className={permMenus.includes(menu.id) ? 'bg-chart-2' : ''}
                                                >
                                                    {permMenus.includes(menu.id) ? '허용' : '차단'}
                                                </Button>
                                            </div>
                                            {menus.filter(sub => sub.parent === menu.id).map(subMenu => (
                                                <div key={subMenu.id} className="flex items-center justify-between p-2 ml-4 bg-muted/50 rounded-lg">
                                                    <span className="text-sm">{subMenu.name}</span>
                                                    <Button
                                                        variant={permMenus.includes(subMenu.id) ? 'default' : 'outline'}
                                                        size="sm"
                                                        onClick={() => toggleMenuPermission(subMenu.id)}
                                                        className={permMenus.includes(subMenu.id) ? 'bg-chart-2' : ''}
                                                    >
                                                        {permMenus.includes(subMenu.id) ? '허용' : '차단'}
                                                    </Button>
                                                </div>
                                            ))}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        <div className="flex justify-end gap-2 mt-6">
                            <Button variant="ghost" onClick={() => setShowPermissionsModal(false)}>취소</Button>
                            <Button onClick={handleSavePermissions}>저장</Button>
                        </div>
                    </Card>
                </div>
            )}

            {/* Info */}
            <div className="flex items-start gap-3 p-4 bg-chart-1/10 rounded-xl">
                <Building className="w-5 h-5 text-chart-1 mt-0.5" />
                <div>
                    <div className="font-medium text-chart-1">권한 그룹 사용법</div>
                    <div className="text-sm text-chart-1/80">
                        1. 권한 그룹 생성 → 2. Entra 사용자/보안 그룹 검색하여 멤버 추가 → 3. 모델별 권한 설정
                    </div>
                </div>
            </div>
        </div>
    )
}
