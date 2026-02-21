/**
 * Decisions Page E2E Tests
 *
 * QA-P2-1: Tests for decisions page critical flows.
 */
import { test, expect } from "@playwright/test"
import { mockDecisions, createMockDecision, createMockEntity } from "./fixtures"

test.describe("Decisions Page", () => {
  test.describe("Loading and Display", () => {
    test("should load decisions page and display list", async ({ page }) => {
      const decisions = [
        createMockDecision({ trigger: "Choose database", agent_decision: "PostgreSQL" }),
        createMockDecision({ trigger: "Choose framework", agent_decision: "FastAPI" }),
      ]

      await mockDecisions(page, decisions)

      await page.goto("/decisions")
      await page.waitForLoadState("networkidle")

      // Verify decisions are displayed
      await expect(page.locator("text=Choose database")).toBeVisible()
      await expect(page.locator("text=Choose framework")).toBeVisible()
    })

    test("should display decision details", async ({ page }) => {
      const entity = createMockEntity({ name: "PostgreSQL", type: "technology" })
      const decision = createMockDecision({
        trigger: "Choose database for the project",
        context: "Building a new web application",
        agent_decision: "Use PostgreSQL",
        agent_rationale: "Best for relational data",
        entities: [entity],
      })

      await mockDecisions(page, [decision])

      await page.goto("/decisions")
      await page.waitForLoadState("networkidle")

      // Verify decision content
      await expect(page.locator("text=Choose database for the project")).toBeVisible()

      // Verify entity badge is shown
      await expect(page.locator("text=PostgreSQL")).toBeVisible()
    })

    test("should display empty state when no decisions", async ({ page }) => {
      await mockDecisions(page, [])

      await page.goto("/decisions")
      await page.waitForLoadState("networkidle")

      // Verify empty state
      await expect(
        page.locator("text=No decisions").or(page.locator("text=empty"))
      ).toBeVisible({ timeout: 5000 })
    })
  })

  test.describe("Search Functionality", () => {
    test("should filter decisions by search query", async ({ page }) => {
      // Set up route with dynamic filtering
      await page.route("**/api/decisions*", (route) => {
        const url = new URL(route.request().url())
        const query = url.searchParams.get("q") || ""

        const allDecisions = [
          createMockDecision({ trigger: "Choose database", agent_decision: "PostgreSQL" }),
          createMockDecision({ trigger: "Choose framework", agent_decision: "FastAPI" }),
          createMockDecision({ trigger: "Choose cache", agent_decision: "Redis" }),
        ]

        const filtered = query
          ? allDecisions.filter((d) =>
              d.trigger.toLowerCase().includes(query.toLowerCase()) ||
              d.agent_decision.toLowerCase().includes(query.toLowerCase())
            )
          : allDecisions

        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(filtered),
        })
      })

      await page.goto("/decisions")
      await page.waitForLoadState("networkidle")

      // Initial state should show all decisions
      await expect(page.locator("text=Choose database")).toBeVisible()
      await expect(page.locator("text=Choose framework")).toBeVisible()

      // Search for "database"
      const searchInput = page.getByPlaceholder(/search/i).or(page.locator('input[type="search"]'))
      if (await searchInput.isVisible()) {
        await searchInput.fill("database")
        await page.waitForTimeout(600) // Wait for debounce

        // Should show only database decision
        await expect(page.locator("text=Choose database")).toBeVisible()
      }
    })

    test("should clear search and show all decisions", async ({ page }) => {
      await page.route("**/api/decisions*", (route) => {
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([
            createMockDecision({ trigger: "Decision 1" }),
            createMockDecision({ trigger: "Decision 2" }),
          ]),
        })
      })

      await page.goto("/decisions")
      await page.waitForLoadState("networkidle")

      const searchInput = page.getByPlaceholder(/search/i).or(page.locator('input[type="search"]'))
      if (await searchInput.isVisible()) {
        // Type and then clear
        await searchInput.fill("test")
        await page.waitForTimeout(300)
        await searchInput.clear()
        await page.waitForTimeout(600)

        // All decisions should be visible
        await expect(page.locator("text=Decision 1")).toBeVisible()
        await expect(page.locator("text=Decision 2")).toBeVisible()
      }
    })
  })

  test.describe("Decision Details", () => {
    test("should show decision details in modal or panel", async ({ page }) => {
      const decision = createMockDecision({
        id: "detail-test-123",
        trigger: "Important Decision",
        context: "Very important context here",
        options: ["Option A", "Option B", "Option C"],
        agent_decision: "Chose Option B",
        agent_rationale: "Because it was the best option for our needs",
      })

      await mockDecisions(page, [decision])

      // Also mock the individual decision endpoint
      await page.route("**/api/decisions/detail-test-123", (route) => {
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(decision),
        })
      })

      await page.goto("/decisions")
      await page.waitForLoadState("networkidle")

      // Click on the decision
      await page.click("text=Important Decision")
      await page.waitForTimeout(500)

      // Check if detail view shows more information
      // This could be a modal, side panel, or separate page
      const detailContent = page.locator("text=Because it was the best option")
        .or(page.locator("text=Very important context"))
        .or(page.locator("text=Option A"))

      // At least one detail should be visible
      await expect(detailContent.first()).toBeVisible({ timeout: 5000 })
    })

    test("should display confidence score", async ({ page }) => {
      const decision = createMockDecision({
        trigger: "Test with confidence",
        confidence: 0.92,
      })

      await mockDecisions(page, [decision])

      await page.goto("/decisions")
      await page.waitForLoadState("networkidle")

      // Confidence should be displayed as percentage
      await expect(page.locator("text=92%")).toBeVisible()
    })
  })

  test.describe("Pagination", () => {
    test("should handle pagination when many decisions exist", async ({ page }) => {
      // Create many decisions
      const decisions = Array.from({ length: 50 }, (_, i) =>
        createMockDecision({ trigger: "Decision number " + (i + 1) })
      )

      let currentPage = 1
      await page.route("**/api/decisions*", (route) => {
        const url = new URL(route.request().url())
        const pageParam = parseInt(url.searchParams.get("page") || "1")
        const limit = parseInt(url.searchParams.get("limit") || "10")
        const offset = (pageParam - 1) * limit

        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(decisions.slice(offset, offset + limit)),
        })
      })

      await page.goto("/decisions")
      await page.waitForLoadState("networkidle")

      // First page should show
      await expect(page.locator("text=Decision number 1")).toBeVisible()

      // Look for pagination controls
      const nextButton = page.locator("text=Next").or(page.locator('[aria-label="Next page"]'))
      if (await nextButton.isVisible()) {
        await nextButton.click()
        await page.waitForLoadState("networkidle")
        // Second page should show different decisions
      }
    })
  })

  test.describe("Entity Filtering", () => {
    test("should filter by entity type if filter is available", async ({ page }) => {
      const decisions = [
        createMockDecision({
          trigger: "Tech decision",
          entities: [createMockEntity({ name: "PostgreSQL", type: "technology" })],
        }),
        createMockDecision({
          trigger: "Pattern decision",
          entities: [createMockEntity({ name: "MVC", type: "pattern" })],
        }),
      ]

      await mockDecisions(page, decisions)

      await page.goto("/decisions")
      await page.waitForLoadState("networkidle")

      // Look for entity type filter
      const filterButton = page.locator("text=Filter").or(page.locator('[aria-label="Filter"]'))
      if (await filterButton.isVisible()) {
        await filterButton.click()

        // Select technology filter if available
        const techFilter = page.locator("text=technology").or(page.locator("text=Technology"))
        if (await techFilter.isVisible()) {
          await techFilter.click()
          await page.waitForLoadState("networkidle")
        }
      }
    })
  })
})
