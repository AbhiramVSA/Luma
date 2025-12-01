"use client"

import type { ReactNode } from "react"
import { useEffect, useState } from "react"
import Link from "next/link"
import { ShieldAlert } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { getAuthToken } from "@/lib/api"

interface AuthGateProps {
  children: ReactNode
}

export function AuthGate({ children }: AuthGateProps) {
  const [ready, setReady] = useState(false)
  const [isAuthenticated, setIsAuthenticated] = useState(false)

  useEffect(() => {
    const evaluate = () => {
      setIsAuthenticated(Boolean(getAuthToken()))
      setReady(true)
    }

    evaluate()
    window.addEventListener("storage", evaluate)
    return () => window.removeEventListener("storage", evaluate)
  }, [])

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <p className="text-sm text-muted-foreground">Preparing secure workspace...</p>
      </div>
    )
  }

  if (!isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-background via-background to-background/95 p-4">
        <Card className="max-w-md w-full border-border/80 shadow-xl animate-soft-scale">
          <CardHeader className="space-y-3 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
              <ShieldAlert className="h-6 w-6" />
            </div>
            <CardTitle className="text-2xl">Authentication Required</CardTitle>
            <CardDescription>
              Sign in with your InnerBhakti credentials to access the video automation studio.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <Button asChild size="lg" className="w-full">
              <Link href="/login">Go to secure login</Link>
            </Button>
            <p className="text-xs text-muted-foreground text-center">
              Don’t have access? Contact an administrator to receive a workspace invite.
            </p>
          </CardContent>
        </Card>
      </div>
    )
  }

  return <>{children}</>
}
