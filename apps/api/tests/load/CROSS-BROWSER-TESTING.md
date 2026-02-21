# Cross-Browser Testing Checklist

This document outlines the cross-browser testing strategy for Continuum's web application.

## Target Browsers

| Browser | Versions | Priority |
|---------|----------|----------|
| Chrome | Latest, Latest-1 | Critical |
| Firefox | Latest, Latest-1 | Critical |
| Safari | Latest (macOS), Latest (iOS) | Critical |
| Edge | Latest | Medium |

## Test Environments

### Desktop

| OS | Browsers |
|----|----------|
| macOS Sonoma/Ventura | Chrome, Safari, Firefox |
| Windows 11/10 | Chrome, Edge, Firefox |
| Ubuntu 22.04 | Chrome, Firefox |

### Mobile (Responsive)

| Device | Browser |
|--------|---------|
| iPhone 15/14 (iOS 17/16) | Safari |
| iPad Pro/Air | Safari |
| Android (Pixel/Samsung) | Chrome |

## User Flows

### 1. Dashboard View

**Route:** `/` (Home Page)

| Test Case | Chrome | Firefox | Safari | Status |
|-----------|--------|---------|--------|--------|
| Page loads without errors | [ ] | [ ] | [ ] | |
| Statistics cards render correctly | [ ] | [ ] | [ ] | |
| Recent decisions list displays | [ ] | [ ] | [ ] | |
| Navigation links work | [ ] | [ ] | [ ] | |
| Responsive layout (mobile) | [ ] | [ ] | [ ] | |
| Theme toggle (light/dark) works | [ ] | [ ] | [ ] | |
| Loading states display correctly | [ ] | [ ] | [ ] | |
| Error states display correctly | [ ] | [ ] | [ ] | |

**Specific Checks:**
- [ ] Decision count displays correctly
- [ ] Entity count displays correctly
- [ ] Session count displays correctly
- [ ] Recent decisions show trigger text
- [ ] Entity badges render with correct colors

---

### 2. Knowledge Graph

**Route:** `/graph`

| Test Case | Chrome | Firefox | Safari | Status |
|-----------|--------|---------|--------|--------|
| Graph canvas renders | [ ] | [ ] | [ ] | |
| Nodes display with correct styling | [ ] | [ ] | [ ] | |
| Edges render between nodes | [ ] | [ ] | [ ] | |
| Pan functionality works | [ ] | [ ] | [ ] | |
| Zoom functionality works | [ ] | [ ] | [ ] | |
| Node selection highlights | [ ] | [ ] | [ ] | |
| Node detail panel opens | [ ] | [ ] | [ ] | |
| Minimap displays correctly | [ ] | [ ] | [ ] | |
| Fit-to-view button works | [ ] | [ ] | [ ] | |
| Filter controls function | [ ] | [ ] | [ ] | |

**Specific Checks:**
- [ ] Decision nodes (purple) render correctly
- [ ] Entity nodes (blue/green by type) render correctly
- [ ] Edge labels are readable
- [ ] Hover states work on nodes
- [ ] Touch gestures work on mobile (pinch-zoom, pan)
- [ ] Performance acceptable with 100+ nodes
- [ ] No canvas rendering glitches

---

### 3. Search Functionality

**Route:** `/search` and Global Search Bar

| Test Case | Chrome | Firefox | Safari | Status |
|-----------|--------|---------|--------|--------|
| Search input accepts text | [ ] | [ ] | [ ] | |
| Search suggestions appear | [ ] | [ ] | [ ] | |
| Results display on submit | [ ] | [ ] | [ ] | |
| Result items are clickable | [ ] | [ ] | [ ] | |
| Empty state displays | [ ] | [ ] | [ ] | |
| Loading indicator shows | [ ] | [ ] | [ ] | |
| Keyboard navigation works | [ ] | [ ] | [ ] | |
| Search history persists | [ ] | [ ] | [ ] | |

**Specific Checks:**
- [ ] Autocomplete dropdown renders correctly
- [ ] Result highlighting works
- [ ] Decision results show trigger preview
- [ ] Entity results show type badge
- [ ] Score/relevance indicator displays
- [ ] Hybrid search filters work

