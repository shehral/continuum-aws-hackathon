# Continuum Kubernetes Deployment

This directory contains Kubernetes manifests for deploying Continuum to a Kubernetes cluster using Kustomize.

## Directory Structure

```
k8s/
├── base/                    # Base manifests (shared across environments)
│   ├── kustomization.yaml   # Kustomize configuration
│   ├── namespace.yaml       # Namespace definition
│   ├── configmap.yaml       # Non-sensitive configuration
│   ├── secrets.yaml         # Secret template (placeholders only)
│   ├── api-deployment.yaml  # FastAPI backend deployment
│   ├── api-service.yaml     # API ClusterIP service
│   ├── web-deployment.yaml  # Next.js frontend deployment
│   ├── web-service.yaml     # Web ClusterIP service
│   ├── ingress.yaml         # Ingress for external traffic
│   ├── hpa.yaml             # HorizontalPodAutoscalers
│   ├── pdb.yaml             # PodDisruptionBudgets
│   └── networkpolicy.yaml   # Network security policies
├── overlays/
│   ├── development/         # Development environment overrides
│   │   └── kustomization.yaml
│   └── production/          # Production environment overrides
│       └── kustomization.yaml
└── README.md
```

## Prerequisites

1. **Kubernetes cluster** (1.25+)
2. **kubectl** configured to access the cluster
3. **Kustomize** (built into kubectl 1.14+)
4. **Container registry** with built images
5. **Ingress controller** (nginx-ingress recommended)

## Building Docker Images

### API (FastAPI Backend)

```bash
# From repository root
cd apps/api
docker build -t continuum/api:latest .

# Tag for your registry
docker tag continuum/api:latest ghcr.io/your-org/continuum-api:v0.1.0
docker push ghcr.io/your-org/continuum-api:v0.1.0
```

### Web (Next.js Frontend)

```bash
# From repository root
cd apps/web

# Build with API URL for production
docker build \
  --build-arg NEXT_PUBLIC_API_URL=https://api.continuum.example.com \
  -t continuum/web:latest .

# Tag for your registry
docker tag continuum/web:latest ghcr.io/your-org/continuum-web:v0.1.0
docker push ghcr.io/your-org/continuum-web:v0.1.0
```

## Creating Secrets

**IMPORTANT**: Never commit actual secrets to version control!

### Option 1: Manual Creation

```bash
# Create namespace first
kubectl create namespace continuum

# Create secrets from literals
kubectl create secret generic continuum-secrets \
  --from-literal=DATABASE_URL="postgresql+asyncpg://user:pass@postgres:5432/continuum" \
  --from-literal=NEO4J_URI="bolt://neo4j:7687" \
  --from-literal=NEO4J_USER="neo4j" \
  --from-literal=NEO4J_PASSWORD="your-neo4j-password" \
  --from-literal=REDIS_URL="redis://:your-redis-password@redis:6379" \
  --from-literal=NVIDIA_API_KEY="nvapi-xxx" \
  --from-literal=NVIDIA_EMBEDDING_API_KEY="nvapi-xxx" \
  --from-literal=SECRET_KEY="your-jwt-secret-key" \
  --from-literal=NEXTAUTH_SECRET="your-nextauth-secret" \
  --from-literal=NEXTAUTH_URL="https://continuum.example.com" \
  -n continuum
```

### Option 2: External Secrets Operator (Recommended for Production)

```yaml
# external-secret.yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: continuum-secrets
  namespace: continuum
spec:
  refreshInterval: 1h
  secretStoreRef:
    kind: ClusterSecretStore
    name: aws-secrets-manager
  target:
    name: continuum-secrets
  data:
    - secretKey: DATABASE_URL
      remoteRef:
        key: continuum/database-url
    - secretKey: NVIDIA_API_KEY
      remoteRef:
        key: continuum/nvidia-api-key
    # ... other secrets
```

### Option 3: Sealed Secrets

```bash
# Install kubeseal
brew install kubeseal

# Create sealed secret
kubectl create secret generic continuum-secrets \
  --from-literal=DATABASE_URL=xxx \
  --dry-run=client -o yaml | kubeseal > sealed-secrets.yaml

# Apply sealed secret
kubectl apply -f sealed-secrets.yaml
```

## Deployment

### Development Environment

```bash
# Preview what will be deployed
kubectl kustomize k8s/overlays/development

# Deploy
kubectl apply -k k8s/overlays/development

# Check deployment status
kubectl get pods -n continuum -w
```

