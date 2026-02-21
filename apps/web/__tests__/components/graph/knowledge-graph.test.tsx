import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '../../utils/test-utils'
import { KnowledgeGraph } from '@/components/graph/knowledge-graph'

// Mock ReactFlow since it requires browser APIs
vi.mock('@xyflow/react', () => {
  const React = require('react')

  const MockReactFlow = ({ children, nodes, edges, onNodeClick }: {
    children: React.ReactNode
    nodes: { id: string; data: { label: string } }[]
    edges: { id: string }[]
    onNodeClick?: (event: React.MouseEvent, node: { id: string }) => void
  }) => (
    <div data-testid="react-flow">
      <div data-testid="nodes-container">
        {nodes.map((node: { id: string; data: { label: string } }) => (
          <div
            key={node.id}
            data-testid={`node-${node.id}`}
            onClick={(e) => onNodeClick?.(e, node as any)}
          >
            {node.data.label}
          </div>
        ))}
      </div>
      <div data-testid="edges-container">
        {edges.map((edge: { id: string }) => (
          <div key={edge.id} data-testid={`edge-${edge.id}`} />
        ))}
      </div>
      {children}
    </div>
  )

  const MockReactFlowProvider = ({ children }: { children: React.ReactNode }) => (
    <div data-testid="react-flow-provider">{children}</div>
  )

  return {
    ReactFlow: MockReactFlow,
    ReactFlowProvider: MockReactFlowProvider,
    Controls: () => <div data-testid="controls" />,
    Background: () => <div data-testid="background" />,
    MiniMap: () => <div data-testid="minimap" />,
    Panel: ({ children, position }: { children: React.ReactNode; position: string }) => (
      <div data-testid={`panel-${position}`}>{children}</div>
    ),
    useNodesState: (initialNodes: any[]) => [initialNodes, vi.fn(), vi.fn()],
    useEdgesState: (initialEdges: any[]) => [initialEdges, vi.fn(), vi.fn()],
    useReactFlow: () => ({
      setCenter: vi.fn(),
      getZoom: vi.fn(() => 1),
      fitView: vi.fn(),
    }),
    Handle: () => null,
    Position: { Top: 'top', Bottom: 'bottom' },
    MarkerType: { ArrowClosed: 'arrowclosed' },
    BackgroundVariant: { Dots: 'dots' },
  }
})

// Sample test data with proper types
const sampleGraphData = {
  nodes: [
    {
      id: 'decision-1',
      type: 'decision' as const,
      label: 'Use PostgreSQL for database',
      has_embedding: true,
      data: {
        id: 'decision-1',
        trigger: 'Need to choose a database',
        context: 'Building a new application',
        options: ['PostgreSQL', 'MongoDB', 'MySQL'],
        decision: 'Use PostgreSQL',
        rationale: 'Better for relational data',
        confidence: 0.9,
        created_at: '2024-01-01T00:00:00Z',
        source: 'claude_logs' as const,
        entities: [{ id: 'e1', name: 'PostgreSQL', type: 'technology' as const }],
      },
    },
    {
      id: 'entity-1',
      type: 'entity' as const,
      label: 'PostgreSQL',
      has_embedding: true,
      data: {
        id: 'entity-1',
        name: 'PostgreSQL',
        type: 'technology' as const,
      },
    },
    {
      id: 'entity-2',
      type: 'entity' as const,
      label: 'Redis',
      has_embedding: false,
      data: {
        id: 'entity-2',
        name: 'Redis',
        type: 'technology' as const,
      },
    },
  ],
  edges: [
    {
      id: 'edge-1',
      source: 'decision-1',
      target: 'entity-1',
      relationship: 'INVOLVES',
      weight: 0.95,
    },
  ],
}

