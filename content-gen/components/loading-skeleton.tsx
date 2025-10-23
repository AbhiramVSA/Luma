"use client"
import { Card, CardContent, CardHeader } from "@/components/ui/card"

export function AudioCardSkeleton() {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="space-y-3 animate-pulse">
          <div className="h-4 bg-muted rounded w-1/3" />
          <div className="h-3 bg-muted rounded w-full" />
          <div className="h-8 bg-muted rounded" />
        </div>
      </CardContent>
    </Card>
  )
}

export function VideoCardSkeleton() {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="space-y-4 animate-pulse">
          <div className="h-4 bg-muted rounded w-1/3" />
          <div className="h-32 bg-muted rounded" />
          <div className="h-8 bg-muted rounded" />
        </div>
      </CardContent>
    </Card>
  )
}

export function FormSkeleton() {
  return (
    <Card>
      <CardHeader>
        <div className="h-6 bg-muted rounded w-1/3 mb-2 animate-pulse" />
        <div className="h-4 bg-muted rounded w-2/3 animate-pulse" />
      </CardHeader>
      <CardContent>
        <div className="space-y-4 animate-pulse">
          <div className="h-32 bg-muted rounded" />
          <div className="h-10 bg-muted rounded" />
        </div>
      </CardContent>
    </Card>
  )
}
