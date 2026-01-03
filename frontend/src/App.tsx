import { useState } from 'react'
import { ModelStudio } from './components/ModelStudio'
import { AdminSettings } from './components/AdminSettings'
import { ModelView } from './components/ModelView'
import { WelcomeScreen } from './components/WelcomeScreen'
import { Sidebar, type MenuId } from './components/Sidebar'
import { LoginPage } from './components/LoginPage'
import { AuditLogViewer } from './components/AuditLogViewer'
import { DashboardStats } from './components/admin/DashboardStats'
import { ProfilePage } from './components/ProfilePage'
import { UserManagement } from './components/UserManagement'
import { ModelGallery } from './components/ModelGallery'
import { AllExtractionHistory } from './features/extraction/components/AllExtractionHistory'
import { QuickExtractionModal } from './components/QuickExtractionModal'
import { useAuth } from './auth'
import { Loader2 } from 'lucide-react'

function App() {
  const { isAuthenticated, isLoading } = useAuth()
  const [activeMenu, setActiveMenu] = useState<MenuId>('home' as MenuId)

  // Quick Extraction State
  const [isQuickExtractionOpen, setIsQuickExtractionOpen] = useState(false)
  const [quickStartFile, setQuickStartFile] = useState<File | null>(null)

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return <LoginPage />
  }

  const handleGetStarted = () => {
    setActiveMenu('model-studio')
  }

  const handleNavigate = (menuId: string) => {
    setActiveMenu(menuId as MenuId)
  }

  const handleQuickExtractionStart = (modelId: string, file: File) => {
    setQuickStartFile(file)
    setActiveMenu(`model-${modelId}` as MenuId)
  }

  const renderContent = () => {
    switch (activeMenu) {
      case 'home':
        return <WelcomeScreen onGetStarted={handleGetStarted} onNavigate={handleNavigate} />

      case 'model-studio':
        return (
          <div className="flex-1 p-8 overflow-auto">
            <ModelStudio />
          </div>
        )

      case 'admin-dashboard':
        return (
          <div className="flex-1 p-8 overflow-auto">
            <h2 className="text-2xl font-bold mb-6">대시보드</h2>
            <DashboardStats />
          </div>
        )

      case 'admin-audit':
        return (
          <div className="flex-1 p-8 overflow-auto">
            <AuditLogViewer />
          </div>
        )

      case 'settings-general':
        return (
          <div className="flex-1 p-8 overflow-auto">
            <AdminSettings />
          </div>
        )


      case 'profile' as MenuId:
        return (
          <div className="flex-1 p-8 overflow-auto">
            <ProfilePage />
          </div>
        )

      case 'settings-users':
        return (
          <div className="flex-1 p-8 overflow-auto">
            <UserManagement />
          </div>
        )

      case 'model-gallery':
        return (
          <ModelGallery onSelectModel={(modelId) => setActiveMenu(`model-${modelId}` as MenuId)} />
        )

      case 'extraction-history':
        return <AllExtractionHistory onNavigate={handleNavigate} />
    }

    if (activeMenu.startsWith('model-')) {
      const modelId = activeMenu.replace('model-', '')
      // Pass quickStartFile if relevant (will be null otherwise)
      // Note: We might want to clear it after consuming?
      // ModelView should handle that or we can clear here after render?
      // For now passing as prop.
      return <ModelView
        key={modelId} // Remount on model change
        modelId={modelId}
        initialFile={quickStartFile}
        onFileConsumed={() => setQuickStartFile(null)} // Callback to clear
      />
    }

    return <WelcomeScreen onGetStarted={handleGetStarted} onNavigate={handleNavigate} />
  }

  return (
    <div className="h-screen flex bg-background overflow-hidden">
      <Sidebar
        activeMenu={activeMenu}
        onMenuChange={setActiveMenu}
        onQuickExtraction={() => setIsQuickExtractionOpen(true)}
      />

      <div className="flex-1 flex flex-col overflow-hidden">
        {renderContent()}
      </div>

      <QuickExtractionModal
        isOpen={isQuickExtractionOpen}
        onClose={() => setIsQuickExtractionOpen(false)}
        onStartExtraction={handleQuickExtractionStart}
      />
    </div>
  )
}

export default App
