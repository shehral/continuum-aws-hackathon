"use client"

import { useState, useMemo } from "react"
import { CheckSquare, Square, Search, FolderOpen, FileText, ChevronDown, ChevronRight } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

interface FileInfo {
  file_path: string
  project_name: string
  project_dir: string
  conversation_count: number
  size_bytes: number
  last_modified: string
}

interface FileBrowserProps {
  files: FileInfo[]
  selectedFiles: string[]
  onSelectionChange: (selected: string[]) => void
  className?: string
}

export function FileBrowser({
  files,
  selectedFiles,
  onSelectionChange,
  className,
}: FileBrowserProps) {
  const [search, setSearch] = useState("")
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(new Set())

  // Group files by project
  const filesByProject = useMemo(() => {
    const grouped = new Map<string, FileInfo[]>()

    files.forEach((file) => {
      const project = file.project_name || "unknown"
      if (!grouped.has(project)) {
        grouped.set(project, [])
      }
      grouped.get(project)!.push(file)
    })

    // Sort files within each project by last modified (newest first)
    grouped.forEach((projectFiles) => {
      projectFiles.sort((a, b) =>
        new Date(b.last_modified).getTime() - new Date(a.last_modified).getTime()
      )
    })

    return grouped
  }, [files])

  // Filter files by search
  const filteredProjects = useMemo(() => {
    if (!search) return filesByProject

    const filtered = new Map<string, FileInfo[]>()

    filesByProject.forEach((projectFiles, projectName) => {
      const matchingFiles = projectFiles.filter((file) => {
        const searchLower = search.toLowerCase()
        return (
          file.project_name.toLowerCase().includes(searchLower) ||
          file.file_path.toLowerCase().includes(searchLower)
        )
      })

      if (matchingFiles.length > 0) {
        filtered.set(projectName, matchingFiles)
      }
    })

    return filtered
  }, [filesByProject, search])

  const toggleProject = (project: string) => {
    const newExpanded = new Set(expandedProjects)
    if (newExpanded.has(project)) {
      newExpanded.delete(project)
    } else {
      newExpanded.add(project)
    }
    setExpandedProjects(newExpanded)
  }

  const toggleFile = (filePath: string) => {
    const newSelected = selectedFiles.includes(filePath)
      ? selectedFiles.filter((f) => f !== filePath)
      : [...selectedFiles, filePath]
    onSelectionChange(newSelected)
  }

  const toggleProjectFiles = (projectFiles: FileInfo[]) => {
    const projectFilePaths = projectFiles.map((f: FileInfo) => f.file_path)
    const allSelected = projectFilePaths.every((fp: string) => selectedFiles.includes(fp))

    if (allSelected) {
      // Deselect all project files
      onSelectionChange(selectedFiles.filter((f: string) => !projectFilePaths.includes(f)))
    } else {
      // Select all project files
      const uniqueSet = new Set([...selectedFiles, ...projectFilePaths])
      const newSelected = Array.from(uniqueSet)
      onSelectionChange(newSelected)
    }
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const formatDate = (isoDate: string) => {
    const date = new Date(isoDate)
    const now = new Date()
    const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24))

    if (diffDays === 0) return "Today"
    if (diffDays === 1) return "Yesterday"
    if (diffDays < 7) return `${diffDays}d ago`
    if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`
    return date.toLocaleDateString()
  }

  const selectAll = () => {
    onSelectionChange(files.map((file: FileInfo) => file.file_path))
  }

  const deselectAll = () => {
    onSelectionChange([])
  }

  const allSelected = files.length > 0 && selectedFiles.length === files.length

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {/* Search and Controls */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <Input
            placeholder="Search files..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9 bg-white/[0.05] border-white/10"
          />
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={allSelected ? deselectAll : selectAll}
          className="bg-white/[0.05] border-white/10"
        >
          {allSelected ? (
            <>
              <Square className="h-4 w-4 mr-2" />
              Deselect All
            </>
          ) : (
            <>
              <CheckSquare className="h-4 w-4 mr-2" />
              Select All
            </>
          )}
        </Button>
      </div>

      {/* File Tree */}
      <ScrollArea className="h-[400px] rounded-lg border border-white/10 bg-white/[0.03]">
        <div className="p-2">
          {filteredProjects.size === 0 ? (
            <div className="text-center py-8 text-slate-400">
              {search ? "No files match your search" : "No files available"}
            </div>
          ) : (
            Array.from(filteredProjects.entries()).map(([projectName, projectFiles]) => {
              const isExpanded = expandedProjects.has(projectName)
              const projectFilePaths = projectFiles.map((f: FileInfo) => f.file_path)
              const allProjectFilesSelected = projectFilePaths.every((fp: string) =>
                selectedFiles.includes(fp)
              )
              const someProjectFilesSelected = projectFilePaths.some((fp: string) =>
                selectedFiles.includes(fp)
              ) && !allProjectFilesSelected

              return (
                <div key={projectName} className="mb-2">
                  {/* Project Header */}
                  <div
                    className="flex items-center gap-2 p-2 rounded-lg hover:bg-white/[0.05] cursor-pointer group"
                    onClick={() => toggleProject(projectName)}
                  >
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0"
                      onClick={(e) => {
                        e.stopPropagation()
                        toggleProjectFiles(projectFiles)
                      }}
                    >
                      {allProjectFilesSelected ? (
                        <CheckSquare className="h-4 w-4 text-cyan-400" />
                      ) : someProjectFilesSelected ? (
                        <Square className="h-4 w-4 text-cyan-400 fill-cyan-400/30" />
                      ) : (
                        <Square className="h-4 w-4 text-slate-500" />
                      )}
                    </Button>
                    {isExpanded ? (
                      <ChevronDown className="h-4 w-4 text-slate-400" />
                    ) : (
                      <ChevronRight className="h-4 w-4 text-slate-400" />
                    )}
                    <FolderOpen className="h-4 w-4 text-cyan-400" />
                    <span className="text-sm font-medium text-slate-200 flex-1">
                      {projectName}
                    </span>
                    <Badge variant="outline" className="text-xs">
                      {projectFiles.length} file{projectFiles.length !== 1 ? "s" : ""}
                    </Badge>
                  </div>

                  {/* Project Files */}
                  {isExpanded && (
                    <div className="ml-6 mt-1 space-y-1">
                      {projectFiles.map((file) => {
                        const isSelected = selectedFiles.includes(file.file_path)
                        const fileName = file.file_path.split("/").pop() || file.file_path

                        return (
                          <div
                            key={file.file_path}
                            className={cn(
                              "flex items-center gap-2 p-2 rounded-lg hover:bg-white/[0.05] cursor-pointer group",
                              isSelected && "bg-cyan-500/10"
                            )}
                            onClick={() => toggleFile(file.file_path)}
                          >
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-6 w-6 p-0"
                              onClick={(e) => {
                                e.stopPropagation()
                                toggleFile(file.file_path)
                              }}
                            >
                              {isSelected ? (
                                <CheckSquare className="h-4 w-4 text-cyan-400" />
                              ) : (
                                <Square className="h-4 w-4 text-slate-500 group-hover:text-slate-400" />
                              )}
                            </Button>
                            <FileText className="h-4 w-4 text-slate-400" />
                            <span className="text-sm text-slate-300 flex-1 truncate">
                              {fileName}
                            </span>
                            <div className="flex items-center gap-2 text-xs text-slate-500">
                              <span>{file.conversation_count} conv</span>
                              <span>•</span>
                              <span>{formatFileSize(file.size_bytes)}</span>
                              <span>•</span>
                              <span>{formatDate(file.last_modified)}</span>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })
          )}
        </div>
      </ScrollArea>

      {/* Selection Summary */}
      {selectedFiles.length > 0 && (
        <div className="text-sm text-slate-400">
          {selectedFiles.length} file{selectedFiles.length !== 1 ? "s" : ""} selected
        </div>
      )}
    </div>
  )
}
