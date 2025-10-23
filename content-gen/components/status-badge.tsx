"use client"
import { Badge } from "@/components/ui/badge"
import type React from "react"

import { CheckCircle2, Clock, AlertCircle, Loader2 } from "lucide-react"

interface StatusBadgeProps {
  status: string
  variant?: "default" | "secondary" | "outline" | "destructive"
  showIcon?: boolean
}

const statusConfig: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
  // Audio/Video statuses
  completed: {
    color: "bg-green-500/10 text-green-600 border-green-500/50",
    icon: <CheckCircle2 className="h-3 w-3" />,
    label: "Completed",
  },
  processing: {
    color: "bg-blue-500/10 text-blue-600 border-blue-500/50",
    icon: <Loader2 className="h-3 w-3 animate-spin" />,
    label: "Processing",
  },
  submitted: {
    color: "bg-yellow-500/10 text-yellow-600 border-yellow-500/50",
    icon: <Clock className="h-3 w-3" />,
    label: "Submitted",
  },
  failed: {
    color: "bg-red-500/10 text-red-600 border-red-500/50",
    icon: <AlertCircle className="h-3 w-3" />,
    label: "Failed",
  },
  // Image-to-video statuses
  COMPLETED: {
    color: "bg-green-500/10 text-green-600 border-green-500/50",
    icon: <CheckCircle2 className="h-3 w-3" />,
    label: "Completed",
  },
  IN_PROGRESS: {
    color: "bg-blue-500/10 text-blue-600 border-blue-500/50",
    icon: <Loader2 className="h-3 w-3 animate-spin" />,
    label: "In Progress",
  },
  CREATED: {
    color: "bg-yellow-500/10 text-yellow-600 border-yellow-500/50",
    icon: <Clock className="h-3 w-3" />,
    label: "Created",
  },
  FAILED: {
    color: "bg-red-500/10 text-red-600 border-red-500/50",
    icon: <AlertCircle className="h-3 w-3" />,
    label: "Failed",
  },
  // Overall statuses
  success: {
    color: "bg-green-500/10 text-green-600 border-green-500/50",
    icon: <CheckCircle2 className="h-3 w-3" />,
    label: "Success",
  },
  partial: {
    color: "bg-yellow-500/10 text-yellow-600 border-yellow-500/50",
    icon: <AlertCircle className="h-3 w-3" />,
    label: "Partial",
  },
}

export function StatusBadge({ status, showIcon = true }: StatusBadgeProps) {
  const config = statusConfig[status] || {
    color: "bg-gray-500/10 text-gray-600 border-gray-500/50",
    icon: <Clock className="h-3 w-3" />,
    label: status,
  }

  return (
    <Badge className={`${config.color} border`}>
      {showIcon && <span className="mr-1">{config.icon}</span>}
      {config.label}
    </Badge>
  )
}
