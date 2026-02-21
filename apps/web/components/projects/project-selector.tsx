"use client"

import { useState } from "react"
import { Check, ChevronsUpDown, Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { cn } from "@/lib/utils"

interface ProjectSelectorProps {
  value: string | null
  onChange: (value: string | null) => void
  projects: string[]
  placeholder?: string
  className?: string
}

export function ProjectSelector({
  value,
  onChange,
  projects,
  placeholder = "Select project...",
  className,
}: ProjectSelectorProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState("")

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className={cn("w-full justify-between", className)}
        >
          <span className={cn("truncate", !value && "text-muted-foreground")}>
            {value || placeholder}
          </span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[300px] p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput
            placeholder="Search or create project..."
            value={search}
            onValueChange={setSearch}
          />
          <CommandList>
            <CommandEmpty>
              {search ? (
                <div className="py-6 text-center text-sm">
                  <p className="text-muted-foreground mb-3">No matching projects</p>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => {
                      onChange(search)
                      setOpen(false)
                      setSearch("")
                    }}
                    className="gap-2"
                  >
                    <Plus className="h-4 w-4" />
                    Create &ldquo;{search}&rdquo;
                  </Button>
                </div>
              ) : (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  Start typing to create a project
                </p>
              )}
            </CommandEmpty>
            <CommandGroup>
              {/* Show existing projects filtered by search */}
              {projects
                .filter((p) => p.toLowerCase().includes(search.toLowerCase()))
                .map((project) => (
                  <CommandItem
                    key={project}
                    value={project}
                    onSelect={() => {
                      onChange(project === value ? null : project)
                      setOpen(false)
                      setSearch("")
                    }}
                  >
                    <Check
                      className={cn(
                        "mr-2 h-4 w-4",
                        value === project ? "opacity-100" : "opacity-0"
                      )}
                    />
                    {project}
                  </CommandItem>
                ))}

              {/* Show "Create new" option if search doesn't match any existing project */}
              {search && !projects.some((p) => p.toLowerCase() === search.toLowerCase()) && (
                <CommandItem
                  value={search}
                  onSelect={() => {
                    onChange(search)
                    setOpen(false)
                    setSearch("")
                  }}
                  className="border-t"
                >
                  <Plus className="mr-2 h-4 w-4" />
                  <span>
                    Create &ldquo;<span className="font-medium">{search}</span>&rdquo;
                  </span>
                </CommandItem>
              )}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
