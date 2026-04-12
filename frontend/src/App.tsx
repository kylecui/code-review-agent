import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Sidebar } from '@/components/layout/sidebar'
import { useLogout } from '@/hooks/use-auth'
import { useCurrentUser } from '@/hooks/use-current-user'
import { LoginPage } from '@/pages/login'

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

  return (
    <div className="flex min-h-screen bg-zinc-100 text-zinc-900">
      <Sidebar
        user={user}
        activePage={activePage}
        onNavigate={setActivePage}
        onLogout={() => logout.mutate()}
      />
      <main className="flex flex-1 items-center justify-center p-8">
        <p className="text-zinc-500">
          {activePage === 'scans' && 'Scan dashboard — coming soon'}
          {activePage === 'settings' && 'Settings — coming soon'}
          {activePage === 'policies' && 'Policy editor — coming soon'}
          {activePage === 'users' && 'User management — coming soon'}
        </p>
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
