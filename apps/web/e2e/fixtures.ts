/**
 * E2E Test Fixtures and Utilities
 *
 * QA-P2-1: Shared fixtures and helpers for E2E tests.
 */
import { test as base, expect } from "@playwright/test"

// Extend the base test with custom fixtures
export const test = base.extend({
  // Auto-wait for API to be ready before each test
  autoWaitForApi: [
    async ({ page }, use) => {
      // Navigate to the page and wait for hydration
      await page.goto("/")
      // Wait for React to hydrate by checking for interactive elements
      await page.waitForLoadState("networkidle")
      await use(page)
    },
    { auto: true },
  ],
})

export { expect }

// Page Object for Dashboard
export class DashboardPage {
  constructor(private page: any) {}

  async goto() {
    await this.page.goto("/")
    await this.page.waitForLoadState("networkidle")
  }

  async getStatCardValue(title: string) {
    const card = this.page.locator("text=" + title).locator("..").locator("..")
    return card.locator(".text-4xl").textContent()
  }

  async getRecentDecisionsCount() {
    const cards = this.page.locator('[role="article"]')
    return cards.count()
  }

  async clickViewGraph() {
    await this.page.click("text=View Graph")
  }

  async clickAddKnowledge() {
    await this.page.click("text=Add Knowledge")
  }
}

// Page Object for Decisions Page
export class DecisionsPage {
  constructor(private page: any) {}

  async goto() {
    await this.page.goto("/decisions")
    await this.page.waitForLoadState("networkidle")
  }

  async searchDecision(query: string) {
    const searchInput = this.page.getByPlaceholder(/search/i)
    await searchInput.fill(query)
    await this.page.waitForTimeout(500) // Debounce
  }

  async getDecisionCount() {
    const decisions = this.page.locator('[role="article"]')
    return decisions.count()
  }

  async clickFirstDecision() {
    const firstDecision = this.page.locator('[role="article"]').first()
    await firstDecision.click()
  }
}

// Page Object for Graph Page
export class GraphPage {
  constructor(private page: any) {}

  async goto() {
    await this.page.goto("/graph")
    await this.page.waitForLoadState("networkidle")
  }

  async waitForGraphRender() {
    // Wait for React Flow to render
    await this.page.waitForSelector('[data-testid="rf__wrapper"]', { timeout: 10000 }).catch(() => {
      // Fallback: wait for any canvas or svg element
      return this.page.waitForSelector("canvas, svg", { timeout: 5000 })
    })
  }

  async getNodeCount() {
    // React Flow nodes have specific classes
    const nodes = this.page.locator(".react-flow__node")
    return nodes.count()
  }

  async clickNode(index: number) {
    const nodes = this.page.locator(".react-flow__node")
    await nodes.nth(index).click()
  }

  async zoomIn() {
    const zoomIn = this.page.locator('[aria-label="zoom in"]')
    if (await zoomIn.isVisible()) {
      await zoomIn.click()
    }
  }

  async zoomOut() {
    const zoomOut = this.page.locator('[aria-label="zoom out"]')
    if (await zoomOut.isVisible()) {
      await zoomOut.click()
    }
  }
}

// API mocking utilities
export async function mockDashboardStats(page: any, stats: any) {
  await page.route("**/api/dashboard/stats", (route: any) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(stats),
    })
  })
}

export async function mockDecisions(page: any, decisions: any[]) {
  await page.route("**/api/decisions*", (route: any) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(decisions),
    })
  })
}

export async function mockGraphData(page: any, graphData: any) {
  await page.route("**/api/graph*", (route: any) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(graphData),
    })
  })
}

// Test data factories
export function createMockDecision(overrides = {}) {
  return {
    id: "test-decision-" + Math.random().toString(36).slice(2),
    trigger: "Test trigger",
    context: "Test context",
    options: ["Option A", "Option B"],
    agent_decision: "Chose Option A",
    agent_rationale: "Because it was better",
    human_decision: null,
    human_rationale: null,
    confidence: 0.85,
    created_at: new Date().toISOString(),
    source: "manual",
    entities: [],
    ...overrides,
  }
}

export function createMockEntity(overrides = {}) {
  return {
    id: "test-entity-" + Math.random().toString(36).slice(2),
    name: "Test Entity",
    type: "technology",
    ...overrides,
  }
}

export function createMockGraphData(nodeCount = 5, edgeCount = 3) {
  const nodes = []
  const edges = []

  for (let i = 0; i < nodeCount; i++) {
    nodes.push({
      id: "node-" + i,
      type: i % 2 === 0 ? "decision" : "entity",
      label: "Node " + i,
      has_embedding: true,
      data: i % 2 === 0
        ? createMockDecision({ id: "node-" + i })
        : createMockEntity({ id: "node-" + i }),
    })
  }

  for (let i = 0; i < edgeCount; i++) {
    edges.push({
      id: "edge-" + i,
      source: "node-" + i,
      target: "node-" + ((i + 1) % nodeCount),
      relationship: "INVOLVES",
      weight: 0.8,
    })
  }

  return { nodes, edges, pagination: { page: 1, page_size: 100, total_count: nodeCount, total_pages: 1, has_more: false } }
}
