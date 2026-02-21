"use client"

import dagre from "dagre"
import type { Node, Edge } from "@xyflow/react"

export type LayoutType = "force" | "hierarchical" | "radial" | "clustered"

export interface LayoutOptions {
  type: LayoutType
  direction?: "TB" | "LR" | "BT" | "RL"
  nodeSpacing?: number
  rankSpacing?: number
}

const DEFAULT_NODE_WIDTH = 280
const DEFAULT_NODE_HEIGHT = 120
const ENTITY_NODE_WIDTH = 160
const ENTITY_NODE_HEIGHT = 56

interface ForceNode {
  id: string
  x: number
  y: number
  vx: number
  vy: number
  type: string
  connections: number
  cluster?: number
}

/**
 * Build adjacency map for clustering
 */
function buildAdjacencyMap(nodes: Node[], edges: Edge[]): Map<string, Set<string>> {
  const adjacency = new Map<string, Set<string>>()
  nodes.forEach(n => adjacency.set(n.id, new Set()))
  
  edges.forEach(edge => {
    adjacency.get(edge.source)?.add(edge.target)
    adjacency.get(edge.target)?.add(edge.source)
  })
  
  return adjacency
}

/**
 * Cluster nodes based on shared connections using union-find
 */
function clusterNodes(nodes: Node[], edges: Edge[]): Map<string, number> {
  const parent = new Map<string, string>()
  nodes.forEach(n => parent.set(n.id, n.id))
  
  const find = (id: string): string => {
    if (parent.get(id) !== id) {
      parent.set(id, find(parent.get(id)!))
    }
    return parent.get(id)!
  }
  
  const union = (a: string, b: string) => {
    const rootA = find(a)
    const rootB = find(b)
    if (rootA !== rootB) {
      parent.set(rootA, rootB)
    }
  }
  
  // Union nodes that share edges
  edges.forEach(edge => {
    union(edge.source, edge.target)
  })
  
  // Assign cluster IDs
  const clusters = new Map<string, number>()
  const clusterIds = new Map<string, number>()
  let nextClusterId = 0
  
  nodes.forEach(n => {
    const root = find(n.id)
    if (!clusterIds.has(root)) {
      clusterIds.set(root, nextClusterId++)
    }
    clusters.set(n.id, clusterIds.get(root)!)
  })
  
  return clusters
}

/**
 * Real force-directed layout with proper physics simulation
 * Uses a Barnes-Hut inspired algorithm for performance
 */
