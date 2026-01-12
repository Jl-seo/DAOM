import { useState, useEffect, useCallback } from 'react'
import {
    Shield, Search, X, Building,
    Loader2, RefreshCw, FolderPlus, Trash2, Plus, UserPlus, Globe, ChevronDown, ChevronRight
} from 'lucide-react'
import { groupsApi, modelsApi, menusApi, usersApi, type GroupInfo, type ModelPermission, type MenuInfo, type UserInfo } from '../lib/api'
import { useGraphApi, type EntraUser, type EntraGroup } from '../hooks/useGraphApi'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card } from '@/components/ui/card'
import { useTranslation } from 'react-i18next'

type SearchType = 'user' | 'entra_group' | 'local_user'

export function UserManagement() {
    const { t } = useTranslation()
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
    const [isEditingGroup, setIsEditingGroup] = useState(false)
    const [editingGroupId, setEditingGroupId] = useState<string | null>(null)

    const [showAddMemberModal, setShowAddMemberModal] = useState(false)
    const [selectedGroup, setSelectedGroup] = useState<GroupInfo | null>(null)
    const [memberSearchType, setMemberSearchType] = useState<SearchType>('local_user')
    const [memberSearchTerm, setMemberSearchTerm] = useState('')
    const [entraSearchResults, setEntraSearchResults] = useState<(EntraUser | EntraGroup | UserInfo)[]>([])
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
            } else if (memberSearchType === 'entra_group') {
                const results = await searchEntraGroups(memberSearchTerm)
                setEntraSearchResults(results)
            } else {
                // Local user search
                try {
                    const res = await usersApi.getAll(memberSearchTerm)
                    setEntraSearchResults(res.data)
                } catch (e) {
                    console.error(e)
                }
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
            if (isEditingGroup && editingGroupId) {
                await groupsApi.update(editingGroupId, groupName, groupDesc)
                toast.success(t('admin.messages.group_update_success'))
            } else {
                await groupsApi.create(groupName, groupDesc, isSuperAdmin)
                toast.success(t('admin.messages.group_created'))
            }
            setShowGroupModal(false)
            setGroupName('')
            setGroupDesc('')
            setIsSuperAdmin(false)
            setIsEditingGroup(false)
            setEditingGroupId(null)
            fetchData()
        } catch {
            toast.error(isEditingGroup ? t('admin.messages.group_update_failed') : t('admin.errors.group_create_failed'))
        } finally {
            setCreatingGroup(false)
        }
    }

    const openCreateModal = () => {
        setIsEditingGroup(false)
        setEditingGroupId(null)
        setGroupName('')
        setGroupDesc('')
        setIsSuperAdmin(false)
        setShowGroupModal(true)
    }

    const openEditModal = (group: GroupInfo) => {
        setIsEditingGroup(true)
        setEditingGroupId(group.id)
        setGroupName(group.name)
        setGroupDesc(group.description)
        setIsSuperAdmin(group.permissions?.superAdmin || false)
        setShowGroupModal(true)
    }

    const handleDeleteGroup = async (groupId: string) => {
        if (!confirm(t('admin.messages.delete_confirm'))) return
        try {
            await groupsApi.deleteGroup(groupId)
            toast.success(t('admin.messages.group_deleted'))
            fetchData()
        } catch {
            toast.error(t('admin.errors.group_delete_failed'))
        }
    }

    const handleAddMember = async (item: EntraUser | EntraGroup | UserInfo) => {
        if (!selectedGroup) return
        setAddingMember(true)
        try {
            // Map item to API expected format
            const type = memberSearchType === 'entra_group' ? 'entra_group' : 'user'
            const id = 'id' in item ? item.id : '' // Both have id

            // Type guard for name/displayName
            let name = ''
            if ('displayName' in item) {
                name = item.displayName || ''
            } else if ('name' in item) {
                name = (item as UserInfo).name || ''
            }

            await groupsApi.addMember(selectedGroup.id, type, id, name)
            toast.success(t('admin.messages.member_added'))
            fetchData()
            setMemberSearchTerm('')
            setEntraSearchResults([])
        } catch {
            toast.error(t('admin.errors.member_add_failed'))
        } finally {
            setAddingMember(false)
        }
    }

    const handleRemoveMember = async (groupId: string, memberId: string) => {
        try {
            await groupsApi.removeMember(groupId, memberId)
            toast.success(t('admin.messages.member_removed'))
            fetchData()
        } catch {
            toast.error(t('admin.errors.member_remove_failed'))
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
            toast.success(t('admin.messages.permissions_saved'))
            setShowPermissionsModal(false)
            fetchData()
        } catch {
            toast.error(t('admin.errors.permission_save_failed'))
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
                        <h2 className="text-xl font-bold text-foreground">{t('admin.user_management.title')}</h2>
                        <p className="text-sm text-muted-foreground">{t('admin.user_management.subtitle')}</p>
                    </div>
                </div>
                <div className="flex gap-2">
                    <Button variant="ghost" size="icon" onClick={fetchData}>
                        <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
                    </Button>
                    <Button onClick={openCreateModal}>
                        <FolderPlus className="w-4 h-4 mr-2" />
                        {t('admin.user_management.create_group')}
                    </Button>
                </div>
            </div>

            {/* Search */}
            <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
                <Input
                    type="text"
                    placeholder={t('admin.user_management.search_placeholder')}
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
                        <h3 className="text-lg font-bold text-foreground mb-2">{t('admin.user_management.no_groups')}</h3>
                        <p className="text-sm text-muted-foreground mb-6 max-w-md mx-auto whitespace-pre-wrap">
                            {t('admin.user_management.no_groups_desc')}
                        </p>
                        <Button onClick={openCreateModal} className="bg-gradient-to-r from-primary to-chart-5">
                            <FolderPlus className="w-5 h-5 mr-2" />
                            {t('admin.user_management.create_first_group')}
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
                                                    {t('admin.user_management.super_admin_badge')}
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
                                                <span className="font-medium">{group.members?.length || 0}</span> {t('admin.user_management.member_count')}
                                            </span>
                                            <span className="text-border">•</span>
                                            <span className="font-medium">{group.permissions?.models?.length || 0}</span> {t('admin.user_management.model_perm')}
                                            <span className="text-border">•</span>
                                            <span className="font-medium">{group.permissions?.menus?.length || 0}</span> {t('admin.user_management.menu_perm')}
                                        </div>
                                    </div>
                                </div>

                                <div className="flex gap-2" onClick={e => e.stopPropagation()}>
                                    <Button variant="secondary" size="sm" onClick={() => openPermissionsModal(group)}>
                                        {t('admin.user_management.permission_settings')}
                                    </Button>
                                    <Button variant="outline" size="sm" onClick={(e) => { e.stopPropagation(); openEditModal(group) }}>
                                        {t('admin.user_management.edit_info')}
                                    </Button>
                                    <Button variant="outline" size="sm" onClick={() => { setSelectedGroup(group); setShowAddMemberModal(true); setMemberSearchTerm(''); setEntraSearchResults([]) }}>
                                        <UserPlus className="w-4 h-4 mr-1" />
                                        {t('admin.user_management.add_member')}
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
                                                {t('admin.user_management.member_list')}
                                            </h4>
                                            {group.members?.length === 0 ? (
                                                <div className="text-center py-6">
                                                    <p className="text-sm text-muted-foreground">{t('admin.user_management.no_members')}</p>
                                                    <button
                                                        onClick={() => { setSelectedGroup(group); setShowAddMemberModal(true); setMemberSearchTerm(''); setEntraSearchResults([]) }}
                                                        className="mt-2 text-xs text-primary hover:text-primary/80"
                                                    >
                                                        {t('admin.user_management.add_member_btn')}
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
                                                                        {(member.displayName || '?').slice(0, 2).toUpperCase()}
                                                                    </div>
                                                                )}
                                                                <div>
                                                                    <div className="text-sm font-medium text-foreground">
                                                                        {member.displayName}
                                                                    </div>
                                                                    <div className="text-xs text-muted-foreground">
                                                                        {member.type === 'entra_group' ? t('admin.user_management.entra_group') : t('admin.user_management.entra_user')}
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
                                                {t('admin.user_management.permission_summary')}
                                            </h4>
                                            {group.permissions?.superAdmin ? (
                                                <div className="p-4 bg-gradient-to-br from-destructive/10 to-chart-5/10 rounded-lg border-2 border-destructive/20">
                                                    <div className="flex items-center gap-2 mb-2">
                                                        <Shield className="w-5 h-5 text-destructive" />
                                                        <span className="font-bold text-destructive">{t('admin.user_management.super_admin_badge')}</span>
                                                    </div>
                                                    <p className="text-sm text-destructive/80">{t('admin.user_management.super_admin_summary')}</p>
                                                </div>
                                            ) : (
                                                <div className="space-y-3">
                                                    {(!group.permissions?.models?.length && !group.permissions?.menus?.length) ? (
                                                        <div className="text-center py-6">
                                                            <p className="text-sm text-muted-foreground">{t('admin.user_management.no_permissions_set')}</p>
                                                            <button
                                                                onClick={() => openPermissionsModal(group)}
                                                                className="mt-2 text-xs text-chart-1 hover:text-chart-1/80"
                                                            >
                                                                {t('admin.user_management.set_permission_btn')}
                                                            </button>
                                                        </div>
                                                    ) : (
                                                        <>
                                                            {group.permissions?.models && group.permissions.models.length > 0 && (
                                                                <div>
                                                                    <div className="text-xs font-semibold text-muted-foreground mb-2">{t('admin.labels.model')} {t('admin.user_management.permission_settings')}</div>
                                                                    <div className="space-y-1.5">
                                                                        {group.permissions.models.map((perm) => (
                                                                            <div key={perm.modelId} className="flex items-center justify-between p-2 bg-muted rounded-lg">
                                                                                <span className="text-sm text-foreground">{perm.modelName}</span>
                                                                                <span className={`inline-flex items-center gap-1 text-xs font-medium px-2.5 py-1 rounded-full ${perm.role === 'Admin'
                                                                                    ? 'bg-primary/10 text-primary'
                                                                                    : 'bg-chart-1/10 text-chart-1'
                                                                                    }`}>
                                                                                    {perm.role === 'Admin' ? `⚡ ${t('admin.users.admin')}` : `👁️ ${t('admin.users.user')}`}
                                                                                </span>
                                                                            </div>
                                                                        ))}
                                                                    </div>
                                                                </div>
                                                            )}
                                                            {group.permissions?.menus && group.permissions.menus.length > 0 && (
                                                                <div>
                                                                    <div className="text-xs font-semibold text-muted-foreground mb-2">{t('admin.user_management.menu_access')}</div>
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
                        <h3 className="text-lg font-bold text-foreground mb-4">{isEditingGroup ? t('admin.user_management.edit_group') : t('admin.user_management.create_group')}</h3>
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-foreground mb-1">{t('admin.user_management.group_name')}</label>
                                <Input type="text" value={groupName} onChange={(e) => setGroupName(e.target.value)} placeholder="마케팅팀" />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-foreground mb-1">{t('admin.user_management.description')}</label>
                                <Input type="text" value={groupDesc} onChange={(e) => setGroupDesc(e.target.value)} placeholder="설명" />
                            </div>
                            <label className="flex items-center gap-2 p-3 bg-destructive/10 rounded-lg cursor-pointer">
                                <input type="checkbox" checked={isSuperAdmin} onChange={(e) => setIsSuperAdmin(e.target.checked)} className="rounded" />
                                <div>
                                    <div className="font-semibold text-destructive">{t('admin.user_management.super_admin')}</div>
                                    <div className="text-xs text-destructive/80">{t('admin.user_management.super_admin_desc')}</div>
                                </div>
                            </label>
                            {isEditingGroup && <p className="text-xs text-muted-foreground">{t('admin.user_management.no_permission_msg')}</p>}
                        </div>
                        <div className="flex justify-end gap-2 mt-6">
                            <Button variant="ghost" onClick={() => setShowGroupModal(false)}>{t('common.actions.cancel')}</Button>
                            <Button onClick={handleCreateGroup} disabled={creatingGroup}>
                                {creatingGroup ? t('common.messages.saving') : (isEditingGroup ? t('common.actions.edit') : t('common.actions.create'))}
                            </Button>
                        </div>
                    </Card>
                </div>
            )}

            {/* Add Member Modal */}
            {showAddMemberModal && selectedGroup && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <Card className="p-6 w-full max-w-lg">
                        <h3 className="text-lg font-bold text-foreground mb-4">"{selectedGroup.name}" {t('admin.user_management.add_member')}</h3>

                        <div className="flex gap-2 mb-4">
                            <Button
                                variant={memberSearchType === 'local_user' ? 'default' : 'outline'}
                                className="flex-1"
                                onClick={() => setMemberSearchType('local_user')}
                            >
                                {t('admin.user_management.local_user')}
                            </Button>
                            <Button
                                variant={memberSearchType === 'user' ? 'default' : 'outline'}
                                className="flex-1"
                                onClick={() => setMemberSearchType('user')}
                            >
                                {t('admin.user_management.entra_user')}
                            </Button>
                            <Button
                                variant={memberSearchType === 'entra_group' ? 'default' : 'outline'}
                                className="flex-1"
                                onClick={() => setMemberSearchType('entra_group')}
                            >
                                {t('admin.user_management.entra_group')}
                            </Button>
                        </div>

                        <div className="relative mb-4">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                            <Input
                                type="text"
                                value={memberSearchTerm}
                                onChange={(e) => setMemberSearchTerm(e.target.value)}
                                placeholder={memberSearchType === 'user' ? t('admin.users.search_user') : t('admin.permissions.search_group')}
                                className="pl-9"
                            />
                        </div>

                        {graphError && <p className="text-sm text-destructive mb-2">{graphError}</p>}

                        <div className="max-h-64 overflow-auto space-y-1">
                            {graphLoading ? (
                                <div className="flex justify-center py-4"><Loader2 className="w-6 h-6 animate-spin text-primary" /></div>
                            ) : entraSearchResults.length === 0 ? (
                                <p className="text-center text-muted-foreground py-4">{memberSearchTerm.length >= 2 ? t('common.messages.no_data') : t('common.placeholders.min_2_chars')}</p>
                            ) : (
                                entraSearchResults.map((item, idx) => (
                                    <div key={item.id || idx} className="flex items-center justify-between p-2 hover:bg-accent rounded-lg">
                                        <div className="flex items-center gap-2">
                                            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white font-bold text-xs ${memberSearchType === 'entra_group' ? 'bg-chart-1' : 'bg-gradient-to-br from-primary to-chart-5'}`}>
                                                {memberSearchType === 'entra_group' ? <Globe className="w-4 h-4" /> :
                                                    (('displayName' in item && item.displayName) || ('name' in item && item.name) || '?').slice(0, 2)}
                                            </div>
                                            <div>
                                                <div className="text-sm font-medium">{'displayName' in item ? item.displayName : (item as UserInfo).name}</div>
                                                <div className="text-xs text-muted-foreground">
                                                    {memberSearchType === 'local_user' ? (item as UserInfo).email :
                                                        memberSearchType === 'user' ? (item as EntraUser).mail :
                                                            (item as EntraGroup).description || 'Entra 보안 그룹'}
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
                            <Button variant="ghost" onClick={() => setShowAddMemberModal(false)}>{t('common.actions.close')}</Button>
                        </div>
                    </Card>
                </div>
            )}

            {/* Permissions Modal */}
            {showPermissionsModal && editingGroupPermissions && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <Card className="p-6 w-full max-w-lg max-h-[80vh] overflow-auto">
                        <h3 className="text-lg font-bold text-foreground mb-4">"{editingGroupPermissions.name}" {t('admin.user_management.permission_settings')}</h3>

                        <label className="flex items-center gap-2 mb-4 p-3 bg-destructive/10 rounded-lg cursor-pointer">
                            <input type="checkbox" checked={permSuperAdmin} onChange={(e) => setPermSuperAdmin(e.target.checked)} className="rounded" />
                            <div>
                                <div className="font-semibold text-destructive">{t('admin.user_management.super_admin')}</div>
                                <div className="text-xs text-destructive/80">{t('admin.user_management.super_admin_desc')}</div>
                            </div>
                        </label>

                        {!permSuperAdmin && (
                            <div>
                                <h4 className="font-medium text-foreground mb-2">{t('admin.user_management.model_access')}</h4>
                                <div className="space-y-2">
                                    {models.length === 0 ? (
                                        <p className="text-sm text-muted-foreground">{t('common.messages.no_data')}</p>
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
                                                        {perm ? (perm.role === 'Admin' ? t('admin.users.admin') : t('admin.users.user')) : t('common.status.none')}
                                                    </Button>
                                                </div>
                                            )
                                        })
                                    )}
                                </div>

                                <h4 className="font-medium text-foreground mb-2 mt-4">{t('admin.user_management.menu_access')}</h4>
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
                                                    {permMenus.includes(menu.id) ? t('admin.user_management.allow') : t('admin.user_management.block')}
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
                                                        {permMenus.includes(subMenu.id) ? t('admin.user_management.allow') : t('admin.user_management.block')}
                                                    </Button>
                                                </div>
                                            ))}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        <div className="flex justify-end gap-2 mt-6">
                            <Button variant="ghost" onClick={() => setShowPermissionsModal(false)}>{t('common.actions.cancel')}</Button>
                            <Button onClick={handleSavePermissions}>{t('common.actions.save')}</Button>
                        </div>
                    </Card>
                </div>
            )}

            {/* Info */}
            <div className="flex items-start gap-3 p-4 bg-chart-1/10 rounded-xl">
                <Building className="w-5 h-5 text-chart-1 mt-0.5" />
                <div>
                    <div className="font-medium text-chart-1">{t('admin.user_management.usage_guide')}</div>
                    <div className="text-sm text-chart-1/80">
                        {t('admin.user_management.usage_step_1')} → {t('admin.user_management.usage_step_2')} → {t('admin.user_management.usage_step_3')}
                    </div>
                </div>
            </div>
        </div>
    )
}
