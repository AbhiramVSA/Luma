"use client"
import { useEffect, useState, useDeferredValue, useMemo, useCallback } from "react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Loader2, Download, AlertCircle, CheckCircle2, Copy, Music, Trash2 } from "lucide-react"

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

const AUDIO_STORAGE_KEY = "ib-audio-generation-state"

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
      const stored = window.localStorage.getItem(AUDIO_STORAGE_KEY)
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

    if (audioOutputs.length === 0) {
      window.localStorage.removeItem(AUDIO_STORAGE_KEY)
      return
    }

    const payload = {
      outputs: audioOutputs,
      manifestFile,
    }

    window.localStorage.setItem(AUDIO_STORAGE_KEY, JSON.stringify(payload))
  }, [audioOutputs, manifestFile])

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

  return (
    <div className="space-y-6">
      {/* Input Section */}
      <Card>
        <CardHeader>
          <CardTitle>Generate Audio Dialogue</CardTitle>
          <CardDescription>Enter a multi-scene script to generate AI voice dialogues using ElevenLabs</CardDescription>
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
              Format: Scene descriptions followed by character dialogues. Each scene will generate separate audio files.
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
            Audio generated successfully! {audioOutputs.length} scene(s) created.
          </AlertDescription>
        </Alert>
      )}

      {/* Results Section */}
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

                    {/* Audio Player */}
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
    </div>
  )
}
