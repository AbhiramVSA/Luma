"use client"

import { useState, useMemo, useDeferredValue, useCallback } from "react"

import Image from "next/image"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  AlertCircle,
  CheckCircle2,
  Download,
  ExternalLink,
  Loader2,
  Plus,
  Trash2,
  Video,
} from "lucide-react"

interface SceneInput {
  scene_id: string
  image_url: string
  notes: string
  preview_url?: string
  uploading: boolean
  upload_error?: string
}

interface SceneVideoAsset {
  scene_id: string
  order: number
  video_url: string
  placeholder?: string | null
}

interface AudioOutput {
  scene_id?: string
  file_name?: string
  audio_file?: string
  [key: string]: unknown
}

interface HeyGenVideoResult {
  scene_id: string
  status: string
  video_id?: string | null
  video_url?: string | null
  message?: string | null
  thumbnail_url?: string | null
}

interface CreatomateRenderResponse {
  status: "success" | "failed"
  template_id: string
  modifications: Record<string, string>
  creatomate_job: Record<string, unknown>
  audio_outputs: AudioOutput[]
  scene_videos: SceneVideoAsset[]
  heygen_results: HeyGenVideoResult[]
  errors: string[]
}

const API_BASE_URL = "http://127.0.0.1:8002"
const ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"]
const MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024

const createEmptyScene = (): SceneInput => ({
  scene_id: "",
  image_url: "",
  notes: "",
  uploading: false,
})

