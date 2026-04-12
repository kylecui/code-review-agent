import type { ReactNode } from 'react'

import { useCurrentUser } from '@/hooks/use-current-user'

interface AuthGuardProps {
  children: ReactNode
}

export function AuthGuard({ children }: AuthGuardProps) {
  const { data: user, isLoading } = useCurrentUser()

  if (isLoading) {
    return <div className="flex min-h-screen items-center justify-center">Loading...</div>
  }

  if (!user) {
    return null
  }

  return <>{children}</>
}
