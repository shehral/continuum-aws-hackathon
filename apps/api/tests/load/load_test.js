/**
 * Continuum API Load Test Script
 * 
 * Target: 50 RPS with <500ms p99 latency
 * 
 * Usage:
 *   brew install k6  # if not already installed
 *   k6 run load_test.js
 *   
 *   # With custom options:
 *   k6 run --vus 50 --duration 60s load_test.js
 *   
 *   # With HTML report:
 *   k6 run --out json=results.json load_test.js
 * 
 * Environment Variables:
 *   API_BASE_URL - Base URL of the API (default: http://localhost:8000)
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const decisionsLatency = new Trend('decisions_latency', true);
const graphLatency = new Trend('graph_latency', true);
const hybridSearchLatency = new Trend('hybrid_search_latency', true);
const dashboardStatsLatency = new Trend('dashboard_stats_latency', true);
const requestCounter = new Counter('requests');

// Test configuration
export const options = {
  // Ramp up to 50 VUs over 30s, hold for 2 minutes, ramp down
  stages: [
    { duration: '30s', target: 50 },   // Ramp up to 50 users
    { duration: '2m', target: 50 },    // Stay at 50 users
    { duration: '30s', target: 0 },    // Ramp down
  ],
  
  // Thresholds - fail the test if these are not met
  thresholds: {
    // Overall HTTP request duration
    http_req_duration: [
      'p(95)<400',   // 95% of requests under 400ms
      'p(99)<500',   // 99% of requests under 500ms (target)
    ],
    
    // Error rate should be less than 1%
    errors: ['rate<0.01'],
    
    // Endpoint-specific latency thresholds
    decisions_latency: ['p(99)<500'],
    graph_latency: ['p(99)<500'],
    hybrid_search_latency: ['p(99)<600'],  // Search can be slightly slower
    dashboard_stats_latency: ['p(99)<500'],
    
    // Request rate - should achieve ~50 RPS at peak
    http_reqs: ['rate>=40'],
  },
  
  // Tags for better organization in results
  tags: {
    testType: 'load',
    application: 'continuum-api',
  },
};

// Configuration
const BASE_URL = __ENV.API_BASE_URL || 'http://localhost:8000';

// Sample search queries for testing
const searchQueries = [
  'PostgreSQL',
  'authentication',
  'database',
  'API',
  'architecture',
  'security',
  'performance',
  'testing',
  'deployment',
  'monitoring',
];

// Common headers
const headers = {
  'Content-Type': 'application/json',
  'Accept': 'application/json',
};

/**
 * Health check to verify API is available
 */
export function setup() {
  const healthCheck = http.get(`${BASE_URL}/health`);
  
  if (healthCheck.status !== 200) {
    throw new Error(`API is not healthy. Status: ${healthCheck.status}`);
  }
  
  console.log(`API Health Check: ${healthCheck.status} - Ready for load testing`);
  console.log(`Base URL: ${BASE_URL}`);
  
  return {
    baseUrl: BASE_URL,
    headers: headers,
  };
}

/**
 * Main test function - executed by each VU
 */
export default function(data) {
  // Randomly select which endpoint to test (weighted distribution)
  const rand = Math.random();
  
  if (rand < 0.30) {
    // 30% - GET /api/decisions
    testDecisionsEndpoint(data);
  } else if (rand < 0.55) {
    // 25% - GET /api/graph
    testGraphEndpoint(data);
  } else if (rand < 0.75) {
    // 20% - POST /api/graph/search/hybrid
    testHybridSearchEndpoint(data);
  } else {
    // 25% - GET /api/dashboard/stats
    testDashboardStatsEndpoint(data);
  }
  
  // Small sleep to prevent overwhelming the server
  sleep(0.1 + Math.random() * 0.2);
}

/**
 * Test GET /api/decisions
 */
function testDecisionsEndpoint(data) {
  group('GET /api/decisions', function() {
    const limit = Math.floor(Math.random() * 50) + 10; // 10-60
    const offset = Math.floor(Math.random() * 5) * 10;  // 0, 10, 20, 30, 40
    
    const start = Date.now();
    const response = http.get(
      `${data.baseUrl}/api/decisions?limit=${limit}&offset=${offset}`,
      { headers: data.headers, tags: { endpoint: 'decisions' } }
    );
    const duration = Date.now() - start;
    
    requestCounter.add(1);
    decisionsLatency.add(duration);
    
    const success = check(response, {
      'decisions: status is 200': (r) => r.status === 200,
      'decisions: response is array': (r) => {
        try {
          const body = JSON.parse(r.body);
          return Array.isArray(body);
        } catch {
          return false;
        }
      },
      'decisions: latency < 500ms': () => duration < 500,
    });
    
    errorRate.add(!success);
  });
}

