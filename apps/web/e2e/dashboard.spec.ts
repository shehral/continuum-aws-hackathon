/**
 * Dashboard E2E Tests
 *
 * QA-P2-1: Tests for dashboard page critical flows.
 */
import { test, expect } from "@playwright/test"
import {
  DashboardPage,
  mockDashboardStats,
  createMockDecision,
} from "./fixtures"

test.describe("Dashboard Page", () => {
  test.describe("Loading and Display", () => {
    test("should load dashboard and display stats cards", async ({ page }) => {
      // Mock the API response
      await mockDashboardStats(page, {
        total_decisions: 42,
        total_entities: 128,
        total_sessions: 7,
        recent_decisions: [],
      })

      await page.goto("/")
      await page.waitForLoadState("networkidle")

      // Verify page title and header
      await expect(page.locator("text=Welcome back!")).toBeVisible()

      // Verify stat cards are present
      await expect(page.locator("text=Total Decisions")).toBeVisible()
      await expect(page.locator("text=Entities")).toBeVisible()
      await expect(page.locator("text=Capture Sessions")).toBeVisible()
      await expect(page.locator("text=Graph Connections")).toBeVisible()
    })

    test("should display animated numbers in stat cards", async ({ page }) => {
      await mockDashboardStats(page, {
        total_decisions: 100,
        total_entities: 50,
        total_sessions: 10,
        recent_decisions: [],
      })

      await page.goto("/")
      await page.waitForLoadState("networkidle")

      // Wait for animation to complete (1 second default)
      await page.waitForTimeout(1200)

      // Verify numbers are displayed (animation should have completed)
      const decisionsCard = page.locator("text=Total Decisions").locator("..").locator("..")
      await expect(decisionsCard).toContainText("100")
    })

    test("should display empty state when no decisions", async ({ page }) => {
      await mockDashboardStats(page, {
        total_decisions: 0,
        total_entities: 0,
        total_sessions: 0,
        recent_decisions: [],
      })

      await page.goto("/")
      await page.waitForLoadState("networkidle")

      // Verify empty state message
      await expect(page.locator("text=No decisions yet")).toBeVisible()
      await expect(page.locator("text=Add Knowledge").first()).toBeVisible()
    })

    test("should display recent decisions", async ({ page }) => {
      const decisions = [
        createMockDecision({ trigger: "Choose database", decision: "PostgreSQL" }),
        createMockDecision({ trigger: "Choose framework", decision: "FastAPI" }),
        createMockDecision({ trigger: "Choose cache", decision: "Redis" }),
      ]

      await mockDashboardStats(page, {
        total_decisions: 3,
        total_entities: 10,
        total_sessions: 1,
        recent_decisions: decisions,
      })

      await page.goto("/")
      await page.waitForLoadState("networkidle")

      // Verify recent decisions are displayed
      await expect(page.locator("text=Recent Decisions")).toBeVisible()
      await expect(page.locator("text=Choose database")).toBeVisible()
      await expect(page.locator("text=Choose framework")).toBeVisible()
      await expect(page.locator("text=Choose cache")).toBeVisible()
    })
  })

  test.describe("Navigation", () => {
    test("should navigate to graph page when clicking View Graph", async ({ page }) => {
      await mockDashboardStats(page, {
        total_decisions: 5,
        total_entities: 10,
        total_sessions: 1,
        recent_decisions: [],
      })

      await page.goto("/")
      await page.waitForLoadState("networkidle")

      await page.click("text=View Graph")
      await expect(page).toHaveURL(/\/graph/)
    })

    test("should navigate to add page when clicking Add Knowledge", async ({ page }) => {
      await mockDashboardStats(page, {
        total_decisions: 0,
        total_entities: 0,
        total_sessions: 0,
        recent_decisions: [],
      })

      await page.goto("/")
      await page.waitForLoadState("networkidle")

      await page.click("text=Add Knowledge")
      await expect(page).toHaveURL(/\/add/)
    })

    test("should navigate to decisions page when clicking on stat card", async ({ page }) => {
      await mockDashboardStats(page, {
        total_decisions: 10,
        total_entities: 20,
        total_sessions: 2,
        recent_decisions: [],
      })

      await page.goto("/")
      await page.waitForLoadState("networkidle")

      // Click on Total Decisions card (should be a link when value > 0)
      const decisionsCard = page.locator("text=Total Decisions").locator("..").locator("..")
      await decisionsCard.click()
      await expect(page).toHaveURL(/\/decisions/)
    })

    test("should navigate to decision details when clicking recent decision", async ({ page }) => {
      const decision = createMockDecision({ id: "test-123", trigger: "Test Decision" })

      await mockDashboardStats(page, {
        total_decisions: 1,
        total_entities: 5,
        total_sessions: 1,
        recent_decisions: [decision],
      })

      await page.goto("/")
      await page.waitForLoadState("networkidle")

      await page.click("text=Test Decision")
      await expect(page).toHaveURL(/\/decisions/)
    })
  })

  test.describe("Error Handling", () => {
    test("should display error state when API fails", async ({ page }) => {
      // Mock API failure
      await page.route("**/api/dashboard/stats", (route) => {
        route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Service unavailable" }),
        })
      })

      await page.goto("/")
      await page.waitForLoadState("networkidle")

      // Verify error state is shown
      await expect(page.locator("text=Failed to load").or(page.locator("text=error"))).toBeVisible({ timeout: 5000 })
    })

    test("should allow retry after error", async ({ page }) => {
      let callCount = 0

      await page.route("**/api/dashboard/stats", (route) => {
        callCount++
        if (callCount === 1) {
          route.fulfill({
            status: 503,
            contentType: "application/json",
            body: JSON.stringify({ detail: "Service unavailable" }),
          })
        } else {
          route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              total_decisions: 5,
              total_entities: 10,
              total_sessions: 1,
              recent_decisions: [],
            }),
          })
        }
      })

      await page.goto("/")
      await page.waitForLoadState("networkidle")

      // Click retry button if visible
      const retryButton = page.locator("text=Try again").or(page.locator("text=Retry"))
      if (await retryButton.isVisible({ timeout: 3000 })) {
        await retryButton.click()
        await page.waitForLoadState("networkidle")

        // Verify data is now loaded
        await expect(page.locator("text=Total Decisions")).toBeVisible()
      }
    })
  })

  test.describe("Accessibility", () => {
    test("should have proper ARIA labels", async ({ page }) => {
      await mockDashboardStats(page, {
        total_decisions: 5,
        total_entities: 10,
        total_sessions: 1,
        recent_decisions: [createMockDecision({ trigger: "Test" })],
      })

      await page.goto("/")
      await page.waitForLoadState("networkidle")

      // Check for ARIA labels on interactive elements
      await expect(page.locator('[role="article"]')).toHaveCount(1)
      await expect(page.locator('[role="feed"]').or(page.locator('[role="list"]'))).toBeVisible()
    })

    test("should be keyboard navigable", async ({ page }) => {
      await mockDashboardStats(page, {
        total_decisions: 3,
        total_entities: 10,
        total_sessions: 1,
        recent_decisions: [
          createMockDecision({ trigger: "Decision 1" }),
          createMockDecision({ trigger: "Decision 2" }),
        ],
      })

      await page.goto("/")
      await page.waitForLoadState("networkidle")

      // Tab through interactive elements
      await page.keyboard.press("Tab")
      await page.keyboard.press("Tab")

      // Verify focus is visible (element has focus-visible styles)
      const focusedElement = page.locator(":focus")
      await expect(focusedElement).toBeVisible()
    })
  })
})
