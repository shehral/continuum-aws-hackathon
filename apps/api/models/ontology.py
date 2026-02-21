"""Ontology schema definition for knowledge graph entities and relationships."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class EntityType(Enum):
    """Types of entities that can be extracted from decisions."""

    TECHNOLOGY = "technology"      # PostgreSQL, React, Neo4j
    CONCEPT = "concept"            # microservices, REST API, caching
    PATTERN = "pattern"            # singleton, repository pattern
    SYSTEM = "system"              # authentication system, payment gateway
    PERSON = "person"              # team members, stakeholders
    ORGANIZATION = "organization"  # companies, teams
    FILE = "file"                  # Actual source files / modules in the codebase


class RelationType(Enum):
    """Types of relationships in the knowledge graph."""

    # Entity-Entity relationships
    IS_A = "IS_A"  # X is a type/category of Y
    PART_OF = "PART_OF"  # X is a component of Y
    DEPENDS_ON = "DEPENDS_ON"  # X requires Y
    RELATED_TO = "RELATED_TO"  # X is related to Y (general)
    ALTERNATIVE_TO = "ALTERNATIVE_TO"  # X can be used instead of Y

    # KG-P2-1: Extended entity-entity relationships
    ENABLES = "ENABLES"  # X makes Y possible (e.g., "Docker ENABLES containerization")
    PREVENTS = "PREVENTS"  # X blocks/prevents Y (e.g., "Rate limiting PREVENTS abuse")
    REQUIRES = "REQUIRES"  # X needs Y to work (stronger than DEPENDS_ON, mandatory)
    REFINES = "REFINES"  # X is a more specific version of Y (e.g., "FastAPI REFINES Starlette")

    # Decision-Entity relationships
    INVOLVES = "INVOLVES"  # Decision involves this entity

    # Decision-Decision relationships
    SIMILAR_TO = "SIMILAR_TO"  # Decisions have similar content
    INFLUENCED_BY = "INFLUENCED_BY"  # Decision was influenced by earlier one
    SUPERSEDES = "SUPERSEDES"  # New decision replaces older one
    CONTRADICTS = "CONTRADICTS"  # Decisions conflict with each other

    # Temporal ordering (RQ1.3)
    FOLLOWS = "FOLLOWS"    # Decision B follows Decision A (happens after in conversation)
    PRECEDES = "PRECEDES"  # Decision A precedes Decision B (happens before)

    # Codebase connectivity (Part 4.1, 4.2, 4.3)
    AFFECTS = "AFFECTS"              # Decision → CodeEntity (file/module affected by this decision)
    IMPLEMENTED_BY = "IMPLEMENTED_BY"  # Decision → CommitNode (git commit that implemented it)
    TOUCHES = "TOUCHES"              # CommitNode → CodeEntity (files changed by commit)
    REJECTED_BY = "REJECTED_BY"      # CandidateDecision → DecisionTrace (rejected alternative)


# Valid relationship types per source/target node type combinations (KG-P0-3)
# This defines semantic constraints on which relationships are valid between entity types.
# Format: RelationType -> set of (source_type, target_type) tuples
VALID_ENTITY_RELATIONSHIPS: dict[str, set[tuple[str, str]]] = {
    # IS_A: X is a type/kind of Y (taxonomic relationship)
    # e.g., "PostgreSQL IS_A database", "React IS_A framework"
    "IS_A": {
        ("technology", "concept"),  # PostgreSQL IS_A database
        ("technology", "technology"),  # TypeScript IS_A JavaScript (superset)
        ("pattern", "concept"),  # Repository pattern IS_A design pattern
        ("system", "concept"),  # Auth service IS_A microservice
        ("concept", "concept"),  # REST API IS_A API style
    },
    # PART_OF: X is a component/element of Y
    # e.g., "React PART_OF frontend stack", "Redis PART_OF caching layer"
    "PART_OF": {
        ("technology", "system"),  # React PART_OF frontend
        ("technology", "technology"),  # Redux PART_OF React ecosystem
        ("technology", "concept"),  # PostgreSQL PART_OF backend stack
        ("system", "system"),  # Auth service PART_OF platform
        ("pattern", "system"),  # Repository pattern PART_OF data layer
        ("concept", "concept"),  # Caching PART_OF performance strategy
        ("person", "organization"),  # Alice PART_OF Engineering team
    },
    # DEPENDS_ON: X requires Y to function
    # e.g., "Next.js DEPENDS_ON React", "FastAPI DEPENDS_ON Python"
    "DEPENDS_ON": {
        ("technology", "technology"),  # Next.js DEPENDS_ON React
        ("system", "technology"),  # Auth service DEPENDS_ON Redis
        ("system", "system"),  # Frontend DEPENDS_ON API gateway
        ("pattern", "technology"),  # Repository pattern DEPENDS_ON ORM
        ("pattern", "concept"),  # CQRS DEPENDS_ON event sourcing
    },
    # RELATED_TO: General association (fallback for unclear relationships)
    # Any entity type can be related to any other
    "RELATED_TO": {
        ("technology", "technology"),
        ("technology", "concept"),
        ("technology", "pattern"),
        ("technology", "system"),
        ("concept", "concept"),
        ("concept", "pattern"),
        ("concept", "system"),
        ("pattern", "pattern"),
        ("pattern", "system"),
        ("system", "system"),
        ("person", "technology"),
        ("person", "system"),
        ("organization", "technology"),
        ("organization", "system"),
    },
    # ALTERNATIVE_TO: X can substitute for Y (symmetric relationship)
    # e.g., "MongoDB ALTERNATIVE_TO PostgreSQL", "Vue ALTERNATIVE_TO React"
    "ALTERNATIVE_TO": {
        ("technology", "technology"),  # MongoDB ALTERNATIVE_TO PostgreSQL
        ("pattern", "pattern"),  # CQRS ALTERNATIVE_TO CRUD
        ("system", "system"),  # Kafka ALTERNATIVE_TO RabbitMQ
        ("concept", "concept"),  # REST ALTERNATIVE_TO GraphQL
    },
    # KG-P2-1: ENABLES - X makes Y possible or practical
    # e.g., "Docker ENABLES containerization", "Redis ENABLES caching"
    "ENABLES": {
        ("technology", "concept"),  # Docker ENABLES containerization
        ("technology", "pattern"),  # ORM ENABLES repository pattern
        ("technology", "system"),  # Kubernetes ENABLES microservices deployment
        ("pattern", "concept"),  # Event sourcing ENABLES audit trails
        ("system", "concept"),  # API gateway ENABLES centralized auth
        ("system", "system"),  # Message queue ENABLES async processing
        ("concept", "concept"),  # Caching ENABLES high performance
    },
    # KG-P2-1: PREVENTS - X blocks or prevents Y
    # e.g., "Rate limiting PREVENTS abuse", "Type checking PREVENTS runtime errors"
    "PREVENTS": {
        ("technology", "concept"),  # TypeScript PREVENTS type errors
        ("pattern", "concept"),  # Circuit breaker PREVENTS cascade failures
        ("system", "concept"),  # WAF PREVENTS attacks
        ("concept", "concept"),  # Rate limiting PREVENTS abuse
    },
    # KG-P2-1: REQUIRES - X strictly needs Y (mandatory dependency)
    # Stronger than DEPENDS_ON - indicates hard requirement
    # e.g., "GraphQL REQUIRES schema definition", "OAuth REQUIRES HTTPS"
    "REQUIRES": {
        ("technology", "technology"),  # Next.js REQUIRES Node.js
        ("technology", "concept"),  # OAuth REQUIRES HTTPS
        ("pattern", "technology"),  # CQRS REQUIRES event store
        ("pattern", "concept"),  # Microservices REQUIRES service discovery
        ("system", "technology"),  # Container orchestration REQUIRES container runtime
        ("system", "concept"),  # Real-time system REQUIRES low latency
    },
    # KG-P2-1: REFINES - X is a more specific/enhanced version of Y
    # e.g., "FastAPI REFINES Starlette", "TypeScript REFINES JavaScript"
    "REFINES": {
        ("technology", "technology"),  # FastAPI REFINES Starlette
        ("pattern", "pattern"),  # Event sourcing REFINES audit logging
        ("concept", "concept"),  # Microservices REFINES modular architecture
        ("system", "system"),  # GraphQL gateway REFINES API gateway
    },
}

# Relationships that are ONLY valid between entities (not decisions)
ENTITY_ONLY_RELATIONSHIPS: frozenset[str] = frozenset(
    [
        "IS_A",
        "PART_OF",
        "DEPENDS_ON",
        "RELATED_TO",
        "ALTERNATIVE_TO",
        # KG-P2-1: Extended relationships
        "ENABLES",
        "PREVENTS",
        "REQUIRES",
        "REFINES",
    ]
)

# Relationships that are ONLY valid between decisions
DECISION_ONLY_RELATIONSHIPS: frozenset[str] = frozenset(
    ["SIMILAR_TO", "INFLUENCED_BY", "SUPERSEDES", "CONTRADICTS"]
)

# Relationships from decisions to entities
DECISION_ENTITY_RELATIONSHIPS: frozenset[str] = frozenset(["INVOLVES"])

# All valid relationship types
ALL_RELATIONSHIP_TYPES: frozenset[str] = (
    ENTITY_ONLY_RELATIONSHIPS
    | DECISION_ONLY_RELATIONSHIPS
    | DECISION_ENTITY_RELATIONSHIPS
)


def validate_entity_relationship(
    rel_type: str, source_type: str, target_type: str
) -> tuple[bool, str | None]:
    """Validate if a relationship type is valid between two entity types.

    Args:
        rel_type: The relationship type (e.g., "IS_A", "DEPENDS_ON")
        source_type: The source entity type (e.g., "technology", "concept")
        target_type: The target entity type

    Returns:
        Tuple of (is_valid, error_message).
        error_message is None if valid, otherwise contains explanation.
    """
    # Normalize inputs
    rel_type = rel_type.upper()
    source_type = source_type.lower()
    target_type = target_type.lower()

    # Check if relationship type is known
    if rel_type not in VALID_ENTITY_RELATIONSHIPS:
        if rel_type in DECISION_ONLY_RELATIONSHIPS:
            return (
                False,
                f"'{rel_type}' is only valid between decisions, not entities",
            )
        if rel_type in DECISION_ENTITY_RELATIONSHIPS:
            return (
                False,
                f"'{rel_type}' is for decision-to-entity links, not entity-to-entity",
            )
        return (False, f"Unknown relationship type: '{rel_type}'")

    # Check if the source/target type combination is valid
    valid_combinations = VALID_ENTITY_RELATIONSHIPS[rel_type]
    if (source_type, target_type) not in valid_combinations:
        # Check if reversed would be valid (for user guidance)
        if (target_type, source_type) in valid_combinations:
            return (
                False,
                f"Invalid direction: '{source_type}' cannot {rel_type} '{target_type}'. "
                f"Did you mean '{target_type}' {rel_type} '{source_type}'?",
            )
        return (
            False,
            f"Invalid relationship: '{source_type}' cannot {rel_type} '{target_type}'. "
            f"Valid targets for {source_type} {rel_type}: "
            f"{[t for s, t in valid_combinations if s == source_type]}",
        )

    return (True, None)


def get_suggested_relationship(
    source_type: str, target_type: str, context: str = ""
) -> str:
    """Suggest the most appropriate relationship type for two entity types.

    Args:
        source_type: The source entity type
        target_type: The target entity type
        context: Optional context string for better suggestions

    Returns:
        Suggested relationship type string
    """
    source_type = source_type.lower()
    target_type = target_type.lower()

    # Check each relationship type for validity
    # Priority order reflects semantic specificity
    # KG-P2-1: Include new relationship types in priority order
    priority_order = [
        "REQUIRES",  # Strongest dependency
        "DEPENDS_ON",  # Standard dependency
        "ENABLES",  # Capability relationship
        "PREVENTS",  # Blocking relationship
        "REFINES",  # Specialization
        "PART_OF",  # Composition
        "IS_A",  # Taxonomy
        "ALTERNATIVE_TO",  # Substitution
        "RELATED_TO",  # General fallback
    ]

    for rel_type in priority_order:
        if rel_type in VALID_ENTITY_RELATIONSHIPS:
            if (source_type, target_type) in VALID_ENTITY_RELATIONSHIPS[rel_type]:
                return rel_type

    # Fallback to RELATED_TO if nothing else matches
    return "RELATED_TO"


# Canonical name mappings for entity resolution
# Maps various aliases/variations to the canonical name
CANONICAL_NAMES: dict[str, str] = {
    # ============================================================
    # DATABASES
    # ============================================================
    # PostgreSQL
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "pg": "PostgreSQL",
    "psql": "PostgreSQL",
    # MongoDB
    "mongodb": "MongoDB",
    "mongo": "MongoDB",
    "mongod": "MongoDB",
    # Neo4j
    "neo4j": "Neo4j",
    "neo": "Neo4j",
    # Redis
    "redis": "Redis",
    "redis-server": "Redis",
    # MySQL/MariaDB
    "mysql": "MySQL",
    "mariadb": "MariaDB",
    # SQLite
    "sqlite": "SQLite",
    "sqlite3": "SQLite",
    # DynamoDB
    "dynamodb": "DynamoDB",
    "dynamo": "DynamoDB",
    "amazon dynamodb": "DynamoDB",
    "aws dynamodb": "DynamoDB",
    # Cassandra
    "cassandra": "Cassandra",
    "apache cassandra": "Cassandra",
    # Elasticsearch
    "elasticsearch": "Elasticsearch",
    "elastic": "Elasticsearch",
    "es": "Elasticsearch",
    "opensearch": "OpenSearch",
    # Other databases
    "cockroachdb": "CockroachDB",
    "cockroach": "CockroachDB",
    "timescaledb": "TimescaleDB",
    "timescale": "TimescaleDB",
    "clickhouse": "ClickHouse",
    "influxdb": "InfluxDB",
    "influx": "InfluxDB",
    "couchdb": "CouchDB",
    "couch": "CouchDB",
    "firestore": "Firestore",
    "cloud firestore": "Firestore",
    "supabase": "Supabase",
    "planetscale": "PlanetScale",
    "neon": "Neon",
    "neon postgres": "Neon",
    # ============================================================
    # PROGRAMMING LANGUAGES
    # ============================================================
    # Python
    "python": "Python",
    "py": "Python",
    "python3": "Python",
    "python2": "Python 2",
    "cpython": "Python",
    # JavaScript/TypeScript
    "javascript": "JavaScript",
    "js": "JavaScript",
    "ecmascript": "JavaScript",
    "es6": "JavaScript ES6",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    # Go
    "golang": "Go",
    "go": "Go",
    # Rust
    "rust": "Rust",
    "rustlang": "Rust",
    # Java/Kotlin
    "java": "Java",
    "kotlin": "Kotlin",
    "kt": "Kotlin",
    # Swift
    "swift": "Swift",
    "swiftlang": "Swift",
    # C/C++
    "c": "C",
    "c++": "C++",
    "cpp": "C++",
    "cplusplus": "C++",
    # C#/.NET
    "c#": "C#",
    "csharp": "C#",
    "dotnet": ".NET",
    ".net": ".NET",
    ".net core": ".NET",
    "dotnet core": ".NET",
    # Ruby
    "ruby": "Ruby",
    "rb": "Ruby",
    # PHP
    "php": "PHP",
    # Scala
    "scala": "Scala",
    # Elixir
    "elixir": "Elixir",
    "ex": "Elixir",
    # Clojure
    "clojure": "Clojure",
    "clj": "Clojure",
    # Haskell
    "haskell": "Haskell",
    "hs": "Haskell",
    # ============================================================
    # FRONTEND FRAMEWORKS
    # ============================================================
    # React
    "react": "React",
    "reactjs": "React",
    "react.js": "React",
    "react js": "React",
    # Vue.js
    "vue": "Vue.js",
    "vuejs": "Vue.js",
    "vue.js": "Vue.js",
    "vue 3": "Vue.js",
    "vue3": "Vue.js",
    # Angular
    "angular": "Angular",
    "angularjs": "Angular",
    "angular.js": "Angular",
    # Svelte
    "svelte": "Svelte",
    "sveltejs": "Svelte",
    "sveltekit": "SvelteKit",
    # Next.js
    "nextjs": "Next.js",
    "next.js": "Next.js",
    "next": "Next.js",
    "next js": "Next.js",
    # Nuxt.js
    "nuxt": "Nuxt.js",
    "nuxtjs": "Nuxt.js",
    "nuxt.js": "Nuxt.js",
    # Remix
    "remix": "Remix",
    "remix.run": "Remix",
    # Astro
    "astro": "Astro",
    "astro.build": "Astro",
    # Solid
    "solid": "SolidJS",
    "solidjs": "SolidJS",
    "solid.js": "SolidJS",
    # Qwik
    "qwik": "Qwik",
    # ============================================================
    # BACKEND FRAMEWORKS
    # ============================================================
    # FastAPI
    "fastapi": "FastAPI",
    "fast-api": "FastAPI",
    "fast api": "FastAPI",
    # Django
    "django": "Django",
    "drf": "Django REST Framework",
    "django rest framework": "Django REST Framework",
    # Flask
    "flask": "Flask",
    # Express.js
    "express": "Express.js",
    "expressjs": "Express.js",
    "express.js": "Express.js",
    # NestJS
    "nestjs": "NestJS",
    "nest.js": "NestJS",
    "nest": "NestJS",
    # Spring
    "spring": "Spring",
    "springboot": "Spring Boot",
    "spring boot": "Spring Boot",
    "spring-boot": "Spring Boot",
    # Ruby on Rails
    "rails": "Ruby on Rails",
    "ruby on rails": "Ruby on Rails",
    "ror": "Ruby on Rails",
    # Laravel
    "laravel": "Laravel",
    # ASP.NET
    "asp.net": "ASP.NET",
    "aspnet": "ASP.NET",
    "asp.net core": "ASP.NET Core",
    # Gin
    "gin": "Gin",
    "gin-gonic": "Gin",
    # Echo
    "echo": "Echo",
    "labstack echo": "Echo",
    # Fiber
    "fiber": "Fiber",
    "gofiber": "Fiber",
    # Phoenix
    "phoenix": "Phoenix",
    "phoenix framework": "Phoenix",
    # ============================================================
    # API STANDARDS & PROTOCOLS
    # ============================================================
    "api": "API",
    "rest": "REST API",
    "rest api": "REST API",
    "restful": "REST API",
    "restful api": "REST API",
    "graphql": "GraphQL",
    "gql": "GraphQL",
    "grpc": "gRPC",
    "g-rpc": "gRPC",
    "websocket": "WebSocket",
    "websockets": "WebSocket",
    "ws": "WebSocket",
    "wss": "WebSocket",
    "trpc": "tRPC",
    "openapi": "OpenAPI",
    "swagger": "OpenAPI",
    "soap": "SOAP",
    # ============================================================
    # CLOUD PROVIDERS
    # ============================================================
    # AWS
    "aws": "AWS",
    "amazon web services": "AWS",
    "amazon aws": "AWS",
    # GCP
    "gcp": "GCP",
    "google cloud": "GCP",
    "google cloud platform": "GCP",
    # Azure
    "azure": "Azure",
    "microsoft azure": "Azure",
    "ms azure": "Azure",
    # Other cloud
    "digitalocean": "DigitalOcean",
    "do": "DigitalOcean",
    "linode": "Linode",
    "vultr": "Vultr",
    "heroku": "Heroku",
    "vercel": "Vercel",
    "netlify": "Netlify",
    "cloudflare": "Cloudflare",
    "cf": "Cloudflare",
    "fly": "Fly.io",
    "fly.io": "Fly.io",
    "railway": "Railway",
    "render": "Render",
    # ============================================================
    # CONTAINERIZATION & ORCHESTRATION
    # ============================================================
    # Docker
    "docker": "Docker",
    "docker-compose": "Docker Compose",
    "docker compose": "Docker Compose",
    "compose": "Docker Compose",
    # Kubernetes
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "kube": "Kubernetes",
    # Kubernetes distributions
    "eks": "Amazon EKS",
    "amazon eks": "Amazon EKS",
    "gke": "Google GKE",
    "google gke": "Google GKE",
    "aks": "Azure AKS",
    "azure aks": "Azure AKS",
    "openshift": "OpenShift",
    "rancher": "Rancher",
    "k3s": "K3s",
    "minikube": "Minikube",
    "kind": "KinD",
    # Helm
    "helm": "Helm",
    "helm charts": "Helm",
    # Other container tools
    "podman": "Podman",
    "containerd": "containerd",
    "cri-o": "CRI-O",
    # ============================================================
    # MESSAGE QUEUES & STREAMING
    # ============================================================
    # Kafka
    "kafka": "Apache Kafka",
    "apache kafka": "Apache Kafka",
    # RabbitMQ
    "rabbitmq": "RabbitMQ",
    "rabbit mq": "RabbitMQ",
    "rabbit": "RabbitMQ",
    # Amazon SQS/SNS
    "sqs": "Amazon SQS",
    "amazon sqs": "Amazon SQS",
    "aws sqs": "Amazon SQS",
    "sns": "Amazon SNS",
    "amazon sns": "Amazon SNS",
    # Other queues
    "nats": "NATS",
    "nats.io": "NATS",
    "pulsar": "Apache Pulsar",
    "apache pulsar": "Apache Pulsar",
    "zeromq": "ZeroMQ",
    "0mq": "ZeroMQ",
    "activemq": "ActiveMQ",
    "apache activemq": "ActiveMQ",
    "bull": "Bull",
    "bullmq": "BullMQ",
    "celery": "Celery",
    # ============================================================
    # AI/ML FRAMEWORKS & TOOLS
    # ============================================================
    # LLM Providers
    "openai": "OpenAI",
    "gpt": "GPT",
    "gpt-4": "GPT-4",
    "gpt-3": "GPT-3",
    "gpt4": "GPT-4",
    "gpt3": "GPT-3",
    "chatgpt": "ChatGPT",
    "claude": "Claude",
    "anthropic": "Anthropic",
    "gemini": "Gemini",
    "google gemini": "Gemini",
    "llama": "LLaMA",
    "llama2": "LLaMA 2",
    "llama 2": "LLaMA 2",
    "mistral": "Mistral",
    "mixtral": "Mixtral",
    "cohere": "Cohere",
    "palm": "PaLM",
    "palm 2": "PaLM 2",
    # ML Frameworks
    "tensorflow": "TensorFlow",
    "tf": "TensorFlow",
    "pytorch": "PyTorch",
    "torch": "PyTorch",
    "jax": "JAX",
    "keras": "Keras",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
    "catboost": "CatBoost",
    # LLM Tooling
    "langchain": "LangChain",
    "lang chain": "LangChain",
    "llamaindex": "LlamaIndex",
    "llama index": "LlamaIndex",
    "llama-index": "LlamaIndex",
    "huggingface": "Hugging Face",
    "hugging face": "Hugging Face",
    "hf": "Hugging Face",
    "transformers": "Hugging Face Transformers",
    "openllm": "OpenLLM",
    "ollama": "Ollama",
    "vllm": "vLLM",
    "mlflow": "MLflow",
    "wandb": "Weights & Biases",
    "weights and biases": "Weights & Biases",
    # Vector Databases
    "pinecone": "Pinecone",
    "weaviate": "Weaviate",
    "milvus": "Milvus",
    "qdrant": "Qdrant",
    "chroma": "Chroma",
    "chromadb": "Chroma",
    "pgvector": "pgvector",
    "faiss": "FAISS",
    # ============================================================
    # TESTING FRAMEWORKS
    # ============================================================
    # JavaScript testing
    "jest": "Jest",
    "mocha": "Mocha",
    "vitest": "Vitest",
    "cypress": "Cypress",
    "playwright": "Playwright",
    "puppeteer": "Puppeteer",
    "testing-library": "Testing Library",
    "testing library": "Testing Library",
    "rtl": "React Testing Library",
    # Python testing
    "pytest": "pytest",
    "py.test": "pytest",
    "unittest": "unittest",
    "nose": "nose",
    "hypothesis": "Hypothesis",
    # Other testing
    "junit": "JUnit",
    "junit5": "JUnit 5",
    "testng": "TestNG",
    "rspec": "RSpec",
    "minitest": "Minitest",
    "phpunit": "PHPUnit",
    # ============================================================
    # ORMs & DATABASE TOOLS
    # ============================================================
    # Python ORMs
    "sqlalchemy": "SQLAlchemy",
    "sqlmodel": "SQLModel",
    "tortoise": "Tortoise ORM",
    "tortoise-orm": "Tortoise ORM",
    "peewee": "Peewee",
    "django orm": "Django ORM",
    # JavaScript ORMs
    "prisma": "Prisma",
    "typeorm": "TypeORM",
    "sequelize": "Sequelize",
    "mongoose": "Mongoose",
    "drizzle": "Drizzle ORM",
    "drizzle-orm": "Drizzle ORM",
    "knex": "Knex.js",
    "knex.js": "Knex.js",
    # Other ORMs
    "hibernate": "Hibernate",
    "entity framework": "Entity Framework",
    "ef": "Entity Framework",
    "ef core": "Entity Framework Core",
    "gorm": "GORM",
    "ecto": "Ecto",
    "activerecord": "Active Record",
    "active record": "Active Record",
    # ============================================================
    # UI LIBRARIES & STYLING
    # ============================================================
    # CSS Frameworks
    "tailwind": "Tailwind CSS",
    "tailwindcss": "Tailwind CSS",
    "tailwind css": "Tailwind CSS",
    "bootstrap": "Bootstrap",
    "bulma": "Bulma",
    "foundation": "Foundation",
    # Component Libraries
    "material ui": "Material UI",
    "mui": "Material UI",
    "material-ui": "Material UI",
    "shadcn": "shadcn/ui",
    "shadcn/ui": "shadcn/ui",
    "shadcn ui": "shadcn/ui",
    "chakra": "Chakra UI",
    "chakra ui": "Chakra UI",
    "chakra-ui": "Chakra UI",
    "ant design": "Ant Design",
    "antd": "Ant Design",
    "radix": "Radix UI",
    "radix ui": "Radix UI",
    "headless ui": "Headless UI",
    "headlessui": "Headless UI",
    "mantine": "Mantine",
    "daisyui": "DaisyUI",
    "daisy ui": "DaisyUI",
    # CSS-in-JS
    "styled-components": "styled-components",
    "styled components": "styled-components",
    "emotion": "Emotion",
    "@emotion": "Emotion",
    "css modules": "CSS Modules",
    "sass": "Sass",
    "scss": "Sass",
    "less": "Less",
    # ============================================================
    # STATE MANAGEMENT
    # ============================================================
    "redux": "Redux",
    "redux toolkit": "Redux Toolkit",
    "rtk": "Redux Toolkit",
    "zustand": "Zustand",
    "mobx": "MobX",
    "recoil": "Recoil",
    "jotai": "Jotai",
    "xstate": "XState",
    "x-state": "XState",
    "valtio": "Valtio",
    "pinia": "Pinia",
    "vuex": "Vuex",
    "ngrx": "NgRx",
    "akita": "Akita",
    # ============================================================
    # BUILD TOOLS & BUNDLERS
    # ============================================================
    "webpack": "Webpack",
    "vite": "Vite",
    "vitejs": "Vite",
    "esbuild": "esbuild",
    "rollup": "Rollup",
    "rollup.js": "Rollup",
    "parcel": "Parcel",
    "turbopack": "Turbopack",
    "swc": "SWC",
    "babel": "Babel",
    "babeljs": "Babel",
    "tsc": "TypeScript Compiler",
    "tsup": "tsup",
    "unbuild": "unbuild",
    # ============================================================
    # PACKAGE MANAGERS
    # ============================================================
    "npm": "npm",
    "yarn": "Yarn",
    "pnpm": "pnpm",
    "bun": "Bun",
    "pip": "pip",
    "poetry": "Poetry",
    "pipenv": "Pipenv",
    "uv": "uv",
    "conda": "Conda",
    "cargo": "Cargo",
    "go mod": "Go Modules",
    "go modules": "Go Modules",
    "maven": "Maven",
    "gradle": "Gradle",
    "composer": "Composer",
    "bundler": "Bundler",
    "gem": "RubyGems",
    "rubygems": "RubyGems",
    # ============================================================
    # VERSION CONTROL & COLLABORATION
    # ============================================================
    "git": "Git",
    "github": "GitHub",
    "gh": "GitHub",
    "gitlab": "GitLab",
    "gl": "GitLab",
    "bitbucket": "Bitbucket",
    "bb": "Bitbucket",
    "gitea": "Gitea",
    "gogs": "Gogs",
    "azure devops": "Azure DevOps",
    "ado": "Azure DevOps",
    # ============================================================
    # CI/CD
    # ============================================================
    "github actions": "GitHub Actions",
    "gh actions": "GitHub Actions",
    "gha": "GitHub Actions",
    "gitlab ci": "GitLab CI",
    "gitlab-ci": "GitLab CI",
    "circleci": "CircleCI",
    "circle ci": "CircleCI",
    "jenkins": "Jenkins",
    "travis": "Travis CI",
    "travis ci": "Travis CI",
    "travisci": "Travis CI",
    "drone": "Drone CI",
    "drone ci": "Drone CI",
    "teamcity": "TeamCity",
    "bamboo": "Bamboo",
    "buildkite": "Buildkite",
    "semaphore": "Semaphore",
    "argo": "Argo CD",
    "argocd": "Argo CD",
    "argo cd": "Argo CD",
    "flux": "Flux CD",
    "fluxcd": "Flux CD",
    "spinnaker": "Spinnaker",
    # ============================================================
    # OBSERVABILITY & MONITORING
    # ============================================================
    # Metrics
    "prometheus": "Prometheus",
    "prom": "Prometheus",
    "grafana": "Grafana",
    "datadog": "Datadog",
    "dd": "Datadog",
    "new relic": "New Relic",
    "newrelic": "New Relic",
    "dynatrace": "Dynatrace",
    "cloudwatch": "CloudWatch",
    "aws cloudwatch": "CloudWatch",
    "stackdriver": "Cloud Monitoring",
    "google cloud monitoring": "Cloud Monitoring",
    # Logging
    "logstash": "Logstash",
    "kibana": "Kibana",
    "elk": "ELK Stack",
    "elk stack": "ELK Stack",
    "splunk": "Splunk",
    "loki": "Grafana Loki",
    "grafana loki": "Grafana Loki",
    "fluentd": "Fluentd",
    "fluent bit": "Fluent Bit",
    "fluentbit": "Fluent Bit",
    "papertrail": "Papertrail",
    "loggly": "Loggly",
    # Tracing
    "jaeger": "Jaeger",
    "zipkin": "Zipkin",
    "opentelemetry": "OpenTelemetry",
    "otel": "OpenTelemetry",
    "tempo": "Grafana Tempo",
    "grafana tempo": "Grafana Tempo",
    "honeycomb": "Honeycomb",
    "lightstep": "Lightstep",
    # Error tracking
    "sentry": "Sentry",
    "rollbar": "Rollbar",
    "bugsnag": "Bugsnag",
    "airbrake": "Airbrake",
    # ============================================================
    # INFRASTRUCTURE AS CODE
    # ============================================================
    "terraform": "Terraform",
    "pulumi": "Pulumi",
    "cloudformation": "CloudFormation",
    "aws cloudformation": "CloudFormation",
    "cdk": "AWS CDK",
    "aws cdk": "AWS CDK",
    "ansible": "Ansible",
    "chef": "Chef",
    "puppet": "Puppet",
    "salt": "SaltStack",
    "saltstack": "SaltStack",
    "crossplane": "Crossplane",
    # ============================================================
    # AUTHENTICATION & SECURITY
    # ============================================================
    "jwt": "JWT",
    "json web token": "JWT",
    "json web tokens": "JWT",
    "oauth": "OAuth",
    "oauth2": "OAuth 2.0",
    "oauth 2": "OAuth 2.0",
    "oauth 2.0": "OAuth 2.0",
    "oidc": "OpenID Connect",
    "openid connect": "OpenID Connect",
    "saml": "SAML",
    "auth0": "Auth0",
    "okta": "Okta",
    "keycloak": "Keycloak",
    "firebase auth": "Firebase Auth",
    "cognito": "Amazon Cognito",
    "aws cognito": "Amazon Cognito",
    "clerk": "Clerk",
    "nextauth": "NextAuth.js",
    "next-auth": "NextAuth.js",
    "passport": "Passport.js",
    "passportjs": "Passport.js",
    "supertokens": "SuperTokens",
    # ============================================================
    # COMMON PATTERNS & CONCEPTS
    # ============================================================
    "microservices": "Microservices",
    "microservice": "Microservices",
    "micro-services": "Microservices",
    "monolith": "Monolith",
    "monolithic": "Monolith",
    "serverless": "Serverless",
    "faas": "FaaS",
    "function as a service": "FaaS",
    "ci/cd": "CI/CD",
    "ci cd": "CI/CD",
    "cicd": "CI/CD",
    "continuous integration": "CI/CD",
    "continuous deployment": "CI/CD",
    "devops": "DevOps",
    "dev ops": "DevOps",
    "devsecops": "DevSecOps",
    "gitops": "GitOps",
    "infrastructure as code": "Infrastructure as Code",
    "iac": "Infrastructure as Code",
    "event driven": "Event-Driven Architecture",
    "event-driven": "Event-Driven Architecture",
    "eda": "Event-Driven Architecture",
    "cqrs": "CQRS",
    "event sourcing": "Event Sourcing",
    "domain driven design": "Domain-Driven Design",
    "ddd": "Domain-Driven Design",
    "clean architecture": "Clean Architecture",
    "hexagonal architecture": "Hexagonal Architecture",
    "ports and adapters": "Hexagonal Architecture",
    "twelve factor": "Twelve-Factor App",
    "12 factor": "Twelve-Factor App",
    "12-factor": "Twelve-Factor App",
}


@dataclass
class ResolvedEntity:
    """Result of entity resolution."""

    id: Optional[str]
    name: str
    type: str
    is_new: bool = False
    match_method: Optional[str] = None
    confidence: float = 1.0
    canonical_name: Optional[str] = None
    aliases: list[str] = None

    def __post_init__(self):
        if self.aliases is None:
            self.aliases = []


def get_canonical_name(name: str) -> str:
    """Get the canonical name for an entity, or return the original if not found.

    Checks the static CANONICAL_NAMES dict first, then falls back to the
    dynamically-generated DYNAMIC_CANONICAL_NAMES (Part 3a: OntologyUpdater).
    """
    key = name.lower()
    if key in CANONICAL_NAMES:
        return CANONICAL_NAMES[key]
    # Lazy-load dynamic mappings (auto-generated by OntologyUpdater)
    try:
        from services.ontology_updater import load_dynamic_canonical_names
        dynamic = load_dynamic_canonical_names()
        if key in dynamic:
            return dynamic[key]
    except ImportError:
        pass
    return name


def normalize_entity_name(name: str) -> str:
    """Normalize an entity name for comparison (lowercase, strip whitespace)."""
    return name.lower().strip()