/**
 * Test GET /api/graph
 */
function testGraphEndpoint(data) {
  group('GET /api/graph', function() {
    // Test both paginated and full graph endpoints
    const usePaginated = Math.random() < 0.8; // 80% paginated
    
    let url;
    let tags;
    
    if (usePaginated) {
      const page = Math.floor(Math.random() * 3) + 1;
      const pageSize = Math.floor(Math.random() * 50) + 50; // 50-100
      url = `${data.baseUrl}/api/graph?page=${page}&page_size=${pageSize}`;
      tags = { endpoint: 'graph_paginated' };
    } else {
      url = `${data.baseUrl}/api/graph/all`;
      tags = { endpoint: 'graph_all' };
    }
    
    const start = Date.now();
    const response = http.get(url, { headers: data.headers, tags: tags });
    const duration = Date.now() - start;
    
    requestCounter.add(1);
    graphLatency.add(duration);
    
    const success = check(response, {
      'graph: status is 200': (r) => r.status === 200,
      'graph: has nodes array': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.nodes !== undefined && Array.isArray(body.nodes);
        } catch {
          return false;
        }
      },
      'graph: has edges array': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.edges !== undefined && Array.isArray(body.edges);
        } catch {
          return false;
        }
      },
      'graph: latency < 500ms': () => duration < 500,
    });
    
    errorRate.add(!success);
  });
}

/**
 * Test POST /api/graph/search/hybrid
 */
function testHybridSearchEndpoint(data) {
  group('POST /api/graph/search/hybrid', function() {
    const query = searchQueries[Math.floor(Math.random() * searchQueries.length)];
    const topK = Math.floor(Math.random() * 10) + 5; // 5-15
    
    const payload = JSON.stringify({
      query: query,
      top_k: topK,
      alpha: 0.3,
      threshold: 0.1,
      search_decisions: true,
      search_entities: Math.random() < 0.5,
    });
    
    const start = Date.now();
    const response = http.post(
      `${data.baseUrl}/api/graph/search/hybrid`,
      payload,
      { headers: data.headers, tags: { endpoint: 'hybrid_search' } }
    );
    const duration = Date.now() - start;
    
    requestCounter.add(1);
    hybridSearchLatency.add(duration);
    
    const success = check(response, {
      'hybrid_search: status is 200': (r) => r.status === 200,
      'hybrid_search: response is array': (r) => {
        try {
          const body = JSON.parse(r.body);
          return Array.isArray(body);
        } catch {
          return false;
        }
      },
      'hybrid_search: latency < 600ms': () => duration < 600,
    });
    
    errorRate.add(!success);
  });
}

/**
 * Test GET /api/dashboard/stats
 */
function testDashboardStatsEndpoint(data) {
  group('GET /api/dashboard/stats', function() {
    const start = Date.now();
    const response = http.get(
      `${data.baseUrl}/api/dashboard/stats`,
      { headers: data.headers, tags: { endpoint: 'dashboard_stats' } }
    );
    const duration = Date.now() - start;
    
    requestCounter.add(1);
    dashboardStatsLatency.add(duration);
    
    const success = check(response, {
      'dashboard_stats: status is 200': (r) => r.status === 200,
      'dashboard_stats: has total_decisions': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.total_decisions !== undefined;
        } catch {
          return false;
        }
      },
      'dashboard_stats: has total_entities': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.total_entities !== undefined;
        } catch {
          return false;
        }
      },
      'dashboard_stats: latency < 500ms': () => duration < 500,
    });
    
    errorRate.add(!success);
  });
}

/**
 * Teardown - summary of results
 */
export function teardown(data) {
  console.log('\n========================================');
  console.log('Load Test Complete');
  console.log('========================================');
  console.log(`Base URL: ${data.baseUrl}`);
  console.log('\nTarget: 50 RPS with p99 < 500ms');
  console.log('\nSee detailed metrics above.');
  console.log('========================================\n');
}
