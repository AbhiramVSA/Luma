"use client"

import { useCallback, useMemo, useState } from "react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { AlertCircle, AudioLines, Download, Loader2, MicVocal, Wand2 } from "lucide-react"

interface SceneSegment {
  text: string
  pause_after_seconds: number
}

interface SceneSummary {
  scene_name: string
  segments: SceneSegment[]
  processed_audio_path: string
}

interface LongformScenesResult {
  scenes: SceneSummary[]
  final_audio_path: string
}

const EXAMPLE_MEDITATION = `शुरुआत
धीरे-धीरे अपनी आँखें बंद करें और एक गहरी सांस लें... (5 sec)
अब अपनी सांस छोड़ें और अपने कंधों को ढीला छोड़ दें।

जगह और पोज़शन
आप खुद को एक शांत जंगल में कल्पना करें। (10 sec)
हर ओर हरी-भरी प्रकृति और हल्की हवा चल रही है।

मुख्य यात्रा
अपने हृदय पर ध्यान केंद्रित करें और महसूस करें कि हर धड़कन प्रेम से भर रही है। (15 sec)
इस ऊर्जा को अपने पूरे अस्तित्व में फैलने दें।

समापन
धीरे-धीरे अपना ध्यान वापस कमरे में लाएं।
जब आप तैयार हों, अपनी आँखें खोलें और एक हल्की मुस्कान दें।`

function extractBoundary(contentType: string | null): string {
  if (!contentType) {
    return "longform-scenes-boundary"
  }
  const match = contentType.match(/boundary=([^;]+)/i)
  return match?.[1]?.trim() ?? "longform-scenes-boundary"
}

function parseMultipartMetadata(buffer: ArrayBuffer, boundary: string): LongformScenesResult {
  const decoder = new TextDecoder("utf-8")
  const text = decoder.decode(buffer)
  const boundaryToken = `--${boundary}`
  const rawParts = text
    .split(boundaryToken)
    .map((part) => part.trim())
    .filter((part) => part.length > 0 && part !== "--")

  const jsonPart = rawParts.find((part) => part.includes("Content-Type: application/json"))
  if (!jsonPart) {
    throw new Error("Missing JSON metadata in multipart response")
  }

  const [, body = ""] = jsonPart.split("\r\n\r\n")
  const cleaned = body.replace(/--$/, "").trim()
  if (!cleaned) {
    throw new Error("JSON metadata section was empty")
  }

  return JSON.parse(cleaned) as LongformScenesResult
}

export default function LongformScenesTester() {
  const [script, setScript] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [result, setResult] = useState<LongformScenesResult | null>(null)

  const sceneCount = useMemo(() => result?.scenes.length ?? 0, [result])
  const sentenceCount = useMemo(
    () => result?.scenes.reduce((total, scene) => total + scene.segments.length, 0) ?? 0,
    [result],
  )

  const handleUseExample = useCallback(() => {
    setScript(EXAMPLE_MEDITATION)
  }, [])

  const handleGenerate = useCallback(async () => {
    if (!script.trim()) {
      setError("Please paste a meditation script first.")
      return
    }

    setLoading(true)
    setError("")
    setResult(null)

    try {
      const response = await fetch("http://127.0.0.1:8002/api/v1/longform_scenes", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ script }),
      })

      if (!response.ok) {
        const errorText = await response.text()
        try {
          const parsed = JSON.parse(errorText)
          throw new Error(parsed.detail || "Failed to generate long-form audio")
        } catch {
          throw new Error(errorText || "Failed to generate long-form audio")
        }
      }

      const boundary = extractBoundary(response.headers.get("content-type"))
      const buffer = await response.arrayBuffer()
      const metadata = parseMultipartMetadata(buffer, boundary)
      setResult(metadata)
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unexpected error while generating audio"
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [script])

  return (
    <div className="space-y-6">
      <Card className="animate-fade-in-up">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <MicVocal className="h-5 w-5 text-primary" />
            Longform Scene Stitching
          </CardTitle>
          <CardDescription>
            Paste a multi-scene meditation script. The backend will generate scene audio, infer pauses, and stitch
            everything into a single track using the new longform endpoint.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium">Meditation Script</label>
            <Button variant="ghost" size="sm" className="text-xs h-7" onClick={handleUseExample}>
              <Wand2 className="mr-2 h-3 w-3" /> Use Example
            </Button>
          </div>
          <Textarea
            rows={16}
            className="font-mono text-sm min-h-[320px]"
            placeholder="Paste multi-scene meditation text here..."
            value={script}
            onChange={(event) => setScript(event.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            Scene headers should be on their own lines. Add optional pauses like (5 sec) directly after sentences to
            override the default 1.5 second break.
          </p>

          <Button className="w-full" size="lg" onClick={handleGenerate} disabled={loading || !script.trim()}>
            {loading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Generating stitched audio...
              </>
            ) : (
              <>
                <AudioLines className="mr-2 h-4 w-4" />
                Build Longform Audio
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      {error && (
        <Alert variant="destructive" className="animate-fade-in-up">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {result && (
        <div className="space-y-6 animate-fade-in-up">
          <Card className="hover-lift">
            <CardContent className="space-y-4 pt-6">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm font-medium">Stitched Master Audio</p>
                  <p className="text-xs text-muted-foreground">
                    {sceneCount} scenes · {sentenceCount} sentences
                  </p>
                </div>
                <Badge variant="outline">{sceneCount} scene{sceneCount === 1 ? "" : "s"}</Badge>
              </div>
              <audio controls src={result.final_audio_path} className="w-full" />
              <a
                href={result.final_audio_path}
                download="longform-meditation.mp3"
                className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline"
              >
                <Download className="h-4 w-4" /> Download Master Track
              </a>
            </CardContent>
          </Card>

          <div className="space-y-4">
            <h3 className="text-lg font-semibold">Scenes</h3>
            <div className="grid gap-4 md:grid-cols-2">
              {result.scenes.map((scene, index) => (
                <Card
                  key={`${scene.scene_name}-${index}`}
                  className="hover:border-primary/50 hover-lift animate-fade-in-up"
                  style={{ animationDelay: `${index * 40}ms` }}
                >
                  <CardContent className="space-y-4 pt-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium">{scene.scene_name}</p>
                        <p className="text-xs text-muted-foreground">
                          {scene.segments.length} segment{scene.segments.length === 1 ? "" : "s"}
                        </p>
                      </div>
                      <Badge variant="secondary">Scene {index + 1}</Badge>
                    </div>
                    <audio controls src={scene.processed_audio_path} className="w-full" />
                    <div className="space-y-2 rounded-lg bg-muted/40 p-3 text-xs text-muted-foreground">
                      {scene.segments.map((segment, segmentIndex) => (
                        <div key={`${scene.scene_name}-${segmentIndex}`} className="space-y-1">
                          <p className="font-medium text-foreground/90">
                            Sentence {segmentIndex + 1} · pause {segment.pause_after_seconds.toFixed(1)}s
                          </p>
                          <p className="whitespace-pre-wrap">{segment.text}</p>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