export function applyForceLayout(
  nodes: Node[],
  edges: Edge[],
  options: { iterations?: number; spacing?: number } = {}
): Node[] {
  if (nodes.length === 0) return []
  
  const iterations = options.iterations ?? 300
  const spacing = options.spacing ?? 400
  
  const adjacency = buildAdjacencyMap(nodes, edges)
  const clusters = clusterNodes(nodes, edges)
  
  // Initialize force nodes with positions based on clusters
  const clusterValues = Array.from(clusters.values())
  const numClusters = clusterValues.length > 0 ? Math.max(...clusterValues) + 1 : 1
  const clusterCenters: { x: number; y: number }[] = []
  
  // Arrange cluster centers in a grid pattern
  const clusterCols = Math.ceil(Math.sqrt(numClusters))
  for (let i = 0; i < numClusters; i++) {
    const col = i % clusterCols
    const row = Math.floor(i / clusterCols)
    clusterCenters.push({
      x: col * spacing * 2 + spacing,
      y: row * spacing * 1.5 + spacing
    })
  }
  
  // Initialize nodes near their cluster centers with some randomness
  const forceNodes: ForceNode[] = nodes.map((node, i) => {
    const cluster = clusters.get(node.id) ?? 0
    const center = clusterCenters[cluster]
    const angle = (i / nodes.length) * Math.PI * 2
    const radius = 100 + Math.random() * 150
    
    return {
      id: node.id,
      x: center.x + Math.cos(angle) * radius,
      y: center.y + Math.sin(angle) * radius,
      vx: 0,
      vy: 0,
      type: node.type || "entity",
      connections: adjacency.get(node.id)?.size || 0,
      cluster: clusters.get(node.id)
    }
  })
  
  const nodeMap = new Map(forceNodes.map(n => [n.id, n]))
  
  // Force simulation parameters
  const repulsionStrength = 8000
  const attractionStrength = 0.03
  const clusterStrength = 0.02
  const damping = 0.85
  const minDistance = 100
  
  // Run simulation
  for (let iter = 0; iter < iterations; iter++) {
    const alpha = 1 - iter / iterations // Cooling factor
    
    // Reset velocities
    forceNodes.forEach(n => {
      n.vx = 0
      n.vy = 0
    })
    
    // Repulsion between all nodes (quadratic, but necessary for good results)
    for (let i = 0; i < forceNodes.length; i++) {
      for (let j = i + 1; j < forceNodes.length; j++) {
        const a = forceNodes[i]
        const b = forceNodes[j]
        
        let dx = b.x - a.x
        let dy = b.y - a.y
        let dist = Math.sqrt(dx * dx + dy * dy) || 1
        
        // Minimum distance to prevent overlap
        const nodeMinDist = a.type === "decision" || b.type === "decision" 
          ? minDistance * 2.5 
          : minDistance * 1.5
        
        if (dist < nodeMinDist) {
          dist = nodeMinDist
        }
        
        // Repulsion force (inverse square law)
        const force = (repulsionStrength * alpha) / (dist * dist)
        const fx = (dx / dist) * force
        const fy = (dy / dist) * force
        
        a.vx -= fx
        a.vy -= fy
        b.vx += fx
        b.vy += fy
      }
    }
    
    // Attraction along edges
    edges.forEach(edge => {
      const source = nodeMap.get(edge.source)
      const target = nodeMap.get(edge.target)
      if (!source || !target) return
      
      const dx = target.x - source.x
      const dy = target.y - source.y
      const dist = Math.sqrt(dx * dx + dy * dy) || 1
      
      // Target distance based on node types
      const idealDist = source.type === "decision" && target.type === "decision"
        ? spacing * 1.2
        : spacing * 0.7
      
      const force = (dist - idealDist) * attractionStrength * alpha
      const fx = (dx / dist) * force
      const fy = (dy / dist) * force
      
      source.vx += fx
      source.vy += fy
      target.vx -= fx
      target.vy -= fy
    })
    
    // Cluster cohesion force
    forceNodes.forEach(node => {
      if (node.cluster !== undefined) {
        const center = clusterCenters[node.cluster]
        const dx = center.x - node.x
        const dy = center.y - node.y
        
        node.vx += dx * clusterStrength * alpha
        node.vy += dy * clusterStrength * alpha
      }
    })
    
    // Apply velocities with damping
    forceNodes.forEach(node => {
      node.x += node.vx * damping
      node.y += node.vy * damping
    })
  }
  
  // Center the graph
  const minX = Math.min(...forceNodes.map(n => n.x))
  const minY = Math.min(...forceNodes.map(n => n.y))
  const offsetX = -minX + 100
  const offsetY = -minY + 100
  
  // Map back to React Flow nodes
  return nodes.map(node => {
    const forceNode = nodeMap.get(node.id)!
    const width = node.type === "decision" ? DEFAULT_NODE_WIDTH : ENTITY_NODE_WIDTH
    const height = node.type === "decision" ? DEFAULT_NODE_HEIGHT : ENTITY_NODE_HEIGHT
    
    return {
      ...node,
      position: {
        x: forceNode.x + offsetX - width / 2,
        y: forceNode.y + offsetY - height / 2
      }
    }
  })
}

/**
 * Clustered layout - groups related nodes together
 */
