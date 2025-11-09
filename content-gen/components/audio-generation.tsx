"use client"
import { useCallback, useEffect, useMemo, useState, useDeferredValue } from "react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Loader2,
  Download,
  AlertCircle,
  CheckCircle2,
  Copy,
  Music,
  Trash2,
  Waves,
  Plus,
} from "lucide-react"

interface AudioOutput {
  scene_id: string
  file_name: string
  audio_file: string
}

interface AudioResponse {
  status: string
  outputs: AudioOutput[]
  manifest_file: string
}

interface LongformStitchingInstructions {
  crossfade_ms: number
  normalize_volume: boolean
  output_format: string
}

interface LongformPlanSegment {
  segment_id: string
  text: string
  emotion: string
  character_count: number
  estimated_duration_seconds: number
  pause_after_seconds: number
  enforce_comma_pause?: boolean
}

interface LongformPlan {
  voice_id: string
  segments: LongformPlanSegment[]
  total_segments: number
  total_estimated_duration_seconds: number
  stitching_instructions: LongformStitchingInstructions
}

interface LongformSegmentOutput {
  segment_id: string
  emotion: string
  character_count: number
  estimated_duration_seconds: number
  pause_after_seconds: number
  scene_title?: string
  enforce_comma_pause?: boolean
  file_name: string
  audio_file: string
}

interface LongformCombinedAsset {
  file_name: string
  audio_file: string
}

interface LongformResponse {
  status: string
  generated_at: string
  voice_id: string
  input_mode: "scene_collection" | "script"
  plan: LongformPlan
  segments: LongformSegmentOutput[]
  combined: LongformCombinedAsset
  manifest_file: string
}

interface SceneFormRow {
  sceneId: string
  title: string
  text: string
  pauseSeconds: string
  commaPause: boolean
}

const EXAMPLE_SCRIPT = `Scene 1: A peaceful morning
Character A: Good morning, how are you?
Character B: I'm doing well, thank you for asking.

Scene 2: At the temple
Character A: This place is so serene.
Character B: Yes, it brings peace to the soul.`

const AUDIO_STORAGE_KEY = "ib-audio-generation-state"
const LONGFORM_STORAGE_KEY = "ib-audio-longform-state"