---

### 4. Decision Details

**Route:** `/decisions` and Decision Detail Modal/Page

| Test Case | Chrome | Firefox | Safari | Status |
|-----------|--------|---------|--------|--------|
| Decision list loads | [ ] | [ ] | [ ] | |
| Pagination works | [ ] | [ ] | [ ] | |
| Decision card expands | [ ] | [ ] | [ ] | |
| All decision fields display | [ ] | [ ] | [ ] | |
| Entity links are clickable | [ ] | [ ] | [ ] | |
| Edit functionality works | [ ] | [ ] | [ ] | |
| Delete confirmation works | [ ] | [ ] | [ ] | |
| Source badge displays | [ ] | [ ] | [ ] | |

**Specific Checks:**
- [ ] Trigger text displays fully
- [ ] Context section renders markdown
- [ ] Options list is properly formatted
- [ ] Rationale section is readable
- [ ] Confidence indicator shows percentage
- [ ] Created date formats correctly
- [ ] Entity chips are interactive

---

### 5. Add Decision (Manual Entry)

**Route:** `/add`

| Test Case | Chrome | Firefox | Safari | Status |
|-----------|--------|---------|--------|--------|
| Form renders completely | [ ] | [ ] | [ ] | |
| All input fields accept text | [ ] | [ ] | [ ] | |
| Options can be added/removed | [ ] | [ ] | [ ] | |
| Entity auto-complete works | [ ] | [ ] | [ ] | |
| Form validation displays | [ ] | [ ] | [ ] | |
| Submit button enables/disables | [ ] | [ ] | [ ] | |
| Success message appears | [ ] | [ ] | [ ] | |
| Redirect after submit works | [ ] | [ ] | [ ] | |

**Specific Checks:**
- [ ] Trigger field has character limit indicator
- [ ] Context textarea auto-expands
- [ ] Options input allows multiple entries
- [ ] Entity suggestions work
- [ ] Auto-extract toggle functions
- [ ] Error messages are clear

---

### 6. Authentication Flow

**Routes:** `/login`, `/register`

| Test Case | Chrome | Firefox | Safari | Status |
|-----------|--------|---------|--------|--------|
| Login form displays | [ ] | [ ] | [ ] | |
| Email input validates | [ ] | [ ] | [ ] | |
| Password input masks | [ ] | [ ] | [ ] | |
| Submit button works | [ ] | [ ] | [ ] | |
| Error messages display | [ ] | [ ] | [ ] | |
| Redirect on success | [ ] | [ ] | [ ] | |
| Session persists | [ ] | [ ] | [ ] | |
| Logout works | [ ] | [ ] | [ ] | |

---

## Visual Regression Checks

### Typography

| Check | Chrome | Firefox | Safari |
|-------|--------|---------|--------|
| Font family loads correctly | [ ] | [ ] | [ ] |
| Font weights render properly | [ ] | [ ] | [ ] |
| Line heights are consistent | [ ] | [ ] | [ ] |
| Text doesn't overflow | [ ] | [ ] | [ ] |

### Colors & Themes

| Check | Chrome | Firefox | Safari |
|-------|--------|---------|--------|
| Brand colors render correctly | [ ] | [ ] | [ ] |
| Dark mode colors are consistent | [ ] | [ ] | [ ] |
| Contrast ratios are accessible | [ ] | [ ] | [ ] |
| Gradients render smoothly | [ ] | [ ] | [ ] |

### Layout

| Check | Chrome | Firefox | Safari |
|-------|--------|---------|--------|
| Grid system aligns | [ ] | [ ] | [ ] |
| Flexbox layouts work | [ ] | [ ] | [ ] |
| Overflow scrolling works | [ ] | [ ] | [ ] |
| Fixed/sticky elements position | [ ] | [ ] | [ ] |

### Animations

| Check | Chrome | Firefox | Safari |
|-------|--------|---------|--------|
| Transitions are smooth | [ ] | [ ] | [ ] |
| No animation jank | [ ] | [ ] | [ ] |
| Hover effects work | [ ] | [ ] | [ ] |
| Loading spinners animate | [ ] | [ ] | [ ] |