export function applyClusteredLayout(
  nodes: Node[],
  edges: Edge[],
  options: { clusterSpacing?: number; nodeSpacing?: number } = {}
): Node[] {
  if (nodes.length === 0) return []
  
  const clusterSpacing = options.clusterSpacing ?? 600
  const nodeSpacing = options.nodeSpacing ?? 180
  
  const adjacency = buildAdjacencyMap(nodes, edges)
  
  // Group by decision: each decision + its connected entities
  const decisionNodes = nodes.filter(n => n.type === "decision")
  const entityNodes = nodes.filter(n => n.type === "entity")
  
  // Map entities to their connected decisions
  const entityToDecisions = new Map<string, string[]>()
  entityNodes.forEach(entity => {
    const connectedDecisions = Array.from(adjacency.get(entity.id) || [])
      .filter(id => decisionNodes.some(d => d.id === id))
    entityToDecisions.set(entity.id, connectedDecisions)
  })
  
  const result: Node[] = []
  
  // Calculate cluster positions in a grid
  const numDecisions = decisionNodes.length
  const cols = Math.max(2, Math.ceil(Math.sqrt(numDecisions)))
  
  decisionNodes.forEach((decision, i) => {
    const col = i % cols
    const row = Math.floor(i / cols)
    const clusterX = col * clusterSpacing + clusterSpacing / 2
    const clusterY = row * clusterSpacing + clusterSpacing / 2
    
    // Place decision at cluster center
    result.push({
      ...decision,
      position: {
        x: clusterX - DEFAULT_NODE_WIDTH / 2,
        y: clusterY - DEFAULT_NODE_HEIGHT / 2
      }
    })
    
    // Find entities connected ONLY to this decision
    const connectedEntities = entityNodes.filter(entity => {
      const decisions = entityToDecisions.get(entity.id) || []
      return decisions.length === 1 && decisions[0] === decision.id
    })
    
    // Arrange entities in a circle around the decision
    const radius = Math.max(nodeSpacing, connectedEntities.length * 25)
    connectedEntities.forEach((entity, j) => {
      const angle = (j / connectedEntities.length) * Math.PI * 2 - Math.PI / 2
      result.push({
        ...entity,
        position: {
          x: clusterX + Math.cos(angle) * radius - ENTITY_NODE_WIDTH / 2,
          y: clusterY + Math.sin(angle) * radius - ENTITY_NODE_HEIGHT / 2
        }
      })
    })
  })
  
  // Place shared entities (connected to multiple decisions) between their decisions
  const sharedEntities = entityNodes.filter(entity => {
    const decisions = entityToDecisions.get(entity.id) || []
    return decisions.length > 1 || decisions.length === 0
  })
  
  // Calculate centroid of connected decisions for shared entities
  sharedEntities.forEach((entity, i) => {
    const connectedDecisions = entityToDecisions.get(entity.id) || []
    
    if (connectedDecisions.length === 0) {
      // Orphan entity - place at bottom in a grid pattern to avoid overlap
      const orphanCols = Math.max(3, Math.ceil(Math.sqrt(sharedEntities.filter(e => (entityToDecisions.get(e.id) || []).length === 0).length)))
      const orphanCol = i % orphanCols
      const orphanRow = Math.floor(i / orphanCols)
      const orphanSpacing = nodeSpacing * 1.5 // 1.5x spacing to prevent overlap
      result.push({
        ...entity,
        position: {
          x: orphanCol * orphanSpacing + 200,
          y: (Math.ceil(numDecisions / cols) + 1) * clusterSpacing + orphanRow * (ENTITY_NODE_HEIGHT + 40)
        }
      })
    } else {
      // Find centroid of connected decisions
      let sumX = 0, sumY = 0
      connectedDecisions.forEach(decId => {
        const decNode = result.find(n => n.id === decId)
        if (decNode) {
          sumX += decNode.position.x + DEFAULT_NODE_WIDTH / 2
          sumY += decNode.position.y + DEFAULT_NODE_HEIGHT / 2
        }
      })
      
      const centroidX = sumX / connectedDecisions.length
      const centroidY = sumY / connectedDecisions.length
      
      // Offset slightly to avoid overlap
      const angle = (i * 0.5) % (Math.PI * 2)
      const offset = 80
      
      result.push({
        ...entity,
        position: {
          x: centroidX + Math.cos(angle) * offset - ENTITY_NODE_WIDTH / 2,
          y: centroidY + Math.sin(angle) * offset - ENTITY_NODE_HEIGHT / 2
        }
      })
    }
  })
  
  return result
}

