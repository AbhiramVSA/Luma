"use client"

import { useCallback, useEffect, useMemo, useState, useDeferredValue } from "react"
import { AlertCircle, CheckCircle2, Copy, Download, Loader2, Music, Trash2 } from "lucide-react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { apiAssetUrl, apiFetch } from "@/lib/api"

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

const EXAMPLE_SCRIPT = `Scene 1: A peaceful morning
Character A: Good morning, how are you?
Character B: I'm doing well, thank you for asking.

Scene 2: At the temple
Character A: This place is so serene.
Character B: Yes, it brings peace to the soul.`

const STORAGE_KEY = "ib-audio-generation-state"

export default function AudioGeneration() {
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

  useEffect(() => {
    if (typeof window === "undefined") return
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY)
      if (!stored) return
      const parsed = JSON.parse(stored)
      if (Array.isArray(parsed?.outputs) && parsed.outputs.length > 0) {
        setAudioOutputs(parsed.outputs)
        setManifestFile(typeof parsed.manifestFile === "string" ? parsed.manifestFile : "")
        setSuccess(true)
      }
    } catch (err) {
      console.warn("Failed to restore audio generation state", err)
    }
  }, [])

  useEffect(() => {
    if (typeof window === "undefined") return
    if (!audioOutputs.length) {
      window.localStorage.removeItem(STORAGE_KEY)
      return
    }
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        outputs: audioOutputs,
        manifestFile,
      }),
    )
  }, [audioOutputs, manifestFile])

  const handleCopyScript = useCallback(() => {
    navigator.clipboard.writeText(EXAMPLE_SCRIPT)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }, [])

  const handleClearResults = useCallback(() => {
    setAudioOutputs([])
    setManifestFile("")
    setSuccess(false)
    setError("")
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(STORAGE_KEY)
    }
  }, [])

  const handleGenerateAudio = useCallback(async () => {
    if (!script.trim()) {
      setError("Please enter a script before generating audio")
      return
    }

    setLoading(true)
    setError("")
    setSuccess(false)

    try {
      const response = await apiFetch("/elevenlabs/generate-audio", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ script }),
      })

      if (!response.ok) {
        const detail = await response.json().catch(() => null)
        throw new Error(detail?.detail ?? `Generation failed with ${response.status}`)
      }

      const payload: AudioResponse = await response.json()
      setAudioOutputs(payload.outputs)
      setManifestFile(payload.manifest_file)
      setSuccess(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to generate audio")
    } finally {
      setLoading(false)
    }
  }, [script])

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Generate Audio Dialogue</CardTitle>
          <CardDescription>Produce per-scene ElevenLabs audio clips from a structured script.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium">Script</label>
              <Button variant="ghost" size="sm" onClick={handleCopyScript} className="text-xs h-7">
                <Copy className="mr-1 h-3 w-3" />
                {copied ? "Copied!" : "Use Example"}
              </Button>
            </div>
            <Textarea
              value={script}
              onChange={(event) => setScript(event.target.value)}
              rows={16}
              className="font-mono text-sm min-h-[320px]"
              placeholder={EXAMPLE_SCRIPT}
            />
            <p className="text-xs text-muted-foreground">
              Format: `Scene N` headings followed by dialogues. Each scene produces an individual audio file.
            </p>
          </div>

          <Button onClick={handleGenerateAudio} disabled={loading || !script.trim()} className="w-full" size="lg">
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Generating Audio...
              </>
            ) : (
              <>
                <Music className="mr-2 h-4 w-4" /> Generate Audio
              </>
            )}
          </Button>

          {hasOutputs && (
            <Button variant="outline" size="sm" onClick={handleClearResults} className="w-full" disabled={loading}>
              <Trash2 className="mr-2 h-4 w-4" /> Clear Results
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
            {deferredOutputs.map((output, index) => {
              const audioUrl = apiAssetUrl(output.audio_file)
              return (
                <Card
                  key={`${output.scene_id}-${output.file_name}`}
                  className="hover:border-primary/50 hover-lift animate-fade-in-up"
                  style={{ animationDelay: `${index * 40}ms` }}
                >
                  <CardContent className="pt-6 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-sm font-medium">{output.scene_id}</span>
                      <Badge variant="secondary">Audio</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground break-all">{output.file_name}</p>
                    <audio src={audioUrl} controls className="w-full h-8" />
                    <a
                      href={audioUrl}
                      download
                      className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline"
                    >
                      <Download className="h-4 w-4" /> Download Audio
                    </a>
                  </CardContent>
                </Card>
              )
            })}
          </div>

          {manifestAvailable && (
            <Card
              className="bg-muted/50 hover-lift animate-fade-in-up"
              style={{ animationDelay: `${deferredOutputs.length * 40}ms` }}
            >
              <CardContent className="pt-6 flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-medium">Manifest File</p>
                  <p className="text-xs text-muted-foreground break-all">{manifestFile}</p>
                </div>
                <a
                  href={apiAssetUrl(manifestFile)}
                  download
                  className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline"
                >
                  <Download className="h-4 w-4" /> Download
                </a>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