export default function AudioGeneration() {
  const [mode, setMode] = useState<"dialogue" | "longform">("dialogue")

  // Scene-based dialogue generation state
  const [script, setScript] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [success, setSuccess] = useState(false)
  const [audioOutputs, setAudioOutputs] = useState<AudioOutput[]>([])
  const [manifestFile, setManifestFile] = useState("")
  const [copied, setCopied] = useState(false)
  const deferredOutputs = useDeferredValue(audioOutputs)
  const hasOutputs = deferredOutputs.length > 0
  const manifestAvailable = useMemo(() => Boolean(manifestFile), [manifestFile])

  // Long-form generation state
  const [longformInputMode, setLongformInputMode] = useState<"scenes" | "script">("scenes")
  const [sceneRows, setSceneRows] = useState<SceneFormRow[]>([
    {
      sceneId: "Scene 1",
      title: "",
      text: "",
      pauseSeconds: "3.5",
      commaPause: true,
    },
  ])
  const [longformScript, setLongformScript] = useState("")
  const [longformVoiceId, setLongformVoiceId] = useState("")
  const [longformPrefix, setLongformPrefix] = useState("")
  const [longformLoading, setLongformLoading] = useState(false)
  const [longformError, setLongformError] = useState("")
  const [longformSuccess, setLongformSuccess] = useState(false)
  const [longformData, setLongformData] = useState<LongformResponse | null>(null)
  const deferredLongformSegments = useDeferredValue(longformData?.segments ?? [])
  const hasLongformOutputs = deferredLongformSegments.length > 0

  const planSegmentMap = useMemo(() => {
    if (!longformData) return new Map<string, LongformPlanSegment>()
    return new Map(longformData.plan.segments.map((segment) => [segment.segment_id, segment]))
  }, [longformData])

  useEffect(() => {
    if (typeof window === "undefined") return

    try {
      const stored = window.localStorage.getItem(AUDIO_STORAGE_KEY)
      if (stored) {
        const parsed = JSON.parse(stored)
        if (Array.isArray(parsed?.outputs) && parsed.outputs.length > 0) {
          setAudioOutputs(parsed.outputs)
          setManifestFile(typeof parsed.manifestFile === "string" ? parsed.manifestFile : "")
          setSuccess(true)
        }
      }

      const storedLongform = window.localStorage.getItem(LONGFORM_STORAGE_KEY)
      if (storedLongform) {
        const parsed = JSON.parse(storedLongform)
        if (parsed && typeof parsed === "object") {
          setLongformData(parsed)
          setLongformSuccess(true)
        }
      }
    } catch (err) {
      console.warn("Failed to restore audio generation state", err)
    }
  }, [])

  useEffect(() => {
    if (typeof window === "undefined") return

    if (audioOutputs.length === 0) {
      window.localStorage.removeItem(AUDIO_STORAGE_KEY)
    } else {
      const payload = {
        outputs: audioOutputs,
        manifestFile,
      }
      window.localStorage.setItem(AUDIO_STORAGE_KEY, JSON.stringify(payload))
    }
  }, [audioOutputs, manifestFile])

  useEffect(() => {
    if (typeof window === "undefined") return

    if (!longformData) {
      window.localStorage.removeItem(LONGFORM_STORAGE_KEY)
    } else {
      window.localStorage.setItem(LONGFORM_STORAGE_KEY, JSON.stringify(longformData))
    }
  }, [longformData])

  const handleGenerateAudio = useCallback(async () => {
    if (!script.trim()) {
      setError("Please enter a script")
      return
    }

    setLoading(true)
    setError("")
    setSuccess(false)

    try {
      const response = await fetch("http://127.0.0.1:8002/api/v1/elevenlabs/generate-audio", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ script }),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || "Failed to generate audio")
      }

      const data: AudioResponse = await response.json()
      setAudioOutputs(data.outputs)
      setManifestFile(data.manifest_file)
      setSuccess(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred")
    } finally {
      setLoading(false)
    }
  }, [script])

  const handleClearResults = useCallback(() => {
    setAudioOutputs([])
    setManifestFile("")
    setSuccess(false)
    setError("")
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(AUDIO_STORAGE_KEY)
    }
  }, [])

  const handleCopyScript = useCallback(() => {
    navigator.clipboard.writeText(EXAMPLE_SCRIPT)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [])

  const handleAddSceneRow = useCallback(() => {
    setSceneRows((prev) => [
      ...prev,
      {
        sceneId: `Scene ${prev.length + 1}`,
        title: "",
        text: "",
        pauseSeconds: "0",
        commaPause: true,
      },
    ])
  }, [])

  const handleSceneRowChange = useCallback(
    (index: number, key: keyof SceneFormRow, value: string) => {
      setSceneRows((prev) => {
        const next = [...prev]
        next[index] = {
          ...next[index],
          [key]: key === "pauseSeconds" ? value.replace(/[^0-9.]/g, "") : value,
        }
        return next
      })
    },
    [],
  )

  const handleScenePauseToggle = useCallback((index: number, checked: boolean) => {
    setSceneRows((prev) => {
      const next = [...prev]
      next[index] = {
        ...next[index],
        commaPause: checked,
      }
      return next
    })
  }, [])

  const handleRemoveSceneRow = useCallback((index: number) => {
    setSceneRows((prev) => {
      if (prev.length === 1) {
        return prev
      }
      const next = [...prev]
      next.splice(index, 1)
      return next.map((row, idx) => ({
        ...row,
        sceneId: row.sceneId.trim() ? row.sceneId : `Scene ${idx + 1}`,
      }))
    })
  }, [])

  const hasValidScenes = useMemo(
    () => sceneRows.some((row) => row.text.trim().length >= 20),
    [sceneRows],
  )

  const handleGenerateLongform = useCallback(async () => {
    if (longformInputMode === "scenes" && !hasValidScenes) {
      setLongformError("Add at least one scene with 20+ characters of narration.")
      return
    }

    if (longformInputMode === "script" && !longformScript.trim()) {
      setLongformError("Please enter a narration script")
      return
    }

    setLongformLoading(true)
    setLongformError("")
    setLongformSuccess(false)

    const payload: Record<string, unknown> = {
    }

    if (longformInputMode === "scenes") {
      const scenesPayload = sceneRows
        .map((row, index) => {
          const text = row.text.trim()
          if (!text) return null
          const parsedPause = Number.parseFloat(row.pauseSeconds || "0")
          return {
            scene_id: row.sceneId.trim() || `Scene ${index + 1}`,
            title: row.title.trim() || undefined,
            text,
            pause_after_seconds: Number.isFinite(parsedPause) && parsedPause >= 0 ? parsedPause : 0,
            enforce_comma_pause: row.commaPause,
          }
        })
        .filter(Boolean)

      if (!scenesPayload.length) {
        setLongformLoading(false)
        setLongformError("Scenes payload is empty. Please add narration text.")
        return
      }

      payload.scenes = scenesPayload
    } else {
      payload.script = longformScript.trim()
    }

    if (longformVoiceId.trim()) {
      payload.voice_id = longformVoiceId.trim()
    }
    if (longformPrefix.trim()) {
      payload.filename_prefix = longformPrefix.trim()
    }

    try {
      const response = await fetch("http://127.0.0.1:8002/api/v1/elevenlabs/generate-audio/longform", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || "Failed to generate long-form audio")
      }

      const data: LongformResponse = await response.json()
      setLongformData(data)
      setLongformSuccess(true)
    } catch (err) {
      setLongformError(err instanceof Error ? err.message : "An error occurred")
    } finally {
      setLongformLoading(false)
    }
  }, [
    hasValidScenes,
    longformInputMode,
    longformPrefix,
    longformScript,
    longformVoiceId,
    sceneRows,
  ])

  const handleClearLongform = useCallback(() => {
    setLongformData(null)
    setLongformSuccess(false)
    setLongformError("")
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(LONGFORM_STORAGE_KEY)
    }
  }, [])

  return (
    <Tabs value={mode} onValueChange={(value) => setMode(value as "dialogue" | "longform")} className="space-y-6">
      <TabsList className="grid w-full grid-cols-2 rounded-2xl bg-muted/40 p-1">
        <TabsTrigger value="dialogue" className="flex items-center gap-2 data-[state=active]:bg-background data-[state=active]:shadow-sm">
          <Music className="h-4 w-4" />
          <span>Scene Dialogue</span>
        </TabsTrigger>
        <TabsTrigger value="longform" className="flex items-center gap-2 data-[state=active]:bg-background data-[state=active]:shadow-sm">
          <Waves className="h-4 w-4" />
          <span>Long-form Narration</span>
        </TabsTrigger>
      </TabsList>

      <TabsContent value="dialogue" className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Generate Audio Dialogue</CardTitle>
            <CardDescription>
              Enter a multi-scene script to generate AI voice dialogues using ElevenLabs
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium">Script</label>
                <Button variant="ghost" size="sm" onClick={handleCopyScript} className="text-xs h-7">
                  <Copy className="h-3 w-3 mr-1" />
                  {copied ? "Copied!" : "Use Example"}
                </Button>
              </div>
              <Textarea
                placeholder={`Enter your multi-scene script here. Example:

Scene 1: A peaceful morning
Character A: Good morning, how are you?
Character B: I'm doing well, thank you for asking.

Scene 2: At the temple
Character A: This place is so serene.
Character B: Yes, it brings peace to the soul.`}
                value={script}
                onChange={(e) => setScript(e.target.value)}
                rows={16}
                className="font-mono text-sm min-h-[320px]"
              />
              <p className="text-xs text-muted-foreground">
                Format: Scene descriptions followed by character dialogues. Each scene will generate separate audio
                files.
              </p>
            </div>

            <Button onClick={handleGenerateAudio} disabled={loading || !script.trim()} className="w-full" size="lg">
              {loading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Generating Audio...
                </>
              ) : (
                <>
                  <Music className="mr-2 h-4 w-4" />
                  Generate Audio
                </>
              )}
            </Button>

            {hasOutputs && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleClearResults}
                className="w-full"
                disabled={loading}
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Clear Results
              </Button>
            )}
          </CardContent>
        </Card>

        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {success && (
          <Alert className="border-green-500/50 bg-green-500/10 animate-fade-in-up">
            <CheckCircle2 className="h-4 w-4 text-green-600" />
            <AlertDescription className="text-green-600">
              Audio generated successfully! {audioOutputs.length} scene(s) created.
            </AlertDescription>
          </Alert>
        )}

        {hasOutputs && (
          <div className="space-y-4 animate-fade-in-up">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold">Generated Audio Files</h3>
              <Badge variant="outline">{deferredOutputs.length} files</Badge>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              {deferredOutputs.map((output, index) => (
                <Card
                  key={`${output.scene_id}-${output.file_name}`}
                  className="hover:border-primary/50 hover-lift animate-fade-in-up"
                  style={{ animationDelay: `${index * 40}ms` }}
                >
                  <CardContent className="pt-6">
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-sm font-medium">{output.scene_id}</span>
                        <Badge variant="secondary">Audio</Badge>
                      </div>
                      <p className="text-xs text-muted-foreground break-all">{output.file_name}</p>

                      <audio src={`http://127.0.0.1:8002${output.audio_file}`} controls className="w-full h-8" />

                      <a
                        href={`http://127.0.0.1:8002${output.audio_file}`}
                        download
                        className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline"
                      >
                        <Download className="h-4 w-4" />
                        Download Audio
                      </a>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>

            {manifestAvailable && (
              <Card
                className="bg-muted/50 hover-lift animate-fade-in-up"
                style={{ animationDelay: `${deferredOutputs.length * 40}ms` }}
              >
                <CardContent className="pt-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">Manifest File</p>
                      <p className="text-xs text-muted-foreground">{manifestFile}</p>
                    </div>
                    <a
                      href={`http://127.0.0.1:8002${manifestFile}`}
                      download
                      className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline"
                    >
                      <Download className="h-4 w-4" />
                      Download
                    </a>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </TabsContent>

      <TabsContent value="longform" className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Generate Long-form Narration</CardTitle>
            <CardDescription>
              Clean the script, infer pauses and emotions automatically, and stitch the result into one master audio file.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant={longformInputMode === "scenes" ? "default" : "outline"}
                size="sm"
                onClick={() => setLongformInputMode("scenes")}
              >
                Scene Planner
              </Button>
              <Button
                type="button"
                variant={longformInputMode === "script" ? "default" : "outline"}
                size="sm"
                onClick={() => setLongformInputMode("script")}
              >
                Raw Script
              </Button>
            </div>

            {longformInputMode === "scenes" ? (
              <div className="space-y-4">
                <p className="text-sm text-muted-foreground">
                  Define each narration scene and the silence that should follow before the next clip begins.
                </p>
                <div className="space-y-4">
                  {sceneRows.map((scene, index) => (
                    <div key={`scene-row-${index}`} className="space-y-3 rounded-lg border border-dashed p-4">
                      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                        <div className="flex flex-1 flex-col gap-3 md:flex-row">
                          <div className="flex-1 space-y-2">
                            <label className="text-sm font-medium">Scene ID</label>
                            <Input
                              value={scene.sceneId}
                              onChange={(e) => handleSceneRowChange(index, "sceneId", e.target.value)}
                              placeholder={`Scene ${index + 1}`}
                            />
                          </div>
                          <div className="flex-1 space-y-2">
                            <label className="text-sm font-medium">Title (optional)</label>
                            <Input
                              value={scene.title}
                              onChange={(e) => handleSceneRowChange(index, "title", e.target.value)}
                              placeholder="Morning Hook"
                            />
                          </div>
                          <div className="w-full space-y-2 md:w-40">
                            <label className="text-sm font-medium">Pause After (sec)</label>
                            <Input
                              type="number"
                              min={0}
                              step={0.5}
                              value={scene.pauseSeconds}
                              onChange={(e) => handleSceneRowChange(index, "pauseSeconds", e.target.value)}
                            />
                            <p className="text-xs text-muted-foreground">Silence appended after this scene.</p>
                          </div>
                          <label className="flex w-full items-center justify-between gap-2 rounded-md border border-dashed px-3 py-2 text-left md:w-56">
                            <div>
                              <p className="text-sm font-medium">Pause after punctuation</p>
                              <p className="text-xs text-muted-foreground">Apply 1.5s pause after ., , and ।</p>
                            </div>
                            <Checkbox
                              checked={scene.commaPause}
                              onCheckedChange={(checked) =>
                                handleScenePauseToggle(index, !!checked)
                              }
                              aria-label="Toggle punctuation pause"
                            />
                          </label>
                        </div>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRemoveSceneRow(index)}
                          disabled={sceneRows.length === 1}
                          className="text-destructive"
                        >
                          <Trash2 className="mr-1 h-4 w-4" /> Remove
                        </Button>
                      </div>
                      <div className="space-y-2">
                        <label className="text-sm font-medium">Narration Text</label>
                        <Textarea
                          value={scene.text}
                          onChange={(e) => handleSceneRowChange(index, "text", e.target.value)}
                          rows={6}
                          className="font-mono text-sm"
                          placeholder="Namaste! Swagat hai..."
                        />
                        <p className="text-xs text-muted-foreground">
                          Include any SSML instructions or emphasis markers. Minimum 20 characters recommended.
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
                <Button type="button" variant="outline" size="sm" onClick={handleAddSceneRow} className="w-full md:w-auto">
                  <Plus className="mr-2 h-4 w-4" /> Add Scene
                </Button>
              </div>
            ) : (
              <div className="space-y-2">
                <label className="text-sm font-medium">Narration Script</label>
                <Textarea
                  placeholder="Paste long-form narration here. Section headers are ignored automatically."
                  value={longformScript}
                  onChange={(e) => setLongformScript(e.target.value)}
                  rows={16}
                  className="font-mono text-sm min-h-[320px]"
                />
                <p className="text-xs text-muted-foreground">
                  The agent removes titles, inserts SSML pauses, and segments the script for optimal synthesis.
                </p>
              </div>
            )}

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <label className="text-sm font-medium">Voice ID Override (optional)</label>
                <Input
                  placeholder="7PW9SpipqSt1iujPCdRh"
                  value={longformVoiceId}
                  onChange={(e) => setLongformVoiceId(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">Leave blank to use the voice selected by the agent plan.</p>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Filename Prefix (optional)</label>
                <Input
                  placeholder="nirvana_day1"
                  value={longformPrefix}
                  onChange={(e) => setLongformPrefix(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Applied to each segment and the stitched master file for easier identification.
                </p>
              </div>
            </div>

            <Button
              onClick={handleGenerateLongform}
              disabled={
                longformLoading ||
                (longformInputMode === "scenes" ? !hasValidScenes : !longformScript.trim())
              }
              className="w-full"
              size="lg"
            >
              {longformLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Building Narration...
                </>
              ) : (
                <>
                  <Waves className="mr-2 h-4 w-4" />
                  Generate Long-form Audio
                </>
              )}
            </Button>

            {hasLongformOutputs && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleClearLongform}
                className="w-full"
                disabled={longformLoading}
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Clear Results
              </Button>
            )}
          </CardContent>
        </Card>

        {longformError && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{longformError}</AlertDescription>
          </Alert>
        )}

        {longformSuccess && longformData && (
          <Alert className="border-green-500/50 bg-green-500/10 animate-fade-in-up">
            <CheckCircle2 className="h-4 w-4 text-green-600" />
            <AlertDescription className="text-green-600">
              Long-form narration ready! {longformData.plan.total_segments} segment(s) stitched into a single master file.
            </AlertDescription>
          </Alert>
        )}

        {hasLongformOutputs && longformData && (
          <div className="space-y-6 animate-fade-in-up">
            <Card className="hover-lift">
              <CardContent className="pt-6 space-y-3">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-sm font-medium">Narration Summary</p>
                    <p className="text-xs text-muted-foreground">
                      Voice ID: <span className="font-mono">{longformData.voice_id}</span>
                    </p>
                  </div>
                  <Badge variant="outline">{longformData.plan.total_segments} segments</Badge>
                </div>
                <div className="text-xs text-muted-foreground space-y-1">
                  <p>
                    Estimated duration: {longformData.plan.total_estimated_duration_seconds.toFixed(1)} seconds
                  </p>
                  <p>
                    Stitching: crossfade {longformData.plan.stitching_instructions.crossfade_ms} ms · format {" "}
                    {longformData.plan.stitching_instructions.output_format.toUpperCase()} · normalised {" "}
                    {longformData.plan.stitching_instructions.normalize_volume ? "yes" : "no"}
                  </p>
                  <p>
                    Input mode: {longformData.input_mode === "scene_collection" ? "Scene collection" : "Raw script"}
                  </p>
                  <p>Generated: {new Date(longformData.generated_at).toLocaleString()}</p>
                </div>
                <div className="space-y-3">
                  <p className="text-sm font-medium">Stitched Master</p>
                  <audio
                    src={`http://127.0.0.1:8002${longformData.combined.audio_file}`}
                    controls
                    className="w-full"
                  />
                  <a
                    href={`http://127.0.0.1:8002${longformData.combined.audio_file}`}
                    download
                    className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline"
                  >
                    <Download className="h-4 w-4" />
                    Download Master Audio ({longformData.combined.file_name})
                  </a>
                </div>
                <div className="flex items-center justify-between border-t border-border pt-4">
                  <div>
                    <p className="text-xs text-muted-foreground">Manifest</p>
                    <p className="text-xs font-mono text-muted-foreground">{longformData.manifest_file}</p>
                  </div>
                  <a
                    href={`http://127.0.0.1:8002${longformData.manifest_file}`}
                    download
                    className="inline-flex items-center gap-2 text-xs font-medium text-primary hover:underline"
                  >
                    <Download className="h-4 w-4" />
                    Download
                  </a>
                </div>
              </CardContent>
            </Card>

            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold">Segment Details</h3>
                <Badge variant="outline">{deferredLongformSegments.length} files</Badge>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                {deferredLongformSegments.map((segment, index) => {
                  const planSegment = planSegmentMap.get(segment.segment_id)
                  return (
                    <Card
                      key={`${segment.segment_id}-${segment.file_name}`}
                      className="hover:border-primary/50 hover-lift animate-fade-in-up"
                      style={{ animationDelay: `${index * 40}ms` }}
                    >
                      <CardContent className="pt-6 space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-sm font-medium">{segment.segment_id}</span>
                          <Badge variant="secondary">{segment.emotion}</Badge>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {segment.character_count} characters · {segment.estimated_duration_seconds.toFixed(1)}s
                        </p>
                        {segment.scene_title && (
                          <p className="text-xs font-medium text-muted-foreground">{segment.scene_title}</p>
                        )}
                        <p className="text-xs text-muted-foreground">
                          Pause after: {(segment.pause_after_seconds ?? 0).toFixed(1)}s
                        </p>
                        {planSegment && (
                          <pre className="whitespace-pre-wrap rounded-md bg-muted/60 p-3 text-xs text-muted-foreground">
                            {planSegment.text}
                          </pre>
                        )}
                        <audio
                          src={`http://127.0.0.1:8002${segment.audio_file}`}
                          controls
                          className="w-full h-8"
                        />
                        <a
                          href={`http://127.0.0.1:8002${segment.audio_file}`}
                          download
                          className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline"
                        >
                          <Download className="h-4 w-4" />
                          Download Segment ({segment.file_name})
                        </a>
                      </CardContent>
                    </Card>
                  )
                })}
              </div>
            </div>
          </div>
        )}
      </TabsContent>
    </Tabs>
  )
}