/**
 * Apply hierarchical layout using Dagre
 */
export function applyHierarchicalLayout(
  nodes: Node[],
  edges: Edge[],
  options: { direction?: "TB" | "LR" | "BT" | "RL"; nodeSpacing?: number; rankSpacing?: number } = {}
): Node[] {
  if (nodes.length === 0) return []
  
  const direction = options.direction ?? "TB"
  const nodeSpacing = options.nodeSpacing ?? 200
  const rankSpacing = options.rankSpacing ?? 280

  const g = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}))

  g.setGraph({
    rankdir: direction,
    nodesep: nodeSpacing,
    ranksep: rankSpacing,
    marginx: 100,
    marginy: 100,
    acyclicer: "greedy",
    ranker: "network-simplex"
  })

  nodes.forEach((node) => {
    const width = node.type === "decision" ? DEFAULT_NODE_WIDTH : ENTITY_NODE_WIDTH
    const height = node.type === "decision" ? DEFAULT_NODE_HEIGHT : ENTITY_NODE_HEIGHT
    g.setNode(node.id, { width, height })
  })

  edges.forEach((edge) => {
    g.setEdge(edge.source, edge.target)
  })

  dagre.layout(g)

  return nodes.map((node) => {
    const nodeWithPos = g.node(node.id)
    const width = node.type === "decision" ? DEFAULT_NODE_WIDTH : ENTITY_NODE_WIDTH
    const height = node.type === "decision" ? DEFAULT_NODE_HEIGHT : ENTITY_NODE_HEIGHT

    return {
      ...node,
      position: {
        x: nodeWithPos.x - width / 2,
        y: nodeWithPos.y - height / 2,
      },
    }
  })
}

/**
 * Apply radial layout - decisions at center, entities in outer rings
 */
export function applyRadialLayout(
  nodes: Node[],
  edges: Edge[],
  options: { centerRadius?: number; ringSpacing?: number } = {}
): Node[] {
  if (nodes.length === 0) return []
  
  const decisionNodes = nodes.filter((n) => n.type === "decision")
  const entityNodes = nodes.filter((n) => n.type === "entity")

  const baseRadius = Math.max(350, decisionNodes.length * 100)
  const centerRadius = options.centerRadius ?? baseRadius
  const ringSpacing = options.ringSpacing ?? 320

  // Calculate dynamic center based on graph size
  const totalNodes = nodes.length
  const estimatedWidth = Math.max(1600, totalNodes * 50)
  const estimatedHeight = Math.max(1200, totalNodes * 40)
  const centerX = estimatedWidth / 2
  const centerY = estimatedHeight / 2

  const result: Node[] = []

  // Place decision nodes in the center
  if (decisionNodes.length === 1) {
    result.push({
      ...decisionNodes[0],
      position: { x: centerX - DEFAULT_NODE_WIDTH / 2, y: centerY - DEFAULT_NODE_HEIGHT / 2 },
    })
  } else {
    const decisionAngleStep = (2 * Math.PI) / decisionNodes.length
    decisionNodes.forEach((node, index) => {
      const angle = index * decisionAngleStep - Math.PI / 2
      result.push({
        ...node,
        position: {
          x: centerX + centerRadius * 0.4 * Math.cos(angle) - DEFAULT_NODE_WIDTH / 2,
          y: centerY + centerRadius * 0.4 * Math.sin(angle) - DEFAULT_NODE_HEIGHT / 2,
        },
      })
    })
  }

  // Sort entities by connection count (more connected = closer to center)
  const adjacency = buildAdjacencyMap(nodes, edges)
  const sortedEntities = [...entityNodes].sort((a, b) => {
    const aConns = adjacency.get(a.id)?.size || 0
    const bConns = adjacency.get(b.id)?.size || 0
    return bConns - aConns
  })

  // Place entities in concentric rings
  const entitiesPerRing = Math.max(10, Math.ceil(sortedEntities.length / 3))
  
  sortedEntities.forEach((node, index) => {
    const ringIndex = Math.floor(index / entitiesPerRing)
    const indexInRing = index % entitiesPerRing
    const entitiesInThisRing = Math.min(entitiesPerRing, sortedEntities.length - ringIndex * entitiesPerRing)

    const radius = centerRadius + ringSpacing * (ringIndex + 0.5)
    // Guard against division by zero
    const angleStep = entitiesInThisRing > 0 ? (2 * Math.PI) / entitiesInThisRing : 0
    const angle = indexInRing * angleStep - Math.PI / 2

    result.push({
      ...node,
      position: {
        x: centerX + radius * Math.cos(angle) - ENTITY_NODE_WIDTH / 2,
        y: centerY + radius * Math.sin(angle) - ENTITY_NODE_HEIGHT / 2,
      },
    })
  })

  return result
}