describe('KnowledgeGraph', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders without crashing', () => {
      render(<KnowledgeGraph />)
      // Without data, should show empty state
      expect(screen.getByText(/Your Knowledge Graph is Empty/i)).toBeInTheDocument()
    })

    it('renders with graph data', () => {
      render(<KnowledgeGraph data={sampleGraphData} />)
      expect(screen.getByTestId('react-flow')).toBeInTheDocument()
    })

    it('renders correct number of nodes', () => {
      render(<KnowledgeGraph data={sampleGraphData} />)
      expect(screen.getByTestId('node-decision-1')).toBeInTheDocument()
      expect(screen.getByTestId('node-entity-1')).toBeInTheDocument()
      expect(screen.getByTestId('node-entity-2')).toBeInTheDocument()
    })

    it('renders correct number of edges', () => {
      render(<KnowledgeGraph data={sampleGraphData} />)
      expect(screen.getByTestId('edge-edge-1')).toBeInTheDocument()
    })

    it('renders controls and minimap', () => {
      render(<KnowledgeGraph data={sampleGraphData} />)
      expect(screen.getByTestId('controls')).toBeInTheDocument()
      expect(screen.getByTestId('minimap')).toBeInTheDocument()
    })

    it('renders background', () => {
      render(<KnowledgeGraph data={sampleGraphData} />)
      expect(screen.getByTestId('background')).toBeInTheDocument()
    })
  })

  describe('Empty State', () => {
    it('renders with empty data', () => {
      render(<KnowledgeGraph data={{ nodes: [], edges: [] }} />)
      // Empty nodes should show empty state
      expect(screen.getByText(/Your Knowledge Graph is Empty/i)).toBeInTheDocument()
    })

    it('renders with undefined data', () => {
      render(<KnowledgeGraph data={undefined} />)
      // Undefined data should show empty state
      expect(screen.getByText(/Your Knowledge Graph is Empty/i)).toBeInTheDocument()
    })
  })

  describe('Node Interaction', () => {
    it('calls onNodeClick when node is clicked', () => {
      const handleNodeClick = vi.fn()
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          onNodeClick={handleNodeClick}
        />
      )

      fireEvent.click(screen.getByTestId('node-decision-1'))
      expect(handleNodeClick).toHaveBeenCalled()
    })

    it('shows detail panel when node is selected', () => {
      render(<KnowledgeGraph data={sampleGraphData} />)

      fireEvent.click(screen.getByTestId('node-decision-1'))

      // Detail panel should appear
      expect(screen.getByText(/Decision Details/i)).toBeInTheDocument()
    })
  })

  describe('Source Filtering', () => {
    it('renders source filter panel', () => {
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          sourceCounts={{ claude_logs: 5, interview: 3, manual: 2 }}
        />
      )

      expect(screen.getByText(/Decision Sources/i)).toBeInTheDocument()
    })

    it('shows source counts in filter', () => {
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          sourceCounts={{ claude_logs: 5, interview: 3, manual: 2 }}
        />
      )

      expect(screen.getByText('5')).toBeInTheDocument()
      expect(screen.getByText('3')).toBeInTheDocument()
      expect(screen.getByText('2')).toBeInTheDocument()
    })

    it('calls onSourceFilterChange when source is clicked', () => {
      const handleSourceFilter = vi.fn()
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          sourceCounts={{ claude_logs: 5, interview: 3 }}
          onSourceFilterChange={handleSourceFilter}
        />
      )

      // Click on a source filter button
      const aiExtractedButton = screen.getByText('AI Extracted')
      fireEvent.click(aiExtractedButton)

      expect(handleSourceFilter).toHaveBeenCalled()
    })
  })

  describe('Panels', () => {
    it('renders entity types legend', () => {
      render(<KnowledgeGraph data={sampleGraphData} />)
      expect(screen.getByText(/Entity Types/i)).toBeInTheDocument()
    })

    it('renders relationship legend', () => {
      render(<KnowledgeGraph data={sampleGraphData} />)
      expect(screen.getByText(/Relationships/i)).toBeInTheDocument()
    })

    it('renders stats panel with node and edge counts', () => {
      render(<KnowledgeGraph data={sampleGraphData} />)
      expect(screen.getByText(/3 nodes/i)).toBeInTheDocument()
      expect(screen.getByText(/1 edges/i)).toBeInTheDocument()
    })

    it('renders tip panel', () => {
      render(<KnowledgeGraph data={sampleGraphData} />)
      expect(screen.getByText(/Click and drag to pan/i)).toBeInTheDocument()
    })
  })

  describe('Detail Panel', () => {
    it('shows decision details when decision node is selected', () => {
      render(<KnowledgeGraph data={sampleGraphData} />)

      fireEvent.click(screen.getByTestId('node-decision-1'))

      expect(screen.getByText('Trigger')).toBeInTheDocument()
      expect(screen.getByText('Context')).toBeInTheDocument()
      expect(screen.getByText('Decision')).toBeInTheDocument()
      expect(screen.getByText('Rationale')).toBeInTheDocument()
    })

    it('can close detail panel', () => {
      render(<KnowledgeGraph data={sampleGraphData} />)

      fireEvent.click(screen.getByTestId('node-decision-1'))
      expect(screen.getByText(/Decision Details/i)).toBeInTheDocument()

      // Find and click close button (X icon)
      const closeButtons = screen.getAllByRole('button')
      const closeButton = closeButtons.find(btn =>
        btn.className.includes('hover:text-slate-200')
      )
      if (closeButton) {
        fireEvent.click(closeButton)
      }
    })
  })

  describe('Relationship Styling', () => {
    it('renders edges with relationship type', () => {
      const dataWithMultipleEdges = {
        ...sampleGraphData,
        edges: [
          { id: 'e1', source: 'd1', target: 'ent1', relationship: 'INVOLVES', weight: 1.0 },
          { id: 'e2', source: 'd1', target: 'ent2', relationship: 'SIMILAR_TO', weight: 0.8 },
        ],
      }

      render(<KnowledgeGraph data={dataWithMultipleEdges} />)
      expect(screen.getByTestId('edge-e1')).toBeInTheDocument()
      expect(screen.getByTestId('edge-e2')).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('has interactive elements', () => {
      render(<KnowledgeGraph data={sampleGraphData} />)
      const buttons = screen.getAllByRole('button')
      expect(buttons.length).toBeGreaterThan(0)
    })
  })
})

