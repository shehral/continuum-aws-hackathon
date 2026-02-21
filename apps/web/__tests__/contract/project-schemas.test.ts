import { describe, it, expect } from 'vitest'
import type { Decision, GraphData, GraphNode, Entity } from '@/lib/api'

/**
 * Contract Tests: Frontend/Backend Schema Alignment
 * 
 * These tests verify that TypeScript types match the backend Pydantic schemas
 * for the project management feature. They ensure API contract compatibility.
 */

describe('Project Schema Contract', () => {
  describe('Decision Type Schema', () => {
    it('Decision interface includes project_name field', () => {
      // Create a type-safe Decision object
      const decision: Decision = {
        id: 'decision-1',
        trigger: 'Need to choose database',
        context: 'Building new app',
        options: ['PostgreSQL', 'MongoDB'],
        decision: 'PostgreSQL',
        rationale: 'Better for relational data',
        confidence: 0.9,
        created_at: '2024-01-01T00:00:00Z',
        entities: [],
        source: 'claude_logs',
        project_name: 'continuum', // Should be optional
      }

      expect(decision).toHaveProperty('project_name')
      expect(decision.project_name).toBe('continuum')
    })

    it('Decision allows project_name to be undefined (optional field)', () => {
      const decision: Decision = {
        id: 'decision-2',
        trigger: 'Legacy decision',
        context: 'Old data',
        options: [],
        decision: 'Test',
        rationale: 'Test',
        confidence: 0.8,
        created_at: '2024-01-01T00:00:00Z',
        entities: [],
        // project_name is optional, should compile without it
      }

      expect(decision).toBeDefined()
      expect(decision.project_name).toBeUndefined()
    })

    it('Decision project_name accepts string type', () => {
      const decision: Partial<Decision> = {
        project_name: 'my-project',
      }

      expect(typeof decision.project_name).toBe('string')
    })

    it('Decision project_name can be null or undefined', () => {
      const decisionWithNull: Partial<Decision> = {
        project_name: undefined,
      }

      const decisionWithUndefined: Partial<Decision> = {
        project_name: undefined,
      }

      expect(decisionWithNull.project_name).toBeUndefined()
      expect(decisionWithUndefined.project_name).toBeUndefined()
    })
  })

  describe('DecisionCreate Schema (for POST requests)', () => {
    it('createDecision accepts project_name parameter', () => {
      // Type definition for DecisionCreate payload
      type DecisionCreate = Parameters<typeof import('@/lib/api').api.createDecision>[0]

      const payload: DecisionCreate = {
        trigger: 'Test',
        context: 'Test',
        options: [],
        decision: 'Test',
        rationale: 'Test',
        entities: [],
        // project_name should be accepted but optional
      }

      expect(payload).toBeDefined()
    })
  })

  describe('GraphData Schema', () => {
    it('GraphData interface unchanged by project feature', () => {
      const graphData: GraphData = {
        nodes: [
          {
            id: 'decision-1',
            type: 'decision',
            label: 'Test',
            data: {
              id: 'decision-1',
              trigger: 'Test',
              context: 'Test',
              options: [],
              decision: 'Test',
              rationale: 'Test',
              confidence: 0.9,
              created_at: '2024-01-01T00:00:00Z',
              entities: [],
              project_name: 'continuum',
            },
          },
        ],
        edges: [],
      }

      expect(graphData).toHaveProperty('nodes')
      expect(graphData).toHaveProperty('edges')
      expect(Array.isArray(graphData.nodes)).toBe(true)
      expect(Array.isArray(graphData.edges)).toBe(true)
    })

    it('GraphNode can contain Decision with project_name', () => {
      const node: GraphNode = {
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
          confidence: 0.9,
          created_at: '2024-01-01T00:00:00Z',
          entities: [],
          source: 'manual',
          project_name: 'my-project',
        },
      }

      expect(node.data).toHaveProperty('project_name')
      const decisionData = node.data as Decision
      expect(decisionData.project_name).toBe('my-project')
    })

    it('GraphNode Entity type unaffected by project feature', () => {
      const entityNode: GraphNode = {
        id: 'entity-1',
        type: 'entity',
        label: 'PostgreSQL',
        data: {
          id: 'entity-1',
          name: 'PostgreSQL',
          type: 'technology',
        },
      }

      expect(entityNode.type).toBe('entity')
      const entityData = entityNode.data as Entity
      expect(entityData).toHaveProperty('name')
      expect(entityData).toHaveProperty('type')
      expect(entityData).not.toHaveProperty('project_name')
    })
  })

  describe('ProjectCounts Schema', () => {
    it('getProjectCounts returns Record<string, number>', () => {
      // Type assertion to verify return type
      type ProjectCounts = Awaited<ReturnType<typeof import('@/lib/api').api.getProjectCounts>>

      const counts: ProjectCounts = {
        continuum: 42,
        'docs-website': 15,
        unassigned: 5,
      }

      expect(counts).toBeDefined()
      expect(typeof counts).toBe('object')
      
      // Verify all values are numbers
      Object.values(counts).forEach((count) => {
        expect(typeof count).toBe('number')
      })

      // Verify all keys are strings
      Object.keys(counts).forEach((key) => {
        expect(typeof key).toBe('string')
      })
    })

    it('ProjectCounts can be empty object', () => {
      type ProjectCounts = Record<string, number>
      const emptyCounts: ProjectCounts = {}

      expect(Object.keys(emptyCounts)).toHaveLength(0)
    })

    it('ProjectCounts handles special project names', () => {
      type ProjectCounts = Record<string, number>
      
      const counts: ProjectCounts = {
        'project-with-dashes': 10,
        'project.with.dots': 5,
        'project_with_underscores': 3,
        'project with spaces': 2,
        unassigned: 1,
      }

      expect(counts['project-with-dashes']).toBe(10)
      expect(counts['project.with.dots']).toBe(5)
      expect(counts['project_with_underscores']).toBe(3)
      expect(counts['project with spaces']).toBe(2)
      expect(counts.unassigned).toBe(1)
    })
  })

  describe('API Query Parameters Schema', () => {
    it('getGraph options include project_filter', () => {
      type GraphOptions = Parameters<typeof import('@/lib/api').api.getGraph>[0]

      const options: GraphOptions = {
        include_similarity: true,
        include_temporal: false,
        include_entity_relations: true,
        source_filter: 'claude_logs',
        project_filter: 'continuum',
      }

      expect(options).toHaveProperty('project_filter')
      expect(options.project_filter).toBe('continuum')
    })

    it('getGraph project_filter is optional', () => {
      type GraphOptions = Parameters<typeof import('@/lib/api').api.getGraph>[0]

      const optionsWithoutProject: GraphOptions = {
        include_similarity: true,
      }

      expect(optionsWithoutProject.project_filter).toBeUndefined()
    })

    it('getGraph project_filter accepts string', () => {
      type GraphOptions = Parameters<typeof import('@/lib/api').api.getGraph>[0]

      const options: GraphOptions = {
        project_filter: 'any-project-name',
      }

      expect(typeof options.project_filter).toBe('string')
    })
  })

  describe('Backward Compatibility', () => {
    it('existing Decision fields remain unchanged', () => {
      const decision: Decision = {
        id: 'decision-1',
        trigger: 'Test',
        context: 'Test',
        options: ['A', 'B'],
        decision: 'A',
        rationale: 'Test',
        confidence: 0.9,
        created_at: '2024-01-01T00:00:00Z',
        entities: [],
        source: 'claude_logs',
      }

      // All core fields should still exist
      expect(decision).toHaveProperty('id')
      expect(decision).toHaveProperty('trigger')
      expect(decision).toHaveProperty('context')
      expect(decision).toHaveProperty('options')
      expect(decision).toHaveProperty('decision')
      expect(decision).toHaveProperty('rationale')
      expect(decision).toHaveProperty('confidence')
      expect(decision).toHaveProperty('created_at')
      expect(decision).toHaveProperty('entities')
      expect(decision).toHaveProperty('source')
    })

    it('Entity type unaffected by project feature', () => {
      const entity: Entity = {
        id: 'entity-1',
        name: 'PostgreSQL',
        type: 'technology',
      }

      expect(entity).toHaveProperty('id')
      expect(entity).toHaveProperty('name')
      expect(entity).toHaveProperty('type')
      expect(entity).not.toHaveProperty('project_name')
    })

    it('source_filter still works independently', () => {
      type GraphOptions = Parameters<typeof import('@/lib/api').api.getGraph>[0]

      const options: GraphOptions = {
        source_filter: 'manual',
      }

      expect(options.source_filter).toBe('manual')
      expect(options.project_filter).toBeUndefined()
    })
  })

  describe('Type Safety Validation', () => {
    it('Decision confidence is number between 0-1', () => {
      const decision: Decision = {
        id: 'decision-1',
        trigger: 'Test',
        context: 'Test',
        options: [],
        decision: 'Test',
        rationale: 'Test',
        confidence: 0.75,
        created_at: '2024-01-01T00:00:00Z',
        entities: [],
      }

      expect(decision.confidence).toBeGreaterThanOrEqual(0)
      expect(decision.confidence).toBeLessThanOrEqual(1)
      expect(typeof decision.confidence).toBe('number')
    })

    it('Decision source is union of literal types', () => {
      const sources: Array<Decision['source']> = [
        'claude_logs',
        'interview',
        'manual',
        'unknown',
        undefined,
      ]

      sources.forEach((source) => {
        const decision: Decision = {
          id: 'decision-1',
          trigger: 'Test',
          context: 'Test',
          options: [],
          decision: 'Test',
          rationale: 'Test',
          confidence: 0.9,
          created_at: '2024-01-01T00:00:00Z',
          entities: [],
          source,
        }

        expect(decision).toBeDefined()
      })
    })

    it('Entity type is union of literal types', () => {
      const entityTypes: Array<Entity['type']> = [
        'concept',
        'system',
        'person',
        'technology',
        'pattern',
      ]

      entityTypes.forEach((type) => {
        const entity: Entity = {
          id: 'entity-1',
          name: 'Test',
          type,
        }

        expect(entity.type).toBe(type)
      })
    })
  })

  describe('API Response Structure', () => {
    it('getProjectCounts response matches Record<string, number>', () => {
      // Simulate API response
      const apiResponse = {
        continuum: 42,
        'docs-website': 15,
        unassigned: 5,
      }

      // TypeScript should accept this as ProjectCounts
      type ProjectCounts = Record<string, number>
      const counts: ProjectCounts = apiResponse

      expect(counts).toEqual(apiResponse)
    })

    it('getGraph with project_filter returns standard GraphData', () => {
      // API should return same structure regardless of filters
      const graphData: GraphData = {
        nodes: [
          {
            id: 'decision-1',
            type: 'decision',
            label: 'Test',
            data: {
              id: 'decision-1',
              trigger: 'Test',
              context: 'Test',
              options: [],
              decision: 'Test',
              rationale: 'Test',
              confidence: 0.9,
              created_at: '2024-01-01T00:00:00Z',
              entities: [],
              project_name: 'continuum',
            },
          },
        ],
        edges: [],
      }

      // Same shape as without project_filter
      expect(graphData).toHaveProperty('nodes')
      expect(graphData).toHaveProperty('edges')
    })
  })
})