---

## Accessibility Checks

| Check | Chrome | Firefox | Safari |
|-------|--------|---------|--------|
| Keyboard navigation works | [ ] | [ ] | [ ] |
| Focus indicators visible | [ ] | [ ] | [ ] |
| Screen reader compatibility | [ ] | [ ] | [ ] |
| ARIA labels present | [ ] | [ ] | [ ] |
| Color contrast (WCAG AA) | [ ] | [ ] | [ ] |
| Skip links work | [ ] | [ ] | [ ] |

---

## Performance Benchmarks

Run Lighthouse audits on each browser:

| Metric | Chrome | Firefox | Safari | Target |
|--------|--------|---------|--------|--------|
| First Contentful Paint | | | | < 1.8s |
| Largest Contentful Paint | | | | < 2.5s |
| Total Blocking Time | | | | < 200ms |
| Cumulative Layout Shift | | | | < 0.1 |
| Speed Index | | | | < 3.4s |

---

## Known Browser-Specific Issues

### Safari

- [ ] CSS `gap` in flexbox (supported in Safari 14.1+)
- [ ] Backdrop blur (`backdrop-filter`) may need `-webkit-` prefix
- [ ] Date input formatting differs
- [ ] `position: sticky` in tables may not work

### Firefox

- [ ] Scrollbar styling differences
- [ ] `overflow: overlay` not supported
- [ ] Some CSS filters may render differently

### Edge

- [ ] Should behave like Chrome (Chromium-based)
- [ ] Some enterprise policies may affect behavior

---

## Automated Cross-Browser Testing

### Playwright Configuration

If Playwright is installed, use this configuration:

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
    {
      name: 'Mobile Safari',
      use: { ...devices['iPhone 12'] },
    },
  ],
  webServer: {
    command: 'pnpm dev:web',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
  },
});
```

### Sample E2E Test

```typescript
// e2e/dashboard.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Dashboard', () => {
  test('loads successfully', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/Continuum/);
    await expect(page.getByRole('heading', { name: /Dashboard/i })).toBeVisible();
  });

  test('displays statistics', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText(/Total Decisions/i)).toBeVisible();
    await expect(page.getByText(/Total Entities/i)).toBeVisible();
  });
});

// e2e/graph.spec.ts
test.describe('Knowledge Graph', () => {
  test('renders graph canvas', async ({ page }) => {
    await page.goto('/graph');
    await expect(page.locator('.react-flow')).toBeVisible();
  });

  test('supports zoom controls', async ({ page }) => {
    await page.goto('/graph');
    const zoomIn = page.getByRole('button', { name: /zoom in/i });
    const zoomOut = page.getByRole('button', { name: /zoom out/i });
    await expect(zoomIn).toBeVisible();
    await expect(zoomOut).toBeVisible();
  });
});

// e2e/search.spec.ts
test.describe('Search', () => {
  test('accepts search input', async ({ page }) => {
    await page.goto('/search');
    const searchInput = page.getByPlaceholder(/search/i);
    await searchInput.fill('PostgreSQL');
    await searchInput.press('Enter');
    // Wait for results
    await expect(page.getByText(/results/i)).toBeVisible();
  });
});
```

### Running Automated Tests

```bash
# Install Playwright
pnpm add -D @playwright/test
npx playwright install

# Run all browsers
npx playwright test

# Run specific browser
npx playwright test --project=chromium
npx playwright test --project=firefox
npx playwright test --project=webkit

# Run with UI
npx playwright test --ui

# Generate report
npx playwright show-report
```

---

## Testing Workflow

### Before Release

1. [ ] Run automated Playwright tests on all browsers
2. [ ] Perform manual smoke test on primary flows
3. [ ] Verify no console errors in DevTools
4. [ ] Check network requests complete successfully
5. [ ] Test on at least one mobile device per platform

### Bug Reporting

When reporting cross-browser issues, include:

- Browser name and version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Console errors (if any)
- Screenshot or video

---

## Related Documentation

- [Test Coverage Status](/docs/testing/coverage-status.md)
- [Load Testing](/apps/api/tests/load/README.md)
- [API Documentation](/docs/api/)
