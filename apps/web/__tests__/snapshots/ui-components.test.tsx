/**
 * Snapshot Tests for UI Components
 *
 * QA-P2-3: Tests that UI components render consistently.
 * Helps catch unintended UI changes during refactoring.
 */
import { describe, it, expect, vi } from "vitest"
import { render } from "../utils/test-utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"

// Mock window.matchMedia for components that use it
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

describe("Badge Component Snapshots", () => {
  it("renders default badge", () => {
    const { container } = render(<Badge>Default Badge</Badge>)
    expect(container).toMatchSnapshot()
  })

  it("renders outline badge", () => {
    const { container } = render(<Badge variant="outline">Outline Badge</Badge>)
    expect(container).toMatchSnapshot()
  })

  it("renders secondary badge", () => {
    const { container } = render(<Badge variant="secondary">Secondary Badge</Badge>)
    expect(container).toMatchSnapshot()
  })

  it("renders destructive badge", () => {
    const { container } = render(<Badge variant="destructive">Destructive Badge</Badge>)
    expect(container).toMatchSnapshot()
  })

  it("renders badge with custom className", () => {
    const { container } = render(
      <Badge className="bg-cyan-500 text-white">Custom Badge</Badge>
    )
    expect(container).toMatchSnapshot()
  })
})

describe("Button Component Snapshots", () => {
  it("renders default button", () => {
    const { container } = render(<Button>Click Me</Button>)
    expect(container).toMatchSnapshot()
  })

  it("renders outline button", () => {
    const { container } = render(<Button variant="outline">Outline</Button>)
    expect(container).toMatchSnapshot()
  })

  it("renders ghost button", () => {
    const { container } = render(<Button variant="ghost">Ghost</Button>)
    expect(container).toMatchSnapshot()
  })

  it("renders link button", () => {
    const { container } = render(<Button variant="link">Link</Button>)
    expect(container).toMatchSnapshot()
  })

  it("renders small button", () => {
    const { container } = render(<Button size="sm">Small</Button>)
    expect(container).toMatchSnapshot()
  })

  it("renders large button", () => {
    const { container } = render(<Button size="lg">Large</Button>)
    expect(container).toMatchSnapshot()
  })

  it("renders icon button", () => {
    const { container } = render(<Button size="icon">+</Button>)
    expect(container).toMatchSnapshot()
  })

  it("renders disabled button", () => {
    const { container } = render(<Button disabled>Disabled</Button>)
    expect(container).toMatchSnapshot()
  })

  it("renders button as child (asChild)", () => {
    const { container } = render(
      <Button asChild>
        <a href="/test">Link Button</a>
      </Button>
    )
    expect(container).toMatchSnapshot()
  })
})

describe("Card Component Snapshots", () => {
  it("renders basic card", () => {
    const { container } = render(
      <Card>
        <CardContent>Card Content</CardContent>
      </Card>
    )
    expect(container).toMatchSnapshot()
  })

  it("renders card with header", () => {
    const { container } = render(
      <Card>
        <CardHeader>
          <CardTitle>Card Title</CardTitle>
        </CardHeader>
        <CardContent>Card Content</CardContent>
      </Card>
    )
    expect(container).toMatchSnapshot()
  })

  it("renders card with full header", () => {
    const { container } = render(
      <Card>
        <CardHeader>
          <CardTitle>Card Title</CardTitle>
          <CardDescription>This is a description of the card.</CardDescription>
        </CardHeader>
        <CardContent>Card Content</CardContent>
      </Card>
    )
    expect(container).toMatchSnapshot()
  })

  it("renders styled card", () => {
    const { container } = render(
      <Card className="bg-white/[0.03] backdrop-blur-xl border-white/[0.06]">
        <CardHeader>
          <CardTitle className="text-slate-100">Styled Title</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-slate-400">Styled content</p>
        </CardContent>
      </Card>
    )
    expect(container).toMatchSnapshot()
  })
})
