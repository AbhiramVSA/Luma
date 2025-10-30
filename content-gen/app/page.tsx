"use client"
import { useState } from "react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import AudioGeneration from "@/components/audio-generation"
import VideoGeneration from "@/components/video-generation"
import ImageToVideo from "@/components/image-to-video"
import CreatomateRender from "@/components/creatomate-render"
import { AudioLibrary } from "@/components/audio-library"
import { ApiConfig } from "@/components/api-config"
import { Music, Play, ImageIcon, Folder, Clapperboard } from "lucide-react"

export default function Home() {
  const [activeTab, setActiveTab] = useState("audio")

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-background/95">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container mx-auto px-4 py-4 sm:px-6 lg:px-8 animate-fade-in-up">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-primary/80 text-primary-foreground font-bold shadow-lg">
                IB
              </div>
              <div>
                <h1 className="text-xl font-bold text-foreground">InnerBhakti</h1>
                <p className="text-xs text-muted-foreground">Video Generation Studio</p>
              </div>
            </div>
            <div className="hidden sm:block text-sm text-muted-foreground">
              <p className="font-mono text-xs">API: http://127.0.0.1:8002/api/v1</p>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-8 sm:px-6 lg:px-8 animate-fade-in-up">
        <div className="grid gap-8 lg:grid-cols-4">
          {/* Sidebar */}
          <aside className="lg:col-span-1">
            <div className="sticky top-24 space-y-4">
              <ApiConfig />

              {/* Quick Info */}
              <div className="rounded-lg border border-border bg-card p-4 space-y-3 animate-soft-scale hover-lift">
                <h3 className="text-sm font-semibold">Quick Start</h3>
                <ul className="space-y-2 text-xs text-muted-foreground">
                  <li className="flex gap-2">
                    <span className="text-primary font-bold">1.</span>
                    <span>Generate audio from your script</span>
                  </li>
                  <li className="flex gap-2">
                    <span className="text-primary font-bold">2.</span>
                    <span>Create talking-head videos with HeyGen</span>
                  </li>
                  <li className="flex gap-2">
                    <span className="text-primary font-bold">3.</span>
                    <span>Experiment with image-to-video (optional)</span>
                  </li>
                  <li className="flex gap-2">
                    <span className="text-primary font-bold">4.</span>
                    <span>Render the final Creatomate project</span>
                  </li>
                </ul>
              </div>

              {/* Features List */}
              <div className="rounded-lg border border-border bg-card p-4 space-y-3 animate-soft-scale hover-lift">
                <h3 className="text-sm font-semibold">Features</h3>
                <ul className="space-y-2 text-xs text-muted-foreground">
                  <li className="flex items-center gap-2">
                    <Music className="h-3 w-3 text-primary" />
                    <span>ElevenLabs Audio</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <Play className="h-3 w-3 text-primary" />
                    <span>HeyGen Videos</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <ImageIcon className="h-3 w-3 text-primary" />
                    <span>Kling AI Videos</span>
                  </li>
                  <li className="flex items-center gap-2">
                    <Clapperboard className="h-3 w-3 text-primary" />
                    <span>Creatomate Automation</span>
                  </li>
                </ul>
              </div>
            </div>
          </aside>

          {/* Main Content */}
          <div className="lg:col-span-3">
            <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
              <TabsList className="grid w-full grid-cols-5 mb-8 rounded-2xl bg-muted/40 p-1">
                <TabsTrigger value="audio" className="flex items-center gap-2 transition-all data-[state=active]:bg-background data-[state=active]:shadow-sm">
                  <Music className="h-4 w-4" />
                  <span className="hidden sm:inline">Audio</span>
                </TabsTrigger>
                <TabsTrigger value="video" className="flex items-center gap-2 transition-all data-[state=active]:bg-background data-[state=active]:shadow-sm">
                  <Play className="h-4 w-4" />
                  <span className="hidden sm:inline">Video</span>
                </TabsTrigger>
                <TabsTrigger value="image-video" className="flex items-center gap-2 transition-all data-[state=active]:bg-background data-[state=active]:shadow-sm">
                  <ImageIcon className="h-4 w-4" />
                  <span className="hidden sm:inline">Image</span>
                </TabsTrigger>
                <TabsTrigger value="creatomate" className="flex items-center gap-2 transition-all data-[state=active]:bg-background data-[state=active]:shadow-sm">
                  <Clapperboard className="h-4 w-4" />
                  <span className="hidden sm:inline">Creatomate</span>
                </TabsTrigger>
                <TabsTrigger value="library" className="flex items-center gap-2 transition-all data-[state=active]:bg-background data-[state=active]:shadow-sm">
                  <Folder className="h-4 w-4" />
                  <span className="hidden sm:inline">Library</span>
                </TabsTrigger>
              </TabsList>

              {/* Audio Generation Tab */}
              <TabsContent value="audio" className="space-y-4 animate-fade-in-up" data-testid="tab-audio">
                <AudioGeneration />
              </TabsContent>

              {/* Video Generation Tab */}
              <TabsContent value="video" className="space-y-4 animate-fade-in-up" data-testid="tab-video">
                <VideoGeneration />
              </TabsContent>

              {/* Image-to-Video Tab */}
              <TabsContent value="image-video" className="space-y-4 animate-fade-in-up" data-testid="tab-image">
                <ImageToVideo />
              </TabsContent>

              {/* Creatomate Tab */}
              <TabsContent value="creatomate" className="space-y-4 animate-fade-in-up" data-testid="tab-creatomate">
                <CreatomateRender />
              </TabsContent>

              {/* Audio Library Tab */}
              <TabsContent value="library" className="space-y-4 animate-fade-in-up" data-testid="tab-library">
                <AudioLibrary />
              </TabsContent>
            </Tabs>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-border bg-background/50 py-8 mt-16">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col items-center justify-between gap-4 sm:flex-row text-sm text-muted-foreground">
            <p>InnerBhakti Video Generation Studio</p>
            <p className="text-xs">Powered by ElevenLabs, HeyGen, and Freepik Kling AI</p>
          </div>
        </div>
      </footer>
    </div>
  )
}
