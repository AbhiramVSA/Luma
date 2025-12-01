"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { LogIn, LogOut } from "lucide-react"

import { Button } from "@/components/ui/button"
import { clearAuthToken, getAuthToken } from "@/lib/api"

export function AuthStatus() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [ready, setReady] = useState(false)
  const router = useRouter()

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
      <span className="text-xs font-mono text-muted-foreground" aria-live="polite">
        Checking auth...
      </span>
    )
  }

  if (!isAuthenticated) {
    return (
      <Button variant="outline" size="sm" asChild>
        <Link href="/login" className="flex items-center gap-2">
          <LogIn className="h-3.5 w-3.5" />
          Sign in
        </Link>
      </Button>
    )
  }

  return (
    <Button
      variant="secondary"
      size="sm"
      className="flex items-center gap-2"
      onClick={() => {
        clearAuthToken()
        setIsAuthenticated(false)
        router.refresh()
      }}
    >
      <LogOut className="h-3.5 w-3.5" />
      Sign out
    </Button>
  )
}
