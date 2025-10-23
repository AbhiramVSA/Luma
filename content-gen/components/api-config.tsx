"use client"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { AlertCircle, CheckCircle2 } from "lucide-react"
import { useState, useEffect } from "react"

export function ApiConfig() {
  const [apiStatus, setApiStatus] = useState<"checking" | "connected" | "disconnected">("checking")

  useEffect(() => {
    const checkApiStatus = async () => {
      try {
        const response = await fetch("http://127.0.0.1:8002/api/v1/health", {
          method: "GET",
        })
        setApiStatus(response.ok ? "connected" : "disconnected")
      } catch (err) {
        setApiStatus("disconnected")
      }
    }

    checkApiStatus()
  const interval = setInterval(checkApiStatus, 600000) // Check every 10 minutes

    return () => clearInterval(interval)
  }, [])

  return (
    <Card className="bg-muted/50">
      <CardHeader>
        <CardTitle className="text-sm">API Configuration</CardTitle>
        <CardDescription>Backend connection status</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground">Base URL</p>
          <p className="font-mono text-xs break-all">http://127.0.0.1:8002/api/v1</p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground">Status:</span>
          {apiStatus === "connected" && (
            <Badge className="bg-green-500/10 text-green-600 border-green-500/50">
              <CheckCircle2 className="h-3 w-3 mr-1" />
              Connected
            </Badge>
          )}
          {apiStatus === "disconnected" && (
            <Badge variant="destructive">
              <AlertCircle className="h-3 w-3 mr-1" />
              Disconnected
            </Badge>
          )}
          {apiStatus === "checking" && <Badge variant="outline">Checking...</Badge>}
        </div>

        {apiStatus === "disconnected" && (
          <Alert variant="destructive" className="mt-3">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription className="text-xs">
              Backend API is not responding. Make sure the server is running at http://127.0.0.1:8002
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}
