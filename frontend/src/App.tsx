import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { Sidebar } from '@/components/layout/sidebar'
import { useLogout } from '@/hooks/use-auth'
import { useCurrentUser } from '@/hooks/use-current-user'
import { LoginPage } from '@/pages/login'
import { ScanDetailPage } from '@/pages/scan-detail'
import { ScansPage } from '@/pages/scans'
import { SettingsPage } from '@/pages/settings'
import { PoliciesPage } from '@/pages/policies'
import { PolicyEditorPage } from '@/pages/policy-editor'
import { UsersPage } from '@/pages/users'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

function AuthenticatedApp() {
  const { data: user, isLoading } = useCurrentUser()
  const logout = useLogout()
  const [activePage, setActivePage] = useState('scans')
  const [selectedScanId, setSelectedScanId] = useState<string | null>(null)
  const [selectedPolicyName, setSelectedPolicyName] = useState<string | null>(null)

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-100">
        <p className="text-zinc-500">Loading...</p>
      </div>
    )
  }

  if (!user) {
    return <LoginPage />
  }

  const handleNavigate = (page: string) => {
    setActivePage(page)
    setSelectedScanId(null)
    setSelectedPolicyName(null)
  }

  const renderPage = () => {
    switch (activePage) {
      case 'scans':
        return (
          <ScansPage
            isSuperuser={user.is_superuser}
            onSelectScan={(id) => {
              setSelectedScanId(id)
              setActivePage('scan-detail')
            }}
          />
        )
      case 'scan-detail':
        return selectedScanId ? (
          <ScanDetailPage
            scanId={selectedScanId}
            isSuperuser={user.is_superuser}
            onBack={() => setActivePage('scans')}
          />
        ) : (
          <ScansPage
            isSuperuser={user.is_superuser}
            onSelectScan={(id) => {
              setSelectedScanId(id)
              setActivePage('scan-detail')
            }}
          />
        )
      case 'settings':
        return <SettingsPage />
      case 'policies':
        return (
          <PoliciesPage
            onEditPolicy={(name) => {
              setSelectedPolicyName(name)
              setActivePage('policy-editor')
            }}
          />
        )
      case 'policy-editor':
        return selectedPolicyName ? (
          <PolicyEditorPage
            policyName={selectedPolicyName}
            onBack={() => setActivePage('policies')}
          />
        ) : (
          <PoliciesPage
            onEditPolicy={(name) => {
              setSelectedPolicyName(name)
              setActivePage('policy-editor')
            }}
          />
        )
      case 'users':
        return <UsersPage currentUserId={user.id} />
      default:
        return null
    }
  }

  return (
    <div className="flex min-h-screen bg-zinc-100 text-zinc-900">
      <Sidebar
        user={user}
        activePage={activePage}
        onNavigate={handleNavigate}
        onLogout={() => logout.mutate()}
      />
      <main className="flex-1 overflow-auto p-8">
        {renderPage()}
      </main>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthenticatedApp />
    </QueryClientProvider>
  )
}
