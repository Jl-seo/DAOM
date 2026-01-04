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
import { Menu } from 'lucide-react'
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "./components/ui/sheet"
import { VisuallyHidden } from '@radix-ui/react-visually-hidden'
import { QuickExtractionView } from './features/quick/QuickExtractionView'

function App() {
  const { isAuthenticated, isLoading } = useAuth()
  const [activeMenu, setActiveMenu] = useState<MenuId>('home' as MenuId)

  // Mobile Menu State
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)

  // Quick Extraction State (Legacy modal state retained if needed, but we use View now)
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
    setIsMobileMenuOpen(false) // Close mobile menu if open
  }

  const handleQuickExtractionStart = (modelId: string, file: File) => {
    setQuickStartFile(file)
    setActiveMenu(`model-${modelId}` as MenuId)
  }

  const renderContent = () => {
    switch (activeMenu) {
      case 'home':
        return <WelcomeScreen onGetStarted={handleGetStarted} onNavigate={handleNavigate} />

      case 'quick-extraction':
        return <QuickExtractionView />

      case 'model-studio':
        return (
          <div className="flex-1 p-4 md:p-8 overflow-auto">
            <ModelStudio />
          </div>
        )

      case 'admin-dashboard':
        return (
          <div className="flex-1 p-4 md:p-8 overflow-auto">
            <h2 className="text-2xl font-bold mb-6">대시보드</h2>
            <DashboardStats />
          </div>
        )

      case 'admin-audit':
        return (
          <div className="flex-1 p-4 md:p-8 overflow-auto">
            <AuditLogViewer />
          </div>
        )

      case 'settings-general':
        return (
          <div className="flex-1 p-4 md:p-8 overflow-auto">
            <AdminSettings />
          </div>
        )


      case 'profile' as MenuId:
        return (
          <div className="flex-1 p-4 md:p-8 overflow-auto">
            <ProfilePage />
          </div>
        )

      case 'settings-users':
        return (
          <div className="flex-1 p-4 md:p-8 overflow-auto">
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
    <div className="h-screen flex flex-col md:flex-row bg-background overflow-hidden">

      {/* Mobile Header */}
      <div className="md:hidden h-14 border-b flex items-center px-4 justify-between bg-sidebar text-sidebar-foreground">
        <div className="flex items-center gap-2">
          <span className="font-bold text-lg">DAOM</span>
        </div>

        <Sheet open={isMobileMenuOpen} onOpenChange={setIsMobileMenuOpen}>
          <SheetTrigger asChild>
            <button className="p-2 -mr-2">
              <Menu className="w-6 h-6" />
            </button>
          </SheetTrigger>
          <SheetContent side="left" className="p-0 border-r-0 w-[80%] max-w-[300px] bg-sidebar text-sidebar-foreground">
            <VisuallyHidden><SheetTitle>Navigation Menu</SheetTitle></VisuallyHidden>
            <Sidebar
              activeMenu={activeMenu}
              onMenuChange={handleNavigate}
              className="w-full border-none shadow-none"
              onClose={() => setIsMobileMenuOpen(false)}
            />
          </SheetContent>
        </Sheet>
      </div>

      {/* Desktop Sidebar */}
      <div className="hidden md:flex flex-shrink-0">
        <Sidebar
          activeMenu={activeMenu}
          onMenuChange={setActiveMenu}
          onQuickExtraction={() => setIsQuickExtractionOpen(true)}
        />
      </div>

      <div className="flex-1 flex flex-col overflow-hidden relative">
        {renderContent()}
      </div>

      {/* Legacy Modal (Optional, can be removed if we fully switch to View) */}
      <QuickExtractionModal
        isOpen={isQuickExtractionOpen}
        onClose={() => setIsQuickExtractionOpen(false)}
        onStartExtraction={handleQuickExtractionStart}
      />
    </div>
  )
}

export default App
