"use client"
import { useState, useRef, useEffect, useCallback } from "react"
import type React from "react"

import Image from "next/image"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Slider } from "@/components/ui/slider"
import { Loader2, AlertCircle, CheckCircle2, Upload, Download, RefreshCw, ImageIcon } from "lucide-react"

interface FreepikPromptBundle {
  prompt: string
  negative_prompt?: string | null
  cfg_scale: number
  duration: "5" | "10"
}

interface ImageToVideoResponse {
  data: {
    task_id: string
    status: string
    generated: string[]
  }
  prompts: FreepikPromptBundle
}

export default function ImageToVideo() {
  const [image, setImage] = useState<string | null>(null)
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [duration, setDuration] = useState("5")
  const [script, setScript] = useState("")
  const [cfgScale, setCfgScale] = useState(0.5)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [success, setSuccess] = useState(false)
  const [taskId, setTaskId] = useState("")
  const [taskStatus, setTaskStatus] = useState("")
  const [generatedVideos, setGeneratedVideos] = useState<string[]>([])
  const [polling, setPolling] = useState(false)
  const [autoPolling, setAutoPolling] = useState(false)
  const [elapsedTime, setElapsedTime] = useState(0)
  const [agentPrompts, setAgentPrompts] = useState<FreepikPromptBundle | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleCheckStatus = useCallback(async () => {
    if (!taskId) return

    setPolling(true)
    setError("")

    try {
      const response = await fetch(
        `http://127.0.0.1:8002/api/v1/freepik/image-to-video/kling-v2-1/${taskId}?wait_for_completion=false`,
        {
          method: "GET",
        },
      )

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || "Failed to check status")
      }

      const data: ImageToVideoResponse = await response.json()
      setTaskStatus(data.data.status)
      setGeneratedVideos(data.data.generated)
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred")
    } finally {
      setPolling(false)
    }
  }, [taskId])

  // Auto-polling effect
  useEffect(() => {
    if (!autoPolling || !taskId) return

    const interval = setInterval(() => {
      setElapsedTime((prev) => prev + 1)
      handleCheckStatus()
    }, 5000)

    return () => clearInterval(interval)
  }, [autoPolling, taskId, handleCheckStatus])

  // Stop polling when completed
  useEffect(() => {
    if (taskStatus === "COMPLETED" || taskStatus === "FAILED") {
      setAutoPolling(false)
    }
  }, [taskStatus])

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Validate file type
    if (!["image/jpeg", "image/png"].includes(file.type)) {
      setError("Please upload a JPG or PNG image")
      return
    }

    // Validate file size (10MB)
    if (file.size > 10 * 1024 * 1024) {
      setError("Image must be smaller than 10MB")
      return
    }

    setImageFile(file)
    setError("")

    // Convert to base64
    const reader = new FileReader()
    reader.onload = (event) => {
      setImage(event.target?.result as string)
    }
    reader.readAsDataURL(file)
  }

  const handleGenerateVideo = async () => {
    if (!image) {
      setError("Please upload an image")
      return
    }

    if (script.trim().length < 10) {
      setError("Script must be at least 10 characters long")
      return
    }

    setLoading(true)
    setError("")
    setSuccess(false)
    setElapsedTime(0)
    setAgentPrompts(null)

    try {
      const response = await fetch("http://127.0.0.1:8002/api/v1/freepik/image-to-video/kling-v2-1-std", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          duration,
          image,
          script,
          cfg_scale: cfgScale,
        }),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || "Failed to create video task")
      }

      const data: ImageToVideoResponse = await response.json()
      setTaskId(data.data.task_id)
      setTaskStatus(data.data.status)
      setAgentPrompts(data.prompts)
      setCfgScale(data.prompts.cfg_scale)
      setSuccess(true)
      setAutoPolling(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred")
    } finally {
      setLoading(false)
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case "COMPLETED":
        return "bg-green-500/10 text-green-600 border-green-500/50"
      case "IN_PROGRESS":
        return "bg-blue-500/10 text-blue-600 border-blue-500/50"
      case "CREATED":
        return "bg-yellow-500/10 text-yellow-600 border-yellow-500/50"
      case "FAILED":
        return "bg-red-500/10 text-red-600 border-red-500/50"
      default:
        return "bg-gray-500/10 text-gray-600 border-gray-500/50"
    }
  }

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}:${secs.toString().padStart(2, "0")}`
  }

  return (
    <div className="space-y-6">
      {/* Input Section */}
      <Card>
        <CardHeader>
          <CardTitle>Image-to-Video Generation</CardTitle>
          <CardDescription>Generate videos from images using Freepik Kling AI</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Image Upload */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Upload Image</label>
            <div
              className="border-2 border-dashed border-border rounded-lg p-8 text-center cursor-pointer hover:border-primary/50 transition-colors"
              onClick={() => fileInputRef.current?.click()}
            >
              {image ? (
                <div className="space-y-2">
                  <div className="relative mx-auto h-48 w-full max-w-sm">
                    <Image
                      src={image || "/placeholder.svg"}
                      alt="Uploaded"
                      fill
                      sizes="(min-width: 640px) 320px, 200px"
                      className="rounded-lg object-contain"
                    />
                  </div>
                  <p className="text-sm text-muted-foreground">{imageFile?.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {(imageFile?.size || 0) > 1024 * 1024
                      ? `${((imageFile?.size || 0) / (1024 * 1024)).toFixed(2)} MB`
                      : `${((imageFile?.size || 0) / 1024).toFixed(2)} KB`}
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  <Upload className="h-8 w-8 mx-auto text-muted-foreground" />
                  <p className="text-sm font-medium">Click to upload or drag and drop</p>
                  <p className="text-xs text-muted-foreground">JPG or PNG, max 10MB</p>
                </div>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png"
                onChange={handleImageUpload}
                className="hidden"
              />
            </div>
          </div>

          {/* Duration */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Duration</label>
            <div className="flex gap-4">
              {["5", "10"].map((dur) => (
                <Button
                  key={dur}
                  variant={duration === dur ? "default" : "outline"}
                  onClick={() => setDuration(dur)}
                  className="flex-1"
                >
                  {dur} seconds
                </Button>
              ))}
            </div>
          </div>

          {/* Script */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Narrative Script ({script.length}/2500)</label>
            <Textarea
              placeholder="Paste the narration or scene description that the agent should use to craft prompts..."
              value={script}
              onChange={(e) => setScript(e.target.value.slice(0, 2500))}
              rows={6}
              className="font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground">
              The backend agent will transform this script into production-ready positive and negative prompts.
            </p>
          </div>

          {/* CFG Scale */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium">CFG Scale</label>
              <span className="text-sm font-mono text-muted-foreground">{cfgScale.toFixed(2)}</span>
            </div>
            <Slider
              value={[cfgScale]}
              onValueChange={(value) => setCfgScale(value[0])}
              min={0}
              max={1}
              step={0.1}
              className="w-full"
            />
            <p className="text-xs text-muted-foreground">
              Lower values = more flexible, Higher values = more strict adherence to prompt
            </p>
          </div>

          <Button onClick={handleGenerateVideo} disabled={loading || !image || script.trim().length < 10} className="w-full" size="lg">
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Creating Video Task...
              </>
            ) : (
              <>
                <ImageIcon className="mr-2 h-4 w-4" />
                Generate Video
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
        <Alert className="border-green-500/50 bg-green-500/10">
          <CheckCircle2 className="h-4 w-4 text-green-600" />
          <AlertDescription className="text-green-600">Video task created successfully!</AlertDescription>
        </Alert>
      )}

      {/* Generated Prompts */}
      {agentPrompts && (
        <Card>
          <CardHeader>
            <CardTitle>Generated Prompts</CardTitle>
            <CardDescription>
              Review the agent-crafted guidance used for the submitted Kling task.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Positive Prompt</label>
              <Textarea value={agentPrompts.prompt} readOnly rows={4} className="font-mono text-sm" />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Negative Prompt</label>
              <Textarea
                value={agentPrompts.negative_prompt || "(None)"}
                readOnly
                rows={3}
                className="font-mono text-sm"
              />
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">CFG Scale</p>
                <p className="font-mono text-sm">{agentPrompts.cfg_scale.toFixed(2)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Duration</p>
                <p className="font-mono text-sm">{agentPrompts.duration} seconds</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Status Section */}
      {taskId && (
        <Card>
          <CardHeader>
            <CardTitle>Task Status</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">Task ID</p>
              <p className="font-mono text-sm break-all">{taskId}</p>
            </div>

            <div className="flex items-center justify-between">
              <Badge className={getStatusColor(taskStatus)}>{taskStatus}</Badge>
              <div className="flex items-center gap-2">
                {autoPolling && (
                  <span className="text-xs text-muted-foreground">Elapsed: {formatTime(elapsedTime)}</span>
                )}
                <Button onClick={handleCheckStatus} disabled={polling} variant="outline" size="sm">
                  {polling ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Checking...
                    </>
                  ) : (
                    <>
                      <RefreshCw className="mr-2 h-4 w-4" />
                      Check Status
                    </>
                  )}
                </Button>
              </div>
            </div>

            {taskStatus === "IN_PROGRESS" && (
              <Alert className="border-blue-500/50 bg-blue-500/10">
                <AlertCircle className="h-4 w-4 text-blue-600" />
                <AlertDescription className="text-blue-600">
                  Video is being generated. Auto-refreshing every 5 seconds...
                </AlertDescription>
              </Alert>
            )}

            {taskStatus === "CREATED" && (
              <Alert className="border-yellow-500/50 bg-yellow-500/10">
                <AlertCircle className="h-4 w-4 text-yellow-600" />
                <AlertDescription className="text-yellow-600">
                  Task created. Waiting to start processing...
                </AlertDescription>
              </Alert>
            )}

            {taskStatus === "FAILED" && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>Video generation failed. Please try again.</AlertDescription>
              </Alert>
            )}
          </CardContent>
        </Card>
      )}

      {/* Generated Videos */}
      {generatedVideos.length > 0 && (
        <div className="space-y-4">
          <h3 className="text-lg font-semibold">Generated Videos</h3>
          <div className="grid gap-4 md:grid-cols-2">
            {generatedVideos.map((videoUrl, idx) => (
              <Card key={idx}>
                <CardContent className="pt-6 space-y-3">
                  <video src={videoUrl} controls className="w-full rounded-lg bg-black" />
                  <a
                    href={videoUrl}
                    download
                    className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline"
                  >
                    <Download className="h-4 w-4" />
                    Download Video
                  </a>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