### Production Environment

```bash
# Preview what will be deployed
kubectl kustomize k8s/overlays/production

# Deploy
kubectl apply -k k8s/overlays/production

# Check deployment status
kubectl get pods -n continuum -w
kubectl get hpa -n continuum
kubectl get ingress -n continuum
```

## Post-Deployment Verification

```bash
# Check all resources
kubectl get all -n continuum

# Check pod health
kubectl describe pods -n continuum

# View logs
kubectl logs -n continuum -l app.kubernetes.io/component=api -f
kubectl logs -n continuum -l app.kubernetes.io/component=web -f

# Test health endpoints
kubectl port-forward -n continuum svc/continuum-api 8000:8000
curl http://localhost:8000/health/ready
curl http://localhost:8000/health/live

# Test web frontend
kubectl port-forward -n continuum svc/continuum-web 3000:3000
curl http://localhost:3000/api/health
```

## Scaling

### Manual Scaling

```bash
# Scale API
kubectl scale deployment continuum-api -n continuum --replicas=5

# Scale Web
kubectl scale deployment continuum-web -n continuum --replicas=3
```

### Auto-Scaling

HPA is configured to automatically scale based on CPU/memory. View current status:

```bash
kubectl get hpa -n continuum
kubectl describe hpa continuum-api-hpa -n continuum
```

## Updating

### Rolling Update

```bash
# Update image tag in overlay and apply
kubectl apply -k k8s/overlays/production

# Or update image directly
kubectl set image deployment/continuum-api \
  api=ghcr.io/your-org/continuum-api:v0.2.0 \
  -n continuum
```

### Rollback

```bash
# View rollout history
kubectl rollout history deployment/continuum-api -n continuum

# Rollback to previous version
kubectl rollout undo deployment/continuum-api -n continuum

# Rollback to specific revision
kubectl rollout undo deployment/continuum-api -n continuum --to-revision=2
```

## Monitoring

### Resource Usage

```bash
# Pod resource usage (requires metrics-server)
kubectl top pods -n continuum
kubectl top nodes
```

### Health Endpoints

| Endpoint | Purpose | Expected Response |
|----------|---------|-------------------|
| `/health/live` | Liveness probe | `{"alive": true}` |
| `/health/ready` | Readiness probe | `{"ready": true, "checks": {...}}` |
| `/health/circuits` | Circuit breaker status | Circuit breaker states |

## Troubleshooting

### Pod not starting

```bash
# Check events
kubectl describe pod <pod-name> -n continuum

# Check logs
kubectl logs <pod-name> -n continuum --previous
```

### Database connection issues

```bash
# Verify secrets are mounted
kubectl exec -it <pod-name> -n continuum -- env | grep DATABASE

# Test connectivity from pod
kubectl exec -it <pod-name> -n continuum -- nc -zv postgres 5432
```

### Ingress not working

```bash
# Check ingress status
kubectl describe ingress continuum-ingress -n continuum

# Check ingress controller logs
kubectl logs -n ingress-nginx -l app.kubernetes.io/component=controller
```

## Security Considerations

1. **Secrets**: Use External Secrets Operator or Sealed Secrets in production
2. **NetworkPolicy**: Restricts pod-to-pod communication (requires CNI support)
3. **PodSecurityContext**: Runs as non-root user
4. **ReadOnlyRootFilesystem**: API runs with read-only filesystem
5. **Resource Limits**: Prevents resource exhaustion
6. **TLS**: Enable in production overlay

## Architecture

```
                    ┌─────────────────┐
                    │    Ingress      │
                    │  (nginx/ALB)    │
                    └────────┬────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
          ▼                  ▼                  │
    ┌───────────┐      ┌───────────┐            │
    │  Web Pod  │──────│  API Pod  │            │
    │  (Next.js)│      │ (FastAPI) │            │
    └───────────┘      └─────┬─────┘            │
                             │                  │
          ┌──────────────────┼──────────────────┤
          │                  │                  │
          ▼                  ▼                  ▼
    ┌───────────┐      ┌───────────┐      ┌───────────┐
    │ PostgreSQL│      │   Neo4j   │      │   Redis   │
    └───────────┘      └───────────┘      └───────────┘
```

## Next Steps

1. Set up TLS certificates (cert-manager recommended)
2. Configure monitoring (Prometheus + Grafana)
3. Set up log aggregation (Loki, ELK, or cloud logging)
4. Configure alerting rules
5. Set up CI/CD pipeline for automated deployments
