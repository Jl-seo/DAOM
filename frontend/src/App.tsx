import { useState, lazy, Suspense } from 'react'
import { WelcomeScreen } from './components/WelcomeScreen'
import { Sidebar, type MenuId } from './components/Sidebar'
import { LoginPage } from './components/LoginPage'
import { ProfilePage } from './components/ProfilePage'
import { ModelGallery } from './components/ModelGallery'
import { useAuth } from './auth'
import { Menu, Loader2 } from 'lucide-react'
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "./components/ui/sheet"
import { VisuallyHidden } from '@radix-ui/react-visually-hidden'

// Lazy loaded components for code splitting
const ModelStudio = lazy(() => import('./components/ModelStudio').then(m => ({ default: m.ModelStudio })))
const AdminSettings = lazy(() => import('./components/AdminSettings').then(m => ({ default: m.AdminSettings })))
const ModelView = lazy(() => import('./components/ModelView').then(m => ({ default: m.ModelView })))
const AuditLogViewer = lazy(() => import('./components/AuditLogViewer').then(m => ({ default: m.AuditLogViewer })))
const DashboardStats = lazy(() => import('./components/admin/DashboardStats').then(m => ({ default: m.DashboardStats })))
const UserManagement = lazy(() => import('./components/UserManagement').then(m => ({ default: m.UserManagement })))
const AllExtractionHistory = lazy(() => import('./features/extraction/components/AllExtractionHistory').then(m => ({ default: m.AllExtractionHistory })))
const QuickExtractionView = lazy(() => import('./features/quick/QuickExtractionView').then(m => ({ default: m.QuickExtractionView })))

// Loading fallback component
const PageLoader = () => (
  <div className="flex-1 flex items-center justify-center">
    <Loader2 className="w-8 h-8 animate-spin text-primary" />
  </div>
)

function App() {
  const { isAuthenticated, isLoading } = useAuth()
  const [activeMenu, setActiveMenu] = useState<MenuId>('model-gallery' as MenuId)

  // Mobile Menu State
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)

  // File passed to ModelView (for drag-drop scenarios)
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
          <ModelGallery
            onSelectModel={(modelId) => setActiveMenu(`model-${modelId}` as MenuId)}
            onNavigate={handleNavigate}
          />
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
          onQuickExtraction={() => setActiveMenu('quick-extraction')}
        />
      </div>

      <div className="flex-1 flex flex-col overflow-auto relative">
        <Suspense fallback={<PageLoader />}>
          {renderContent()}
        </Suspense>
      </div>
    </div>
  )
}

export default App
