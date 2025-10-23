"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Loader2, RefreshCw, Trash2, Download, Database } from "lucide-react"

interface AudioFileEntry {
  file_name: string
  relative_path: string
  size_bytes: number
  size_readable: string
  modified_at: string
  download_url: string
}

interface AudioFileResponse {
  count: number
  files: AudioFileEntry[]
  manifest_present: boolean
  asset_cache_present: boolean
}

const API_BASE = "http://127.0.0.1:8002/api/v1/elevenlabs"

export function AudioLibrary() {
  const [files, setFiles] = useState<AudioFileEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [clearing, setClearing] = useState(false)
  const [metadata, setMetadata] = useState({ manifest: false, cache: false })

  const fetchAudioFiles = useCallback(async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await fetch(`${API_BASE}/audio-files`)
      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`)
      }

      const payload: AudioFileResponse = await response.json()
      setFiles(payload.files || [])
      setMetadata({ manifest: payload.manifest_present, cache: payload.asset_cache_present })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load audio files")
    } finally {
      setLoading(false)
    }
  }, [])

  const handleClear = useCallback(async () => {
    if (clearing) return
    if (!window.confirm("Remove all locally cached audio files?")) return

    setClearing(true)
    setError(null)

    try {
      const response = await fetch(`${API_BASE}/audio-files`, { method: "DELETE" })
      if (!response.ok) {
        const detail = await response.json().catch(() => null)
        throw new Error(detail?.detail || `Failed with status ${response.status}`)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to clear audio files")
    } finally {
      setClearing(false)
      fetchAudioFiles()
    }
  }, [clearing, fetchAudioFiles])

  useEffect(() => {
    fetchAudioFiles()
  }, [fetchAudioFiles])

  const totalSize = useMemo(() => {
    const bytes = files.reduce((sum, file) => sum + (file.size_bytes || 0), 0)
    if (!bytes) return "0 B"

    const units = ["B", "KB", "MB", "GB", "TB"]
    let size = bytes
    let unitIndex = 0

    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024
      unitIndex += 1
    }

    const formatted = unitIndex === 0 ? `${size} ${units[unitIndex]}` : `${size.toFixed(1)} ${units[unitIndex]}`
    return formatted
  }, [files])

  const lastUpdatedLabel = useMemo(() => {
    if (!files.length) return ""
    const timestamps = files.map((file) => new Date(file.modified_at).getTime())
    const mostRecent = Math.max(...timestamps)
    return new Date(mostRecent).toLocaleString()
  }, [files])

  return (
    <Card className="animate-soft-scale">
      <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <CardTitle>Audio Library</CardTitle>
          <CardDescription>Inspect and manage locally generated audio clips</CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={fetchAudioFiles}
            disabled={loading || clearing}
            className="hover-lift"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={handleClear}
            disabled={loading || clearing}
            className="hover-lift"
          >
            {clearing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {(loading || error) && (
          <div className="space-y-3">
            {loading && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Loading audio files...</span>
              </div>
            )}
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </div>
        )}

        {!loading && !error && (
          <div className="space-y-6">
            <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              <Badge variant="secondary" className="flex items-center gap-1">
                <Database className="h-3 w-3" />
                {files.length} file{files.length === 1 ? "" : "s"}
              </Badge>
              <span>Total size: {totalSize}</span>
              {lastUpdatedLabel && <span>Last updated: {lastUpdatedLabel}</span>}
              {metadata.manifest && <Badge variant="outline">scene_audio_map.json</Badge>}
              {metadata.cache && <Badge variant="outline">heygen_assets.json</Badge>}
            </div>

            {files.length === 0 ? (
              <p className="text-sm text-muted-foreground">No audio files found in the local cache.</p>
            ) : (
              <div className="space-y-3">
                {files.map((file, index) => (
                  <div
                    key={file.file_name}
                    className="flex flex-col gap-3 rounded-lg border border-border bg-card/60 p-4 shadow-sm transition-all sm:flex-row sm:items-center sm:justify-between animate-fade-in-up hover-lift"
                    style={{ animationDelay: `${index * 0.04}s` }}
                  >
                    <div className="space-y-1">
                      <p className="font-mono text-sm font-semibold text-foreground">{file.file_name}</p>
                      <p className="text-xs text-muted-foreground">
                        {file.size_readable} • Modified {new Date(file.modified_at).toLocaleString()}
                      </p>
                      <p className="text-xs text-muted-foreground break-all">{file.relative_path}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <a
                        href={`http://127.0.0.1:8002${file.download_url}`}
                        download
                        className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-xs font-medium text-primary transition-colors hover:bg-primary/10 hover-lift"
                      >
                        <Download className="h-4 w-4" />
                        Download
                      </a>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
