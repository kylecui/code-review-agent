import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useLogin } from '@/hooks/use-auth'
import { cn } from '@/lib/utils'
import { buttonVariants } from '@/components/ui/button'

export function LoginPage() {
  const login = useLogin()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const isSubmitting = login.isPending

  const handleSubmit: NonNullable<React.ComponentProps<'form'>['onSubmit']> = (event) => {
    event.preventDefault()
    setErrorMessage(null)

    login.mutate(
      { email, password },
      {
        onError: (error) => {
          if (error instanceof Error && error.message) {
            setErrorMessage(error.message)
            return
          }

          setErrorMessage('Login failed. Please try again.')
        },
      },
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-100 p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-center text-2xl">Agent Review</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </div>

            {errorMessage ? <p className="text-sm text-red-600">{errorMessage}</p> : null}

            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? 'Signing In...' : 'Sign In'}
            </Button>

            <div className="flex items-center gap-3 py-1">
              <div className="h-px flex-1 bg-zinc-200" />
              <span className="text-xs uppercase tracking-wide text-zinc-500">or</span>
              <div className="h-px flex-1 bg-zinc-200" />
            </div>

            <a
              href="/api/auth/github/login"
              className={cn(buttonVariants({ variant: 'outline' }), 'w-full')}
            >
              Sign in with GitHub
            </a>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
