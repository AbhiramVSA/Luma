"use client"
import { useState, useEffect, useMemo, useDeferredValue, useCallback } from "react"
import Image from "next/image"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Checkbox } from "@/components/ui/checkbox"
import { Progress } from "@/components/ui/progress"
import { Loader2, AlertCircle, CheckCircle2, Play, RefreshCw, Download, Trash2 } from "lucide-react"

const VIDEO_STORAGE_KEY = "ib-video-generation-state"

interface VideoResult {
  scene_id: string
  status: string
  video_id: string
  video_url: string
  thumbnail_url: string
  message: string
}

interface VideoResponse {
  status: string
  results: VideoResult[]
  missing_assets: string[]
  errors: string[]
}

export default function VideoGeneration() {
  const [script, setScript] = useState("")
  const [forceUpload, setForceUpload] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [success, setSuccess] = useState(false)
  const [videoResults, setVideoResults] = useState<VideoResult[]>([])
  const [overallStatus, setOverallStatus] = useState("")
  const [missingAssets, setMissingAssets] = useState<string[]>([])
  const [errors, setErrors] = useState<string[]>([])
  const [autoRefresh, setAutoRefresh] = useState(false)
  const deferredResults = useDeferredValue(videoResults)
  const hasResults = deferredResults.length > 0
  const progressSummary = useMemo(() => {
    const completed = deferredResults.filter((r) => r.status === "completed").length
    const processing = deferredResults.filter((r) => r.status === "processing" || r.status === "submitted").length
    const failed = deferredResults.filter((r) => r.status === "failed").length
    return { completed, processing, failed }
  }, [deferredResults])

  useEffect(() => {
    if (typeof window === "undefined") return

    try {
      const stored = window.localStorage.getItem(VIDEO_STORAGE_KEY)
      if (!stored) return

      const parsed = JSON.parse(stored)
      if (Array.isArray(parsed?.videoResults) && parsed.videoResults.length > 0) {
        setVideoResults(parsed.videoResults)
        setOverallStatus(typeof parsed.overallStatus === "string" ? parsed.overallStatus : "")
        setMissingAssets(Array.isArray(parsed.missingAssets) ? parsed.missingAssets : [])
        setErrors(Array.isArray(parsed.errors) ? parsed.errors : [])
        setSuccess(true)
      }
    } catch (err) {
      console.warn("Failed to restore video generation state", err)
    }
  }, [])

  useEffect(() => {
    if (typeof window === "undefined") return

    if (videoResults.length === 0) {
      window.localStorage.removeItem(VIDEO_STORAGE_KEY)
      return
    }

    const payload = {
      videoResults,
      overallStatus,
      missingAssets,
      errors,
    }

    window.localStorage.setItem(VIDEO_STORAGE_KEY, JSON.stringify(payload))
  }, [videoResults, overallStatus, missingAssets, errors])

  const handleGenerateVideo = useCallback(async () => {
    if (!script.trim()) {
      setError("Please enter a script")
      return
    }

    setLoading(true)
    setError("")
    setSuccess(false)

    try {
      const response = await fetch("http://127.0.0.1:8002/api/v1/heygen/generate-video", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          script,
          force_upload: forceUpload,
        }),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || "Failed to generate video")
      }

      const data: VideoResponse = await response.json()
      setVideoResults(data.results)
      setOverallStatus(data.status)
      setMissingAssets(data.missing_assets)
      setErrors(data.errors)
      setSuccess(true)

      const hasProcessing = data.results.some((r) => r.status === "processing" || r.status === "submitted")
      if (hasProcessing) {
        setAutoRefresh(true)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred")
    } finally {
      setLoading(false)
    }
  }, [forceUpload, script])

  const handleRefreshStatus = useCallback(async () => {
    if (videoResults.length === 0) return

    try {
      const response = await fetch("http://127.0.0.1:8002/api/v1/heygen/generate-video", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          script,
          force_upload: false,
        }),
      })

      if (!response.ok) return

      const data: VideoResponse = await response.json()
      setVideoResults(data.results)
      setOverallStatus(data.status)

      const hasProcessing = data.results.some((r) => r.status === "processing" || r.status === "submitted")
      if (!hasProcessing) {
        setAutoRefresh(false)
      }
    } catch (err) {
      console.error("Failed to refresh status:", err)
    }
  }, [script, videoResults.length])

  useEffect(() => {
    if (!autoRefresh || videoResults.length === 0) return

    const hasProcessing = videoResults.some((r) => r.status === "processing" || r.status === "submitted")
    if (!hasProcessing) {
      setAutoRefresh(false)
      return
    }

    const interval = setInterval(() => {
      handleRefreshStatus()
    }, 5000)

    return () => clearInterval(interval)
  }, [autoRefresh, videoResults, handleRefreshStatus])

  const handleClearResults = useCallback(() => {
    setVideoResults([])
    setOverallStatus("")
    setMissingAssets([])
    setErrors([])
    setSuccess(false)
    setError("")
    setAutoRefresh(false)
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(VIDEO_STORAGE_KEY)
    }
  }, [])

  const getStatusColor = (status: string) => {
    switch (status) {
      case "completed":
        return "bg-green-500/10 text-green-600 border-green-500/50"
      case "processing":
        return "bg-blue-500/10 text-blue-600 border-blue-500/50"
      case "submitted":
        return "bg-yellow-500/10 text-yellow-600 border-yellow-500/50"
      case "failed":
        return "bg-red-500/10 text-red-600 border-red-500/50"
      default:
        return "bg-gray-500/10 text-gray-600 border-gray-500/50"
    }
  }

  const { completed: completedCount, processing: processingCount, failed: failedCount } = progressSummary

  return (
    <div className="space-y-6">
      {/* Input Section */}
      <Card>
        <CardHeader>
          <CardTitle>Generate Talking-Head Videos</CardTitle>
          <CardDescription>Create AI-powered talking-head videos from your script using HeyGen</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Script</label>
            <Textarea
              placeholder="Enter your scene-based script here. Make sure audio has been generated first."
              value={script}
              onChange={(e) => setScript(e.target.value)}
              rows={16}
              className="font-mono text-sm min-h-[320px]"
            />
          </div>

          <div className="flex items-center space-x-2">
            <Checkbox
              id="force-upload"
              checked={forceUpload}
              onCheckedChange={(checked) => setForceUpload(checked as boolean)}
            />
            <label htmlFor="force-upload" className="text-sm font-medium cursor-pointer">
              Force re-upload audio assets
            </label>
          </div>

          <Button onClick={handleGenerateVideo} disabled={loading || !script.trim()} className="w-full" size="lg">
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Generating Videos...
              </>
            ) : (
              <>
                <Play className="mr-2 h-4 w-4" />
                Generate Videos
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      {/* Error Alert */}
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Success Alert */}
      {success && (
        <Alert className="border-green-500/50 bg-green-500/10 animate-fade-in-up">
          <CheckCircle2 className="h-4 w-4 text-green-600" />
          <AlertDescription className="text-green-600">
            Video generation {overallStatus}! {deferredResults.length} scene(s) processed.
          </AlertDescription>
        </Alert>
      )}

      {/* Results Section */}
      {hasResults && (
        <div className="space-y-4 animate-fade-in-up">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold">Video Results</h3>
            <div className="flex items-center gap-2">
              <Badge variant={overallStatus === "success" ? "default" : "secondary"}>{overallStatus}</Badge>
              <Button
                onClick={handleRefreshStatus}
                disabled={processingCount === 0}
                variant="outline"
                size="sm"
                className="h-8 bg-transparent hover-lift"
              >
                <RefreshCw className="h-4 w-4" />
              </Button>
              <Button
                onClick={handleClearResults}
                variant="destructive"
                size="sm"
                className="h-8 hover-lift"
                disabled={loading}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* Progress Summary */}
          {hasResults && (
            <Card className="bg-muted/50 hover-lift animate-fade-in-up">
              <CardContent className="pt-6">
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-sm">
                    <span>Progress</span>
                    <span className="font-mono">
                      {completedCount}/{deferredResults.length}
                    </span>
                  </div>
                  <Progress value={(completedCount / deferredResults.length) * 100} className="h-2" />
                  <div className="grid grid-cols-3 gap-2 text-xs">
                    <div className="flex items-center gap-1">
                      <div className="h-2 w-2 rounded-full bg-green-500" />
                      <span>{completedCount} completed</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <div className="h-2 w-2 rounded-full bg-blue-500" />
                      <span>{processingCount} processing</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <div className="h-2 w-2 rounded-full bg-red-500" />
                      <span>{failedCount} failed</span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          <div className="grid gap-4 md:grid-cols-2">
            {deferredResults.map((result, index) => (
              <Card
                key={`${result.scene_id}-${result.video_id}`}
                className="hover-lift animate-fade-in-up"
                style={{ animationDelay: `${index * 50}ms` }}
              >
                <CardContent className="pt-6 space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-sm font-medium">{result.scene_id}</span>
                    <Badge className={getStatusColor(result.status)}>{result.status}</Badge>
                  </div>

                  {result.thumbnail_url && (
                    <div className="relative h-32 w-full overflow-hidden rounded-lg">
                      <Image
                        src={result.thumbnail_url || "/placeholder.svg"}
                        alt={`${result.scene_id} thumbnail`}
                        fill
                        sizes="(min-width: 768px) 50vw, 100vw"
                        className="object-cover"
                      />
                    </div>
                  )}

                  {result.video_url && result.status === "completed" && (
                    <div className="space-y-2">
                      <video src={result.video_url} controls className="w-full rounded-lg bg-black" />
                      <a
                        href={result.video_url}
                        download
                        className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline"
                      >
                        <Download className="h-4 w-4" />
                        Download Video
                      </a>
                    </div>
                  )}

                  {result.message && <p className="text-xs text-muted-foreground">{result.message}</p>}
                </CardContent>
              </Card>
            ))}
          </div>

          {missingAssets.length > 0 && (
            <Alert variant="destructive" className="animate-fade-in-up">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                <p className="font-medium mb-2">Missing Assets:</p>
                <ul className="list-disc list-inside space-y-1">
                  {missingAssets.map((asset, idx) => (
                    <li key={idx} className="text-sm">
                      {asset}
                    </li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          )}

          {errors.length > 0 && (
            <Alert variant="destructive" className="animate-fade-in-up">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                <p className="font-medium mb-2">Errors:</p>
                <ul className="list-disc list-inside space-y-1">
                  {errors.map((err, idx) => (
                    <li key={idx} className="text-sm">
                      {err}
                    </li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          )}
        </div>
      )}
    </div>
  )
}
