import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { api } from '@/lib/api'

// Mock global fetch
const mockFetch = vi.fn()
global.fetch = mockFetch

describe('ApiClient - Project Methods', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.resetAllMocks()
  })

  describe('getProjectCounts', () => {
    it('returns project counts with correct data structure', async () => {
      const mockProjectCounts = {
        continuum: 42,
        'docs-website': 15,
        unassigned: 5,
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockProjectCounts,
      })

      const result = await api.getProjectCounts()

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/graph/projects'),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
        })
      )
      expect(result).toEqual(mockProjectCounts)
      expect(Object.keys(result)).toContain('continuum')
      expect(Object.keys(result)).toContain('docs-website')
      expect(Object.keys(result)).toContain('unassigned')
      expect(typeof result.continuum).toBe('number')
    })

    it('handles empty project counts', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({}),
      })

      const result = await api.getProjectCounts()

      expect(result).toEqual({})
    })

    it('handles API errors gracefully', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
      })

      await expect(api.getProjectCounts()).rejects.toThrow(
        'API error: 500 Internal Server Error'
      )
    })

    it('handles network errors', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'))

      await expect(api.getProjectCounts()).rejects.toThrow('Network error')
    })
  })

  describe('getGraph - project_filter parameter', () => {
    it('accepts project_filter parameter', async () => {
      const mockGraphData = {
        nodes: [
          {
            id: 'decision-1',
            type: 'decision',
            label: 'Test Decision',
            data: {
              id: 'decision-1',
              trigger: 'Test',
              context: 'Test context',
              options: ['A', 'B'],
              decision: 'A',
              rationale: 'Test rationale',
              confidence: 0.9,
              created_at: '2024-01-01T00:00:00Z',
              entities: [],
              project_name: 'continuum',
            },
          },
        ],
        edges: [],
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockGraphData,
      })

      await api.getGraph({ project_filter: 'continuum' })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('project_filter=continuum'),
        expect.any(Object)
      )
    })

    it('constructs URL correctly with project_filter', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ nodes: [], edges: [] }),
      })

      await api.getGraph({ project_filter: 'docs-website' })

      const callUrl = mockFetch.mock.calls[0][0]
      expect(callUrl).toContain('/api/graph?')
      expect(callUrl).toContain('project_filter=docs-website')
    })

    it('handles unassigned project filter', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ nodes: [], edges: [] }),
      })

      await api.getGraph({ project_filter: 'unassigned' })

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('project_filter=unassigned'),
        expect.any(Object)
      )
    })

    it('omits project_filter when not provided', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ nodes: [], edges: [] }),
      })

      await api.getGraph({})

      const callUrl = mockFetch.mock.calls[0][0]
      expect(callUrl).not.toContain('project_filter')
    })

    it('handles null project_filter gracefully', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ nodes: [], edges: [] }),
      })

      await api.getGraph({ project_filter: undefined })

      const callUrl = mockFetch.mock.calls[0][0]
      expect(callUrl).not.toContain('project_filter')
    })
  })

  describe('getGraph - combined filters', () => {
    it('filters by both source and project', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ nodes: [], edges: [] }),
      })

      await api.getGraph({
        source_filter: 'claude_logs',
        project_filter: 'continuum',
      })

      const callUrl = mockFetch.mock.calls[0][0]
      expect(callUrl).toContain('source_filter=claude_logs')
      expect(callUrl).toContain('project_filter=continuum')
    })

    it('combines all filter options correctly', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ nodes: [], edges: [] }),
      })

      await api.getGraph({
        include_similarity: true,
        include_temporal: false,
        include_entity_relations: true,
        source_filter: 'manual',
        project_filter: 'docs-website',
      })

      const callUrl = mockFetch.mock.calls[0][0]
      expect(callUrl).toContain('include_similarity=true')
      expect(callUrl).toContain('include_temporal=false')
      expect(callUrl).toContain('include_entity_relations=true')
      expect(callUrl).toContain('source_filter=manual')
      expect(callUrl).toContain('project_filter=docs-website')
    })

    it('preserves existing filter behavior when adding project filter', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ nodes: [], edges: [] }),
      })

      await api.getGraph({
        include_similarity: true,
        source_filter: 'interview',
        project_filter: 'continuum',
      })

      const callUrl = mockFetch.mock.calls[0][0]
      // Verify all params are present
      expect(callUrl).toContain('include_similarity=true')
      expect(callUrl).toContain('source_filter=interview')
      expect(callUrl).toContain('project_filter=continuum')
      
      // Verify URL structure is correct
      expect(callUrl).toMatch(/\/api\/graph\?.*&.*&/)
    })

    it('handles special characters in project names', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ nodes: [], edges: [] }),
      })

      await api.getGraph({ project_filter: 'project with spaces' })

      const callUrl = mockFetch.mock.calls[0][0]
      // URLSearchParams should encode spaces
      expect(callUrl).toContain('project_filter=project')
    })
  })

  describe('GraphData response schema validation', () => {
    it('returns graph data matching GraphData interface', async () => {
      const mockGraphData = {
        nodes: [
          {
            id: 'decision-1',
            type: 'decision',
            label: 'Test Decision',
            has_embedding: true,
            data: {
              id: 'decision-1',
              trigger: 'Need to choose database',
              context: 'Building new app',
              options: ['PostgreSQL', 'MongoDB'],
              decision: 'PostgreSQL',
              rationale: 'Better for relational data',
              confidence: 0.9,
              created_at: '2024-01-01T00:00:00Z',
              source: 'claude_logs',
              project_name: 'continuum',
              entities: [],
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

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockGraphData,
      })

      const result = await api.getGraph({ project_filter: 'continuum' })

      // Verify structure matches GraphData interface
      expect(result).toHaveProperty('nodes')
      expect(result).toHaveProperty('edges')
      expect(Array.isArray(result.nodes)).toBe(true)
      expect(Array.isArray(result.edges)).toBe(true)

      // Verify node structure
      const node = result.nodes[0]
      expect(node).toHaveProperty('id')
      expect(node).toHaveProperty('type')
      expect(node).toHaveProperty('label')
      expect(node).toHaveProperty('data')

      // Verify Decision data includes project_name
      const decisionData = node.data as any
      expect(decisionData).toHaveProperty('project_name')
      expect(decisionData.project_name).toBe('continuum')

      // Verify edge structure
      const edge = result.edges[0]
      expect(edge).toHaveProperty('id')
      expect(edge).toHaveProperty('source')
      expect(edge).toHaveProperty('target')
      expect(edge).toHaveProperty('relationship')
    })

    it('handles decisions without project_name (legacy data)', async () => {
      const mockGraphData = {
        nodes: [
          {
            id: 'decision-1',
            type: 'decision',
            label: 'Test Decision',
            data: {
              id: 'decision-1',
              trigger: 'Test',
              context: 'Test',
              options: [],
              decision: 'Test',
              rationale: 'Test',
              confidence: 0.8,
              created_at: '2024-01-01T00:00:00Z',
              entities: [],
              // No project_name field (legacy)
            },
          },
        ],
        edges: [],
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockGraphData,
      })

      const result = await api.getGraph({ project_filter: 'unassigned' })

      expect(result.nodes).toHaveLength(1)
      // Should handle missing project_name gracefully
      const decisionData = result.nodes[0].data as any
      expect(decisionData.project_name).toBeUndefined()
    })
  })

  describe('Error Handling', () => {
    it('throws error on 404 for project counts', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
      })

      await expect(api.getProjectCounts()).rejects.toThrow(
        'API error: 404 Not Found'
      )
    })

    it('throws error on 403 for unauthorized access', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 403,
        statusText: 'Forbidden',
      })

      await expect(
        api.getGraph({ project_filter: 'restricted' })
      ).rejects.toThrow('API error: 403 Forbidden')
    })

    it('handles malformed JSON response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => {
          throw new SyntaxError('Unexpected token')
        },
      })

      await expect(api.getProjectCounts()).rejects.toThrow('Unexpected token')
    })
  })

  describe('Type Safety', () => {
    it('returns correct type for project counts', async () => {
      const mockCounts = { continuum: 10, unassigned: 2 }
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockCounts,
      })

      const result = await api.getProjectCounts()

      // TypeScript should infer Record<string, number>
      const keys: string[] = Object.keys(result)
      const values: number[] = Object.values(result)

      expect(keys.every((k) => typeof k === 'string')).toBe(true)
      expect(values.every((v) => typeof v === 'number')).toBe(true)
    })
  })
})
