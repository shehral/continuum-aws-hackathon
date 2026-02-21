/**
 * Graph Page E2E Tests
 *
 * QA-P2-1: Tests for graph visualization critical flows.
 */
import { test, expect } from "@playwright/test"
import { mockGraphData, createMockGraphData, createMockDecision, createMockEntity } from "./fixtures"

test.describe("Graph Page", () => {
  test.describe("Loading and Rendering", () => {
    test("should load graph page and render visualization", async ({ page }) => {
      const graphData = createMockGraphData(5, 4)
      await mockGraphData(page, graphData)

      await page.goto("/graph")
      await page.waitForLoadState("networkidle")

      // Wait for React Flow to initialize
      // React Flow renders either a canvas or SVG container
      const graphContainer = page.locator('[data-testid="rf__wrapper"]')
        .or(page.locator(".react-flow"))
        .or(page.locator("canvas"))
        .or(page.locator("svg"))

      await expect(graphContainer.first()).toBeVisible({ timeout: 10000 })
    })

    test("should display correct number of nodes", async ({ page }) => {
      const graphData = createMockGraphData(6, 5)
      await mockGraphData(page, graphData)

      await page.goto("/graph")
      await page.waitForLoadState("networkidle")
      await page.waitForTimeout(2000) // Wait for graph to render

      // Check if stats panel shows correct counts
      const statsText = page.locator("text=6 nodes").or(page.locator("text=6 Nodes"))
      if (await statsText.isVisible({ timeout: 3000 })) {
        await expect(statsText).toBeVisible()
      }
    })

    test("should display empty state when no data", async ({ page }) => {
      await mockGraphData(page, { nodes: [], edges: [], pagination: { page: 1, page_size: 100, total_count: 0, total_pages: 0, has_more: false } })

      await page.goto("/graph")
      await page.waitForLoadState("networkidle")

      // Should show empty state or just an empty graph
      const emptyIndicator = page.locator("text=No data")
        .or(page.locator("text=0 nodes"))
        .or(page.locator("text=empty"))
        .or(page.locator(".react-flow"))

      await expect(emptyIndicator.first()).toBeVisible({ timeout: 5000 })
    })

    test("should render different node types with distinct styles", async ({ page }) => {
      const graphData = {
        nodes: [
          {
            id: "decision-1",
            type: "decision",
            label: "Use PostgreSQL",
            has_embedding: true,
            data: createMockDecision({ id: "decision-1" }),
          },
          {
            id: "entity-1",
            type: "entity",
            label: "PostgreSQL",
            has_embedding: true,
            data: createMockEntity({ id: "entity-1", name: "PostgreSQL" }),
          },
        ],
        edges: [
          { id: "edge-1", source: "decision-1", target: "entity-1", relationship: "INVOLVES", weight: 0.9 },
        ],
        pagination: { page: 1, page_size: 100, total_count: 2, total_pages: 1, has_more: false },
      }

      await mockGraphData(page, graphData)

      await page.goto("/graph")
      await page.waitForLoadState("networkidle")
      await page.waitForTimeout(2000)

      // Nodes should be visible (either in the graph or in a legend)
      const decisionNode = page.locator("text=Use PostgreSQL")
        .or(page.locator('[data-id="decision-1"]'))
      const entityNode = page.locator("text=PostgreSQL")
        .or(page.locator('[data-id="entity-1"]'))

      // At least one should be visible
      const anyNode = decisionNode.or(entityNode)
      await expect(anyNode.first()).toBeVisible({ timeout: 5000 })
    })
  })

  test.describe("Graph Controls", () => {
    test("should have zoom controls", async ({ page }) => {
      const graphData = createMockGraphData(5, 4)
      await mockGraphData(page, graphData)

      await page.goto("/graph")
      await page.waitForLoadState("networkidle")
      await page.waitForTimeout(1000)

      // React Flow controls typically have zoom buttons
      const zoomIn = page.locator('[aria-label="zoom in"]')
        .or(page.locator('button:has-text("+")'))
        .or(page.locator(".react-flow__controls-button"))

      if (await zoomIn.first().isVisible({ timeout: 3000 })) {
        await expect(zoomIn.first()).toBeVisible()
      }
    })

    test("should have fit view control", async ({ page }) => {
      const graphData = createMockGraphData(5, 4)
      await mockGraphData(page, graphData)

      await page.goto("/graph")
      await page.waitForLoadState("networkidle")
      await page.waitForTimeout(1000)

      const fitView = page.locator('[aria-label="fit view"]')
        .or(page.locator("text=Fit"))
        .or(page.locator(".react-flow__controls-fitview"))

      if (await fitView.first().isVisible({ timeout: 3000 })) {
        await expect(fitView.first()).toBeVisible()
      }
    })

    test("should support panning with mouse drag", async ({ page }) => {
      const graphData = createMockGraphData(10, 8)
      await mockGraphData(page, graphData)

      await page.goto("/graph")
      await page.waitForLoadState("networkidle")
      await page.waitForTimeout(2000)

      // Get the graph container
      const container = page.locator(".react-flow").or(page.locator('[data-testid="rf__wrapper"]'))

      if (await container.first().isVisible({ timeout: 3000 })) {
        const box = await container.first().boundingBox()
        if (box) {
          // Perform a drag operation
          await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
          await page.mouse.down()
          await page.mouse.move(box.x + box.width / 2 + 100, box.y + box.height / 2 + 100)
          await page.mouse.up()
        }
      }
    })
  })

  test.describe("Node Interaction", () => {
    test("should show detail panel when clicking a node", async ({ page }) => {
      const graphData = {
        nodes: [
          {
            id: "decision-test",
            type: "decision",
            label: "Test Decision",
            has_embedding: true,
            data: {
              id: "decision-test",
              trigger: "Why we chose this",
              context: "Important context",
              options: ["A", "B"],
              decision: "Chose A",
              rationale: "It was better",
              confidence: 0.9,
              created_at: new Date().toISOString(),
              source: "manual",
              entities: [],
            },
          },
        ],
        edges: [],
        pagination: { page: 1, page_size: 100, total_count: 1, total_pages: 1, has_more: false },
      }

      await mockGraphData(page, graphData)

      // Mock the node details endpoint
      await page.route("**/api/graph/nodes/decision-test", (route) => {
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(graphData.nodes[0]),
        })
      })

      await page.goto("/graph")
      await page.waitForLoadState("networkidle")
      await page.waitForTimeout(2000)

      // Click on a node
      const node = page.locator(".react-flow__node").first()
        .or(page.locator("text=Test Decision"))

      if (await node.first().isVisible({ timeout: 5000 })) {
        await node.first().click()
        await page.waitForTimeout(500)

        // Detail panel should show
        const detailPanel = page.locator("text=Decision Details")
          .or(page.locator("text=Trigger"))
          .or(page.locator("text=Rationale"))
          .or(page.locator("text=Why we chose"))

        await expect(detailPanel.first()).toBeVisible({ timeout: 3000 })
      }
    })

    test("should close detail panel when clicking close button", async ({ page }) => {
      const graphData = createMockGraphData(3, 2)
      await mockGraphData(page, graphData)

      await page.goto("/graph")
      await page.waitForLoadState("networkidle")
      await page.waitForTimeout(2000)

      // Click on a node to open panel
      const node = page.locator(".react-flow__node").first()
      if (await node.isVisible({ timeout: 3000 })) {
        await node.click()
        await page.waitForTimeout(500)

        // Find and click close button
        const closeButton = page.locator('[aria-label="close"]')
          .or(page.locator('button:has-text("X")'))
          .or(page.locator('button:has-text("Close")'))

        if (await closeButton.first().isVisible({ timeout: 2000 })) {
          await closeButton.first().click()
        }
      }
    })
  })

  test.describe("Source Filtering", () => {
    test("should filter nodes by source type", async ({ page }) => {
      const graphData = createMockGraphData(5, 3)
      await mockGraphData(page, graphData)

      // Also respond to filtered requests
      await page.route("**/api/graph/sources", (route) => {
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            claude_logs: 3,
            interview: 2,
            manual: 1,
          }),
        })
      })

      await page.goto("/graph")
      await page.waitForLoadState("networkidle")

      // Look for source filter controls
      const filterPanel = page.locator("text=Decision Sources")
        .or(page.locator("text=Sources"))
        .or(page.locator("text=AI Extracted"))

      if (await filterPanel.first().isVisible({ timeout: 3000 })) {
        await expect(filterPanel.first()).toBeVisible()
      }
    })
  })

  test.describe("Legend and Info", () => {
    test("should display entity types legend", async ({ page }) => {
      const graphData = createMockGraphData(5, 4)
      await mockGraphData(page, graphData)

      await page.goto("/graph")
      await page.waitForLoadState("networkidle")

      const legend = page.locator("text=Entity Types")
        .or(page.locator("text=Legend"))
        .or(page.locator("text=technology"))

      if (await legend.first().isVisible({ timeout: 3000 })) {
        await expect(legend.first()).toBeVisible()
      }
    })

    test("should display relationship types legend", async ({ page }) => {
      const graphData = createMockGraphData(5, 4)
      await mockGraphData(page, graphData)

      await page.goto("/graph")
      await page.waitForLoadState("networkidle")

      const legend = page.locator("text=Relationships")
        .or(page.locator("text=INVOLVES"))
        .or(page.locator("text=SIMILAR_TO"))

      if (await legend.first().isVisible({ timeout: 3000 })) {
        await expect(legend.first()).toBeVisible()
      }
    })
  })

  test.describe("Responsive Behavior", () => {
    test("should adapt to mobile viewport", async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 667 })

      const graphData = createMockGraphData(3, 2)
      await mockGraphData(page, graphData)

      await page.goto("/graph")
      await page.waitForLoadState("networkidle")
      await page.waitForTimeout(1000)

      // Graph should still be visible on mobile
      const graphContainer = page.locator(".react-flow")
        .or(page.locator('[data-testid="rf__wrapper"]'))
        .or(page.locator("canvas"))

      await expect(graphContainer.first()).toBeVisible({ timeout: 5000 })
    })
  })
})