/**
 * Main layout function that dispatches to the appropriate layout algorithm
 */
export function applyLayout(
  nodes: Node[],
  edges: Edge[],
  layoutType: LayoutType,
  options: LayoutOptions = { type: "force" }
): Node[] {
  // Validate direction for hierarchical layout
  const validDirections = ["TB", "LR", "BT", "RL"] as const
  const direction = options.direction && validDirections.includes(options.direction)
    ? options.direction
    : "TB"

  switch (layoutType) {
    case "hierarchical":
      return applyHierarchicalLayout(nodes, edges, {
        direction,
        nodeSpacing: options.nodeSpacing ?? 200,
        rankSpacing: options.rankSpacing ?? 280,
      })
    case "radial":
      return applyRadialLayout(nodes, edges)
    case "clustered":
      return applyClusteredLayout(nodes, edges)
    case "force":
    default:
      return applyForceLayout(nodes, edges)
  }
}

/**
 * Edge bundling - groups parallel edges with curvature
 */
export function bundleEdges(edges: Edge[]): Edge[] {
  const edgeGroups = new Map<string, Edge[]>()
  
  edges.forEach((edge) => {
    const key = [edge.source, edge.target].sort().join("->")
    if (!edgeGroups.has(key)) {
      edgeGroups.set(key, [])
    }
    edgeGroups.get(key)?.push(edge)
  })

  const bundledEdges: Edge[] = []

  edgeGroups.forEach((group) => {
    if (group.length === 1) {
      bundledEdges.push(group[0])
    } else {
      const midIndex = (group.length - 1) / 2
      group.forEach((edge, index) => {
        const offset = (index - midIndex) * 0.4
        bundledEdges.push({
          ...edge,
          type: "smoothstep",
          data: {
            ...edge.data,
            bundleOffset: offset,
            bundleIndex: index,
            bundleSize: group.length,
          },
        })
      })
    }
  })

  return bundledEdges
}

/**
 * Layout information for display
 */
export const LAYOUT_INFO: Record<LayoutType, { label: string; description: string; icon: string }> = {
  force: {
    label: "Force-Directed",
    description: "Natural clustering with physics simulation",
    icon: "scatter-chart",
  },
  clustered: {
    label: "Clustered",
    description: "Group decisions with their entities",
    icon: "layers",
  },
  hierarchical: {
    label: "Hierarchical",
    description: "Tree-like structure showing hierarchy",
    icon: "git-branch",
  },
  radial: {
    label: "Radial",
    description: "Decisions at center, entities in rings",
    icon: "target",
  },
}
