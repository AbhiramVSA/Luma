"use client"
import { Card, CardContent } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"

interface ProgressTrackerProps {
  total: number
  completed: number
  processing: number
  failed: number
  showPercentage?: boolean
}

export function ProgressTracker({ total, completed, processing, failed, showPercentage = true }: ProgressTrackerProps) {
  const percentage = total > 0 ? (completed / total) * 100 : 0

  return (
    <Card className="bg-muted/50">
      <CardContent className="pt-6">
        <div className="space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">Progress</span>
            {showPercentage && <span className="font-mono text-xs">{Math.round(percentage)}%</span>}
            <span className="font-mono text-xs">
              {completed}/{total}
            </span>
          </div>
          <Progress value={percentage} className="h-2" />
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div className="flex items-center gap-1">
              <div className="h-2 w-2 rounded-full bg-green-500" />
              <span>{completed} completed</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="h-2 w-2 rounded-full bg-blue-500" />
              <span>{processing} processing</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="h-2 w-2 rounded-full bg-red-500" />
              <span>{failed} failed</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