export default function CreatomateRender() {
  const [script, setScript] = useState("")
  const [templateId, setTemplateId] = useState("")
  const [forceUploadAudio, setForceUploadAudio] = useState(true)
  const [waitForRender, setWaitForRender] = useState(false)
  const [scenes, setScenes] = useState<SceneInput[]>([createEmptyScene()])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [response, setResponse] = useState<CreatomateRenderResponse | null>(null)
  const deferredScenes = useDeferredValue(scenes)

  const populatedScenes = useMemo(
    () =>
      deferredScenes.filter(
        (scene) => scene.scene_id.trim().length > 0 && scene.image_url.trim().length > 0,
      ),
    [deferredScenes],
  )

  const handleSceneChange = useCallback(
    (index: number, field: keyof SceneInput, value: string) => {
      setScenes((prev) => {
        const next = [...prev]
        next[index] = {
          ...next[index],
          [field]: value,
          ...(field !== "image_url" ? { upload_error: undefined } : {}),
        }
        return next
      })
    },
    [],
  )

  const handleAddScene = useCallback(() => {
    setScenes((prev) => [...prev, createEmptyScene()])
  }, [])

  const handleRemoveScene = useCallback((index: number) => {
    setScenes((prev) => (prev.length === 1 ? prev : prev.filter((_, idx) => idx !== index)))
  }, [])

  const handleSceneImageUpload = useCallback(
    async (index: number, files: FileList | null) => {
      const file = files?.[0]
      if (!file) return

      const sceneRecord = scenes[index]
      const sceneId = sceneRecord?.scene_id.trim()

      if (!sceneId) {
        setScenes((prev) => {
          const next = [...prev]
          next[index] = {
            ...next[index],
            upload_error: "Set a Scene ID before uploading an image.",
          }
          return next
        })
        return
      }

      if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
        setScenes((prev) => {
          const next = [...prev]
          next[index] = {
            ...next[index],
            upload_error: "Unsupported format. Use JPG, PNG, or WEBP.",
          }
          return next
        })
        return
      }

      if (file.size > MAX_IMAGE_SIZE_BYTES) {
        setScenes((prev) => {
          const next = [...prev]
          next[index] = {
            ...next[index],
            upload_error: "Image exceeds 10 MB limit.",
          }
          return next
        })
        return
      }

      setScenes((prev) => {
        const next = [...prev]
        next[index] = {
          ...next[index],
          uploading: true,
          upload_error: undefined,
        }
        return next
      })

      const formData = new FormData()
      formData.append("scene_id", sceneId)
      formData.append("file", file)

      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/creatomate/upload-image`, {
          method: "POST",
          body: formData,
        })

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}))
          throw new Error(errorData.detail || "Image upload failed")
        }

        const data: { url?: string } = await response.json()
        const relativeUrl = typeof data.url === "string" ? data.url : ""
        const absoluteUrl = relativeUrl.startsWith("http")
          ? relativeUrl
          : `${API_BASE_URL}${relativeUrl}`

        setScenes((prev) => {
          const next = [...prev]
          next[index] = {
            ...next[index],
            image_url: relativeUrl,
            preview_url: absoluteUrl,
            uploading: false,
            upload_error: undefined,
          }
          return next
        })
      } catch (err) {
        const message = err instanceof Error ? err.message : "Image upload failed"
        setScenes((prev) => {
          const next = [...prev]
          next[index] = {
            ...next[index],
            uploading: false,
            upload_error: message,
          }
          return next
        })
      }
    },
    [scenes],
  )

  const resetForm = useCallback(() => {
    setLoading(false)
    setError("")
    setResponse(null)
    setScript("")
    setTemplateId("")
    setForceUploadAudio(true)
    setWaitForRender(false)
    setScenes([createEmptyScene()])
  }, [])

  const handleSubmit = useCallback(async () => {
    if (script.trim().length < 10) {
      setError("Script must be at least 10 characters long")
      return
    }

    if (scenes.some((scene) => scene.uploading)) {
      setError("Wait for all image uploads to finish before submitting.")
      return
    }

    const preparedScenes = scenes
      .map((scene) => ({
        scene_id: scene.scene_id.trim(),
        image_url: scene.image_url.trim(),
        notes: scene.notes.trim() || undefined,
      }))
      .filter((scene) => scene.scene_id.length > 0)

    const scenesMissingImages = preparedScenes.filter((scene) => scene.image_url.length === 0)
    if (scenesMissingImages.length > 0) {
      setError("Upload an image for every scene with a Scene ID.")
      return
    }

    if (preparedScenes.length === 0) {
      setError("Add at least one scene with a Scene ID and uploaded image.")
      return
    }

    const payload: Record<string, unknown> = {
      script: script.trim(),
      force_upload_audio: forceUploadAudio,
      wait_for_render: waitForRender,
      scenes: preparedScenes,
    }

    if (templateId.trim()) {
      payload.template_id = templateId.trim()
    }

    setLoading(true)
    setError("")
    setResponse(null)

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/creatomate/render`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || "Creatomate render failed")
      }

      const data: CreatomateRenderResponse = await response.json()
      setResponse(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : "An unexpected error occurred")
    } finally {
      setLoading(false)
    }
  }, [forceUploadAudio, scenes, script, templateId, waitForRender])

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Render Final Video with Creatomate</CardTitle>
          <CardDescription>
            Run the full pipeline: reuse your script, generate missing HeyGen assets, and submit the Creatomate render in
            one click.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <Label htmlFor="creatomate-script">Script</Label>
            <Textarea
              id="creatomate-script"
              placeholder="Paste the screenplay used for audio and video generation..."
              value={script}
              onChange={(event) => setScript(event.target.value)}
              rows={12}
              className="font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground">Minimum 10 characters. The automation reuses this script to rebuild audio, HeyGen videos, and Creatomate inputs.</p>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="creatomate-template">Template ID (optional)</Label>
              <Input
                id="creatomate-template"
                placeholder="cmpl_..."
                value={templateId}
                onChange={(event) => setTemplateId(event.target.value)}
              />
              <p className="text-xs text-muted-foreground">Override the default Creatomate template configured in the backend.</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="creatomate-scenes-count">Scene Metadata</Label>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Badge variant="secondary">{populatedScenes.length} scene(s)</Badge>
                <span>Rows require both Scene ID and uploaded image.</span>
              </div>
            </div>
          </div>

          <div className="grid gap-4">
            {scenes.map((scene, index) => (
              <Card key={`scene-${index}`} className="border-dashed">
                <CardHeader className="py-4">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">Scene {index + 1}</CardTitle>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => handleRemoveScene(index)}
                      className="h-8 w-8"
                      disabled={scenes.length === 1}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid gap-4 md:grid-cols-3">
                    <div className="space-y-2">
                      <Label htmlFor={`scene-id-${index}`}>Scene ID</Label>
                      <Input
                        id={`scene-id-${index}`}
                        placeholder="scene_1"
                        value={scene.scene_id}
                        onChange={(event) => handleSceneChange(index, "scene_id", event.target.value)}
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor={`scene-image-${index}`}>Scene Image (required)</Label>
                      <Input
                        id={`scene-image-${index}`}
                        type="file"
                        accept={ALLOWED_IMAGE_TYPES.join(",")}
                        disabled={scene.uploading}
                        onChange={async (event) => {
                          await handleSceneImageUpload(index, event.target.files)
                          event.target.value = ""
                        }}
                      />
                      <p className="text-xs text-muted-foreground">Upload JPG, PNG, or WEBP (max 10MB). Scene ID must be set before uploading.</p>
                      {scene.uploading && <p className="text-xs text-blue-600">Uploading image...</p>}
                      {scene.upload_error && <p className="text-xs text-red-600">{scene.upload_error}</p>}
                      {(scene.preview_url || scene.image_url) && (
                        <div className="flex items-center gap-3 rounded-md border border-dashed border-border/60 p-2">
                          <Image
                            src={
                              scene.preview_url
                                || (scene.image_url.startsWith("http")
                                  ? scene.image_url
                                  : `${API_BASE_URL}${scene.image_url}`)
                            }
                            alt={`${scene.scene_id || `scene-${index + 1}`} reference`}
                            width={64}
                            height={64}
                            className="h-16 w-16 rounded-md object-cover"
                          />
                          {scene.image_url && (
                            <a
                              href={scene.image_url.startsWith("http") ? scene.image_url : `${API_BASE_URL}${scene.image_url}`}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
                            >
                              <ExternalLink className="h-3 w-3" /> View uploaded image
                            </a>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor={`scene-notes-${index}`}>Notes (optional)</Label>
                    <Textarea
                      id={`scene-notes-${index}`}
                      placeholder="Additional guidance for the automation agent..."
                      value={scene.notes}
                      onChange={(event) => handleSceneChange(index, "notes", event.target.value)}
                      rows={3}
                    />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" onClick={handleAddScene} className="hover-lift">
              <Plus className="h-4 w-4 mr-2" /> Add Scene
            </Button>
            <div className="flex items-center gap-2">
              <Checkbox
                id="force-upload-audio"
                checked={forceUploadAudio}
                onCheckedChange={(checked) => setForceUploadAudio(Boolean(checked))}
              />
              <Label htmlFor="force-upload-audio" className="text-sm font-medium cursor-pointer">
                Force re-upload HeyGen audio assets
              </Label>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="wait-for-render"
                checked={waitForRender}
                onCheckedChange={(checked) => setWaitForRender(Boolean(checked))}
              />
              <Label htmlFor="wait-for-render" className="text-sm font-medium cursor-pointer">
                Wait for Creatomate render completion
              </Label>
            </div>
          </div>

          <div className="grid gap-2 md:grid-cols-2">
            <Button
              type="button"
              onClick={handleSubmit}
              disabled={loading || script.trim().length < 10}
              className="w-full"
              size="lg"
            >
              {loading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Submitting Pipeline...
                </>
              ) : (
                <>
                  <Video className="mr-2 h-4 w-4" />
                  Render with Creatomate
                </>
              )}
            </Button>
            <Button type="button" variant="outline" onClick={resetForm} className="w-full" size="lg" disabled={loading}>
              <Trash2 className="mr-2 h-4 w-4" /> Clear Inputs
            </Button>
          </div>
        </CardContent>
      </Card>

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {response && (
        <div className="space-y-6 animate-fade-in-up">
          <Alert className={response.status === "success" ? "border-green-500/50 bg-green-500/10" : "border-red-500/60 bg-red-500/10"}>
            {response.status === "success" ? (
              <CheckCircle2 className="h-4 w-4 text-green-600" />
            ) : (
              <AlertCircle className="h-4 w-4 text-red-600" />
            )}
            <AlertDescription className={response.status === "success" ? "text-green-600" : "text-red-600"}>
              Creatomate render {response.status}. Template used: <span className="font-mono">{response.template_id}</span>
            </AlertDescription>
          </Alert>

          {response.errors.length > 0 && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                <ul className="list-disc list-inside space-y-1 text-sm">
                  {response.errors.map((err, index) => (
                    <li key={index}>{err}</li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Scene Videos</CardTitle>
              <CardDescription>Completed HeyGen clips mapped to Creatomate placeholders.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              {response.scene_videos.map((asset, index) => (
                <Card key={`${asset.scene_id}-${index}`} className="hover-lift">
                  <CardContent className="pt-6 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-sm font-medium">{asset.scene_id}</span>
                      <Badge variant="secondary">#{asset.order}</Badge>
                    </div>
                    {asset.placeholder && (
                      <p className="text-xs text-muted-foreground">Placeholder: {asset.placeholder}</p>
                    )}
                    {asset.video_url ? (
                      <video src={asset.video_url} controls className="w-full rounded-lg bg-black" />
                    ) : (
                      <p className="text-xs text-muted-foreground">Video URL missing</p>
                    )}
                  </CardContent>
                </Card>
              ))}
              {response.scene_videos.length === 0 && <p className="text-sm text-muted-foreground">No scene videos recorded.</p>}
            </CardContent>
          </Card>

          {response.audio_outputs.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Audio Outputs</CardTitle>
                <CardDescription>Audio files regenerated for this pipeline run.</CardDescription>
              </CardHeader>
              <CardContent className="grid gap-4 md:grid-cols-2">
                {response.audio_outputs.map((audio, index) => {
                  const downloadUrl =
                    typeof audio.audio_file === "string" && audio.audio_file.startsWith("/")
                      ? `${API_BASE_URL}${audio.audio_file}`
                      : (audio.audio_file as string | undefined)

                  return (
                    <Card key={`${audio.scene_id ?? "audio"}-${index}`} className="hover-lift">
                      <CardContent className="pt-6 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-sm font-medium">{audio.scene_id ?? "Unknown Scene"}</span>
                          <Badge variant="outline">Audio</Badge>
                        </div>
                        <p className="text-xs text-muted-foreground break-all">{audio.file_name ?? "unknown.mp3"}</p>
                        {downloadUrl ? (
                          <>
                            <audio src={downloadUrl} controls className="w-full h-8" />
                            <a
                              href={downloadUrl}
                              download
                              className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline"
                            >
                              <Download className="h-4 w-4" /> Download Audio
                            </a>
                          </>
                        ) : (
                          <p className="text-xs text-muted-foreground">Audio URL not available</p>
                        )}
                      </CardContent>
                    </Card>
                  )
                })}
              </CardContent>
            </Card>
          )}

          {response.heygen_results.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>HeyGen Job Summary</CardTitle>
                <CardDescription>Status for each generated clip.</CardDescription>
              </CardHeader>
              <CardContent className="grid gap-4 md:grid-cols-2">
                {response.heygen_results.map((result, index) => (
                  <Card key={`${result.scene_id}-${result.video_id ?? index}`} className="hover-lift">
                    <CardContent className="pt-6 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-sm font-medium">{result.scene_id}</span>
                        <Badge
                          className={
                            result.status === "completed"
                              ? "bg-green-500/10 text-green-600 border-green-500/50"
                              : result.status === "failed"
                                ? "bg-red-500/10 text-red-600 border-red-500/50"
                                : "bg-blue-500/10 text-blue-600 border-blue-500/50"
                          }
                        >
                          {result.status}
                        </Badge>
                      </div>
                      {result.video_url && (
                        <a
                          href={result.video_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline"
                        >
                          <ExternalLink className="h-4 w-4" /> View Video
                        </a>
                      )}
                      {result.message && <p className="text-xs text-muted-foreground">{result.message}</p>}
                    </CardContent>
                  </Card>
                ))}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Creatomate Job Payload</CardTitle>
              <CardDescription>Inspect the raw response from Creatomate for troubleshooting.</CardDescription>
            </CardHeader>
            <CardContent>
              <pre className="whitespace-pre-wrap break-all rounded-lg bg-muted/50 p-4 text-xs">
                {JSON.stringify(response.creatomate_job, null, 2)}
              </pre>
            </CardContent>
          </Card>

          {Object.keys(response.modifications).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Placeholder Modifications</CardTitle>
                <CardDescription>Values submitted to the Creatomate template.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {Object.entries(response.modifications).map(([key, value]) => (
                  <div key={key} className="flex items-center justify-between gap-4 rounded-md border border-border bg-muted/30 p-3 text-sm">
                    <span className="font-mono text-xs break-all">{key}</span>
                    <a
                      href={value}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-primary hover:underline"
                    >
                      <ExternalLink className="h-3 w-3" />
                      <span className="text-xs">Open</span>
                    </a>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
