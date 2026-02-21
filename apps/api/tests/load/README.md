# Continuum API Load Tests

Load testing suite to verify API performance under load.

## Target Performance

- **Throughput**: 50 requests per second (RPS)
- **Latency**: p99 < 500ms
- **Success Rate**: > 99%

## Endpoints Tested

| Endpoint | Method | Weight | Description |
|----------|--------|--------|-------------|
| `/api/decisions` | GET | 30% | List decisions with pagination |
| `/api/graph` | GET | 25% | Fetch knowledge graph (paginated/full) |
| `/api/graph/search/hybrid` | POST | 20% | Hybrid semantic + lexical search |
| `/api/dashboard/stats` | GET | 25% | Dashboard statistics |

## Test Scripts

### 1. k6 Load Test (Recommended)

The k6 script provides detailed metrics, thresholds, and professional load testing capabilities.

**Installation:**
```bash
# macOS
brew install k6

# Linux
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update && sudo apt-get install k6
```

**Usage:**
```bash
# Basic run
k6 run load_test.js

# With custom VUs and duration
k6 run --vus 50 --duration 120s load_test.js

# Custom base URL
API_BASE_URL=http://localhost:8000 k6 run load_test.js

# Generate JSON output
k6 run --out json=results.json load_test.js
```

### 2. Python Load Test (Fallback)

A pure Python implementation using asyncio and aiohttp. No external tools required.

**Usage:**
```bash
# From repository root
cd apps/api
.venv/bin/python tests/load/load_test.py

# With options
.venv/bin/python tests/load/load_test.py \
    --rps 50 \
    --duration 60 \
    --base-url http://localhost:8000 \
    --output results.json
```

**Options:**
- `--base-url`: API base URL (default: http://localhost:8000)
- `--rps`: Target requests per second (default: 50)
- `--duration`: Test duration in seconds (default: 60)
- `--ramp-up`: Ramp-up time in seconds (default: 10)
- `--output`: Output JSON file (default: load_test_results.json)

## Pre-requisites

Before running load tests:

1. **Start Infrastructure:**
   ```bash
   docker-compose up -d
   ```

2. **Start the API:**
   ```bash
   cd apps/api
   .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
   ```

3. **Seed Data (Optional):**
   For meaningful load tests, ensure there's some data in the system:
   ```bash
   # Run the ingest process or create test data via API
   curl -X POST http://localhost:8000/api/decisions \
     -H "Content-Type: application/json" \
     -d '{"trigger":"Test","context":"Testing","options":["A","B"],"decision":"A","rationale":"Best option"}'
   ```

## Interpreting Results

### k6 Output

```
     ✓ decisions: status is 200
     ✓ decisions: response is array
     ✓ decisions: latency < 500ms

     checks.........................: 100.00% ✓ 1500  ✗ 0   
     data_received..................: 2.5 MB  42 kB/s
     data_sent......................: 150 kB  2.5 kB/s
     http_req_duration..............: avg=45ms  min=12ms med=38ms max=320ms p(90)=85ms p(95)=120ms p(99)=280ms
```

### Python Output

```
LATENCY PERCENTILES (ms)
------------------------------------------------------------
Endpoint              Min      Avg      P50      P95      P99      Max
------------------------------------------------------------
decisions            12.3     45.2     38.1     85.4    120.3    320.5
graph                15.2     52.3     42.5     92.1    135.2    380.2
...
------------------------------------------------------------
TEST RESULT: PASSED
  p99 latency (280.5ms) < 500ms target
  Success rate (100.0%) > 99%
```

## Performance Optimization Tips

If tests fail to meet targets:

1. **Database Optimization:**
   - Ensure Neo4j indexes are created
   - Check PostgreSQL connection pool size
   - Verify Redis is running and accessible

2. **API Configuration:**
   - Increase worker processes: `uvicorn main:app --workers 4`
   - Adjust database connection pools in config

3. **Infrastructure:**
   - Check Docker resource limits
   - Monitor CPU and memory during tests
   - Consider connection pooling

4. **Query Optimization:**
   - Review slow queries in Neo4j
   - Add appropriate indexes
   - Consider caching for frequently accessed data

## CI/CD Integration

### GitHub Actions Example

```yaml
load-test:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    
    - name: Start services
      run: docker-compose up -d
    
    - name: Wait for services
      run: sleep 10
    
    - name: Install k6
      run: |
        sudo apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
        echo "deb https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
        sudo apt-get update && sudo apt-get install k6
    
    - name: Start API
      run: |
        cd apps/api
        .venv/bin/uvicorn main:app --port 8000 &
        sleep 5
    
    - name: Run load tests
      run: k6 run apps/api/tests/load/load_test.js
```

## Related Documentation

- [Test Coverage Status](/docs/testing/coverage-status.md)
- [Cross-Browser Testing](/docs/testing/CROSS-BROWSER-TESTING.md)
