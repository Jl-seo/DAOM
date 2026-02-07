/* eslint-disable react-hooks/set-state-in-effect */
import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { WelcomeScreen } from './components/WelcomeScreen'
import { Sidebar } from './components/Sidebar'
import { LoginPage } from './components/LoginPage'
import { ErrorBoundary } from './components/ErrorBoundary'
import { NotFoundPage } from './components/NotFoundPage'
import { PageLoader } from './components/PageLoader'
import { RouteProgressBar } from './components/RouteProgressBar'
import { ProfilePage } from './components/ProfilePage'
import { ModelGallery } from './components/ModelGallery'
import { useAuth } from './auth'
import { Menu, Loader2 } from 'lucide-react'
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "./components/ui/sheet"
import { VisuallyHidden } from '@radix-ui/react-visually-hidden'
import { useState, useCallback, useEffect } from 'react'

// Lazy loaded components for code splitting
const ModelStudio = lazy(() => import('./components/ModelStudio').then(m => ({ default: m.ModelStudio })))
const AdminSettings = lazy(() => import('./components/AdminSettings').then(m => ({ default: m.AdminSettings })))
const ModelView = lazy(() => import('./components/ModelView').then(m => ({ default: m.ModelView })))
const AuditLogViewer = lazy(() => import('./components/AuditLogViewer').then(m => ({ default: m.AuditLogViewer })))
const DashboardStats = lazy(() => import('./components/admin/DashboardStats').then(m => ({ default: m.DashboardStats })))
const UserManagement = lazy(() => import('./components/UserManagement').then(m => ({ default: m.UserManagement })))
const AllExtractionHistory = lazy(() => import('./features/extraction/components/AllExtractionHistory').then(m => ({ default: m.AllExtractionHistory })))
const QuickExtractionView = lazy(() => import('./features/quick/QuickExtractionView').then(m => ({ default: m.QuickExtractionView })))

// Detail routes that should auto-collapse the sidebar
const DETAIL_ROUTE_PATTERNS = [
  /^\/models\/[^/]+\/extractions\/[^/]+/,  // /models/:modelId/extractions/:logId
  /^\/extractions\/[^/]+/,                  // /extractions/:jobId
]

// Layout wrapper for authenticated pages
function AppLayout({ children }: { children: React.ReactNode }) {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false)
  const toggleSidebar = useCallback(() => setIsSidebarCollapsed(prev => !prev), [])
  const location = useLocation()

  // Auto-collapse sidebar on detail routes, auto-expand on others
  useEffect(() => {
    const isDetailRoute = DETAIL_ROUTE_PATTERNS.some(pattern => pattern.test(location.pathname))
    setIsSidebarCollapsed(isDetailRoute)
  }, [location.pathname])

  return (
    <div className="h-screen flex flex-col md:flex-row bg-background overflow-hidden">
      <RouteProgressBar />
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
              className="w-full border-none shadow-none"
              onClose={() => setIsMobileMenuOpen(false)}
            />
          </SheetContent>
        </Sheet>
      </div>

      {/* Desktop Sidebar */}
      <div className={`hidden md:flex flex-shrink-0 transition-all duration-200 ${isSidebarCollapsed ? 'w-16' : 'w-64'}`}>
        <Sidebar collapsed={isSidebarCollapsed} onToggleCollapse={toggleSidebar} />
      </div>

      <div className="flex-1 flex flex-col overflow-auto relative">
        <Suspense fallback={<PageLoader />}>
          {children}
        </Suspense>
      </div>
    </div>
  )
}

function App() {
  const { isAuthenticated, isLoading } = useAuth()

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

  return (
    <ErrorBoundary>
      <Routes>
        {/* Root redirect to model gallery */}
        <Route path="/" element={<Navigate to="/models" replace />} />

        {/* Welcome screen */}
        <Route path="/welcome" element={
          <AppLayout>
            <WelcomeScreen />
          </AppLayout>
        } />

        {/* Quick Extraction */}
        <Route path="/quick-extraction" element={
          <AppLayout>
            <QuickExtractionView />
          </AppLayout>
        } />

        {/* Model Gallery (Home) */}
        <Route path="/models" element={
          <AppLayout>
            <ModelGallery />
          </AppLayout>
        } />

        {/* Individual Model View */}
        <Route path="/models/:modelId" element={
          <AppLayout>
            <ModelView />
          </AppLayout>
        } />

        {/* Deep-link to specific extraction record within a model */}
        <Route path="/models/:modelId/extractions/:logId" element={
          <AppLayout>
            <ModelView />
          </AppLayout>
        } />

        {/* Extraction History */}
        <Route path="/history" element={
          <AppLayout>
            <AllExtractionHistory />
          </AppLayout>
        } />

        {/* Individual Extraction Detail */}
        <Route path="/extractions/:jobId" element={
          <AppLayout>
            <ModelView />
          </AppLayout>
        } />

        {/* Profile */}
        <Route path="/profile" element={
          <AppLayout>
            <div className="flex-1 p-4 md:p-8 overflow-auto">
              <ProfilePage />
            </div>
          </AppLayout>
        } />

        {/* Admin Routes */}
        <Route path="/admin/dashboard" element={
          <AppLayout>
            <div className="flex-1 p-4 md:p-8 overflow-auto">
              <h2 className="text-2xl font-bold mb-6">대시보드</h2>
              <DashboardStats />
            </div>
          </AppLayout>
        } />

        <Route path="/admin/audit" element={
          <AppLayout>
            <div className="flex-1 p-4 md:p-8 overflow-auto">
              <AuditLogViewer />
            </div>
          </AppLayout>
        } />

        <Route path="/admin/model-studio" element={
          <AppLayout>
            <div className="flex-1 p-4 md:p-8 overflow-auto">
              <ModelStudio />
            </div>
          </AppLayout>
        } />

        <Route path="/admin/users" element={
          <AppLayout>
            <div className="flex-1 p-4 md:p-8 overflow-auto">
              <UserManagement />
            </div>
          </AppLayout>
        } />

        <Route path="/admin/settings" element={
          <AppLayout>
            <div className="flex-1 p-4 md:p-8 overflow-auto">
              <AdminSettings />
            </div>
          </AppLayout>
        } />

        {/* 404 Not Found - Must be last */}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </ErrorBoundary>
  )
}

export default App