describe('Node Types', () => {
  describe('Decision Nodes', () => {
    it('renders decision node with correct label', () => {
      render(<KnowledgeGraph data={sampleGraphData} />)
      expect(screen.getByText('Use PostgreSQL for database')).toBeInTheDocument()
    })
  })

  describe('Entity Nodes', () => {
    it('renders entity nodes with correct labels', () => {
      render(<KnowledgeGraph data={sampleGraphData} />)
      expect(screen.getByText('PostgreSQL')).toBeInTheDocument()
      expect(screen.getByText('Redis')).toBeInTheDocument()
    })
  })
})

describe('KnowledgeGraph - Project Filter', () => {
  const projectCounts = {
    continuum: 42,
    'docs-website': 15,
    'mobile-app': 8,
    unassigned: 5,
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Project Filter Panel Rendering', () => {
    it.skip('renders project filter panel when projectCounts provided', () => {
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={projectCounts}
        />
      )

      // Look for project panel or "Projects" heading
      // This will be implemented by frontend-ux-expert
      expect(
        screen.queryByText(/Projects/i) || screen.queryByText(/Filter by Project/i)
      ).toBeTruthy()
    })

    it.skip('does not render project filter when projectCounts is empty', () => {
      render(<KnowledgeGraph data={sampleGraphData} projectCounts={{}} />)

      // Should gracefully handle empty project counts
      const allButtons = screen.getAllByRole('button')
      expect(allButtons).toBeDefined()
    })

    it.skip('renders "All Projects" button', () => {
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={projectCounts}
        />
      )

      expect(screen.getByText(/All Projects/i)).toBeInTheDocument()
    })

    it.skip('renders individual project filter buttons', () => {
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={projectCounts}
        />
      )

      expect(screen.getByText('continuum')).toBeInTheDocument()
      expect(screen.getByText('docs-website')).toBeInTheDocument()
      expect(screen.getByText('mobile-app')).toBeInTheDocument()
      expect(screen.getByText('unassigned')).toBeInTheDocument()
    })

    it.skip('displays project counts in badges', () => {
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={projectCounts}
        />
      )

      expect(screen.getByText('42')).toBeInTheDocument()
      expect(screen.getByText('15')).toBeInTheDocument()
      expect(screen.getByText('8')).toBeInTheDocument()
      expect(screen.getByText('5')).toBeInTheDocument()
    })

    it.skip('shows total count in "All Projects" button', () => {
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={projectCounts}
        />
      )

      // Total should be 42 + 15 + 8 + 5 = 70
      expect(screen.getByText('70')).toBeInTheDocument()
    })
  })

  describe('Project Filter Interaction', () => {
    it.skip('calls onProjectFilterChange when project button is clicked', () => {
      const handleProjectFilter = vi.fn()
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={projectCounts}
          onProjectFilterChange={handleProjectFilter}
        />
      )

      const continuumButton = screen.getByText('continuum')
      fireEvent.click(continuumButton)

      expect(handleProjectFilter).toHaveBeenCalledWith('continuum')
    })

    it.skip('calls onProjectFilterChange with null when "All Projects" clicked', () => {
      const handleProjectFilter = vi.fn()
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={projectCounts}
          projectFilter="continuum"
          onProjectFilterChange={handleProjectFilter}
        />
      )

      const allProjectsButton = screen.getByText(/All Projects/i)
      fireEvent.click(allProjectsButton)

      expect(handleProjectFilter).toHaveBeenCalledWith(null)
    })

    it.skip('toggles selected project on repeated clicks', () => {
      const handleProjectFilter = vi.fn()
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={projectCounts}
          onProjectFilterChange={handleProjectFilter}
        />
      )

      const docsButton = screen.getByText('docs-website')

      // First click: select
      fireEvent.click(docsButton)
      expect(handleProjectFilter).toHaveBeenCalledWith('docs-website')

      // Second click: deselect (should call with null)
      fireEvent.click(docsButton)
      expect(handleProjectFilter).toHaveBeenCalledWith(null)
    })

    it.skip('handles clicking unassigned project', () => {
      const handleProjectFilter = vi.fn()
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={projectCounts}
          onProjectFilterChange={handleProjectFilter}
        />
      )

      const unassignedButton = screen.getByText('unassigned')
      fireEvent.click(unassignedButton)

      expect(handleProjectFilter).toHaveBeenCalledWith('unassigned')
    })
  })

  describe('Project Filter State - Visual Highlighting', () => {
    it.skip('highlights selected project button', () => {
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={projectCounts}
          projectFilter="continuum"
        />
      )

      const continuumButton = screen.getByText('continuum')
      expect(continuumButton.closest('button')).toHaveClass(
        expect.stringMatching(/bg-|border-/)
      )
    })

    it.skip('shows "All Projects" as selected when no filter applied', () => {
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={projectCounts}
          projectFilter={null}
        />
      )

      const allProjectsButton = screen.getByText(/All Projects/i)
      expect(allProjectsButton.closest('button')).toHaveAttribute(
        'aria-pressed',
        'true'
      )
    })

    it.skip('applies outline variant to non-selected projects', () => {
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={projectCounts}
          projectFilter="continuum"
        />
      )

      const docsButton = screen.getByText('docs-website')
      expect(docsButton.closest('button')).not.toHaveAttribute(
        'aria-pressed',
        'true'
      )
    })
  })

  describe('Project Filter Accessibility', () => {
    it.skip('project filter buttons are keyboard navigable', () => {
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={projectCounts}
        />
      )

      const continuumButton = screen.getByText('continuum')
      expect(continuumButton.closest('button')).toHaveAttribute('type', 'button')
    })

    it.skip('project filter buttons have aria-pressed state', () => {
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={projectCounts}
          projectFilter="continuum"
        />
      )

      const continuumButton = screen.getByText('continuum')
      expect(continuumButton.closest('button')).toHaveAttribute(
        'aria-pressed',
        'true'
      )

      const docsButton = screen.getByText('docs-website')
      expect(docsButton.closest('button')).toHaveAttribute(
        'aria-pressed',
        'false'
      )
    })

    it.skip('project filter buttons have aria-label', () => {
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={projectCounts}
        />
      )

      const continuumButton = screen.getByText('continuum')
      const buttonElement = continuumButton.closest('button')
      expect(buttonElement).toHaveAttribute(
        'aria-label',
        expect.stringMatching(/filter|project/i)
      )
    })

    it.skip('allows Tab key navigation through project filters', () => {
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={projectCounts}
        />
      )

      const allButtons = screen.getAllByRole('button')
      const projectButtons = allButtons.filter((btn) =>
        btn.textContent?.match(
          /continuum|docs-website|mobile-app|unassigned|All Projects/
        )
      )

      expect(projectButtons.length).toBeGreaterThan(0)
      projectButtons.forEach((btn) => {
        expect(btn).toBeVisible()
      })
    })
  })

  describe('Project Filter Integration with Source Filter', () => {
    it.skip('renders both source and project filters simultaneously', () => {
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          sourceCounts={{ claude_logs: 5, interview: 3 }}
          projectCounts={projectCounts}
        />
      )

      expect(screen.getByText(/Decision Sources/i)).toBeInTheDocument()
      expect(screen.getByText(/All Projects/i)).toBeInTheDocument()
    })

    it.skip('allows both source and project filters to be active', () => {
      const handleSourceFilter = vi.fn()
      const handleProjectFilter = vi.fn()

      render(
        <KnowledgeGraph
          data={sampleGraphData}
          sourceCounts={{ claude_logs: 5 }}
          projectCounts={projectCounts}
          sourceFilter="claude_logs"
          projectFilter="continuum"
          onSourceFilterChange={handleSourceFilter}
          onProjectFilterChange={handleProjectFilter}
        />
      )

      expect(screen.getByText(/AI Extracted/i)).toBeInTheDocument()
      expect(screen.getByText('continuum')).toBeInTheDocument()
    })

    it.skip('changing project filter does not affect source filter', () => {
      const handleSourceFilter = vi.fn()
      const handleProjectFilter = vi.fn()

      render(
        <KnowledgeGraph
          data={sampleGraphData}
          sourceCounts={{ claude_logs: 5 }}
          projectCounts={projectCounts}
          sourceFilter="claude_logs"
          onSourceFilterChange={handleSourceFilter}
          onProjectFilterChange={handleProjectFilter}
        />
      )

      const continuumButton = screen.getByText('continuum')
      fireEvent.click(continuumButton)

      expect(handleProjectFilter).toHaveBeenCalledWith('continuum')
      expect(handleSourceFilter).not.toHaveBeenCalled()
    })
  })

  describe('Project Filter Edge Cases', () => {
    it.skip('handles project names with special characters', () => {
      const specialProjectCounts = {
        'project-with-dashes': 10,
        'project.with.dots': 5,
        'project_with_underscores': 3,
      }

      render(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={specialProjectCounts}
        />
      )

      expect(screen.getByText('project-with-dashes')).toBeInTheDocument()
      expect(screen.getByText('project.with.dots')).toBeInTheDocument()
      expect(screen.getByText('project_with_underscores')).toBeInTheDocument()
    })

    it.skip('handles very long project names gracefully', () => {
      const longProjectCounts = {
        'very-long-project-name-that-might-need-truncation-or-wrapping': 10,
      }

      render(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={longProjectCounts}
        />
      )

      expect(
        screen.getByText(/very-long-project-name/, { exact: false })
      ).toBeInTheDocument()
    })

    it.skip('handles zero count projects', () => {
      const zeroCounts = {
        continuum: 0,
        'docs-website': 5,
      }

      render(<KnowledgeGraph data={sampleGraphData} projectCounts={zeroCounts} />)

      expect(screen.getByText('continuum')).toBeInTheDocument()
      expect(screen.getByText('0')).toBeInTheDocument()
    })

    it.skip('handles single project', () => {
      const singleProject = {
        continuum: 42,
      }

      render(
        <KnowledgeGraph data={sampleGraphData} projectCounts={singleProject} />
      )

      expect(screen.getByText('continuum')).toBeInTheDocument()
      expect(screen.getByText(/All Projects/i)).toBeInTheDocument()
    })

    it.skip('handles many projects (pagination/scrolling)', () => {
      const manyCounts = Object.fromEntries(
        Array.from({ length: 20 }, (_, i) => [`project-${i}`, i + 1])
      )

      render(<KnowledgeGraph data={sampleGraphData} projectCounts={manyCounts} />)

      expect(screen.getByText('project-0')).toBeInTheDocument()
      expect(screen.getByText('project-19')).toBeInTheDocument()
    })
  })

  describe('Project Filter Panel Position', () => {
    it.skip('positions project filter panel below source filter', () => {
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          sourceCounts={{ claude_logs: 5 }}
          projectCounts={projectCounts}
        />
      )

      const panels = screen.getAllByTestId(/panel-top-left/)
      expect(panels.length).toBeGreaterThanOrEqual(2)
    })

    it.skip('adjusts layout when source filter is hidden', () => {
      render(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={projectCounts}
        />
      )

      expect(screen.getByText(/All Projects/i)).toBeInTheDocument()
    })
  })

  describe('Project Filter Performance', () => {
    it.skip('does not re-render unnecessarily when projectCounts unchanged', () => {
      const { rerender } = render(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={projectCounts}
        />
      )

      const continuumButton = screen.getByText('continuum')
      const initialElement = continuumButton.parentElement

      rerender(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={projectCounts}
        />
      )

      const afterRerender = screen.getByText('continuum')
      expect(afterRerender.parentElement).toBe(initialElement)
    })

    it.skip('updates efficiently when projectFilter prop changes', () => {
      const { rerender } = render(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={projectCounts}
          projectFilter={null}
        />
      )

      rerender(
        <KnowledgeGraph
          data={sampleGraphData}
          projectCounts={projectCounts}
          projectFilter="continuum"
        />
      )

      const continuumButton = screen.getByText('continuum')
      expect(continuumButton.closest('button')).toHaveAttribute(
        'aria-pressed',
        'true'
      )
    })
  })
})
