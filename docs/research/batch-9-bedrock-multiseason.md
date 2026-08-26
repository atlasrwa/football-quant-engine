# Batch 9 — AWS Bedrock Researcher + Multi-Season Research

## Overview

Batch 9 adds two major capabilities to the research platform:

1. **AWS Bedrock LLM Provider** — Production-quality Claude Sonnet integration via AWS Bedrock for AI-assisted research hypothesis generation.
2. **Multi-Season Research** — Ability to load, analyze, and run statistically governed research across multiple FootyStats seasons.

The AI is a **research assistant** that proposes hypotheses. The deterministic pipeline remains the sole authority for statistical validation, FDR correction, walk-forward testing, and governance.

## Architecture

```
ResearchAgent
    |
    v
LLMProvider (interface)
    |
    v
BedrockLLMProvider
    |
    v
AWS Bedrock Runtime (boto3)
    |
    v
Claude Sonnet (configured model)
```

### Key Components

| File | Purpose |
|------|---------|
| `src/research/ai/bedrock.py` | BedrockLLMProvider — implements LLMProvider interface |
| `src/research/ai/bedrock_config.py` | BedrockConfig — typed, validated configuration |
| `src/research/ai/prompts.py` | System prompts v1/v2 with safety boundaries |
| `src/research/ai/agent.py` | ResearchAgent — single and batch proposal generation |
| `src/research/ai/research_loop.py` | AIResearchLoop — bounded iterative research |
| `src/research/ai/multiseason.py` | MultiSeasonDataset and build utilities |
| `src/research/ai/usage_tracker.py` | AI cost control and usage monitoring |
| `src/research/ai/season_stability.py` | Season-level stability reporting |
| `src/research/ai/context.py` | Extended ResearchContextBuilder (multi-season) |

## Model Selection: Claude Sonnet

Claude Sonnet was selected for this workload because:

1. **Structured output quality** — Produces reliable JSON output for research hypothesis schemas.
2. **Instruction following** — Respects complex safety constraints and output format requirements.
3. **Reasoning capability** — Can analyze research context and propose novel hypotheses.
4. **Cost efficiency** — Good balance of quality and cost for batch research operations.
5. **AWS Bedrock availability** — Natively available without managing API keys separately.
6. **Low-temperature reliability** — Produces consistent, high-quality structured output at temperature 0.2.

The model ID is configurable — the system does not hardcode a specific model version.

## Bedrock Integration

### IAM Requirements

The service requires permissions to invoke the Bedrock model:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": [
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-*"
      ]
    }
  ]
}
```

### Credential Resolution

The provider uses standard AWS credential chain (boto3 default):
1. IAM role (ECS/EKS task role, EC2 instance role)
2. Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
3. AWS profile (`~/.aws/credentials`)
4. Container credentials (ECS)

**No credentials are stored in application code, research objects, logs, or prompts.**

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BEDROCK_MODEL_ID` | `anthropic.claude-sonnet-4-20250514-v1:0` | Bedrock model identifier |
| `AWS_REGION` | `us-east-1` | AWS region for Bedrock endpoint |
| `BEDROCK_MAX_TOKENS` | `2000` | Max tokens per response |
| `BEDROCK_TEMPERATURE` | `0.2` | Sampling temperature |
| `BEDROCK_TIMEOUT_SECONDS` | `60` | Request timeout |
| `BEDROCK_MAX_RETRIES` | `3` | Max retry attempts |
| `BEDROCK_MAX_AI_CALLS` | `20` | Max AI calls per research run |
| `BEDROCK_MAX_INPUT_TOKENS` | `100000` | Max cumulative input tokens |
| `BEDROCK_MAX_OUTPUT_TOKENS` | `50000` | Max cumulative output tokens |

## AI Research Workflow

The bounded AI research loop operates as:

```
1. BUILD_CONTEXT        — Assemble bounded research context from memory
2. BEDROCK_PROPOSE      — Request proposals from Claude via Bedrock
3. VALIDATE             — Deterministic validation of every proposal
4. DEDUPLICATE          — Check against research memory
5. QUEUE                — Submit valid proposals as research tasks
6. EXPERIMENT           — Execute via existing deterministic pipeline
7. WALK_FORWARD         — Walk-forward validation (mandatory)
8. FDR                  — False discovery rate correction (mandatory)
9. GOVERNANCE           — Governance classification (mandatory)
10. PERSIST             — Store results
11. UPDATE_MEMORY       — Update research memory
12. OPTIONAL_NEXT_CYCLE — If budget permits, repeat from step 1
13. STOP                — Clean termination
```

### Example Usage

```python
from src.research.ai import (
    AIResearchLoop,
    BedrockConfig,
    BedrockLLMProvider,
    ResearchAgent,
    ResearchBudget,
    ResearchContextBuilder,
)
from src.research.persistence import InMemoryResearchRepository
from src.research.persistence.research_memory import ResearchMemory

# Configure
config = BedrockConfig.from_env()
provider = BedrockLLMProvider(config=config)
agent = ResearchAgent(provider=provider, prompt_version="v2")

# Setup persistence
repo = InMemoryResearchRepository()  # Or PostgresResearchRepository
memory = ResearchMemory(repo)
context_builder = ResearchContextBuilder(repository=repo)
budget = ResearchBudget(max_ai_proposals=10, max_experiments=30)

# Run bounded AI research
loop = AIResearchLoop(
    agent=agent,
    context_builder=context_builder,
    repository=repo,
    memory=memory,
    budget=budget,
    max_cycles=3,
    max_proposals_per_cycle=5,
)

result = loop.run(
    run_id="research_run_001",
    market_type="CORNERS_TOTAL",
    available_features=["dangerous_attacks_home", "possession_home", ...],
    available_markets=["CORNERS_TOTAL", "GOALS_TOTAL", ...],
)

print(f"Status: {result.status.value}")
print(f"Proposals generated: {result.total_proposals_generated}")
print(f"Tasks queued: {result.total_tasks_queued}")
```

### Multi-Season Research

```python
from src.research.ai.multiseason import build_multi_season_dataset

# Load multiple seasons
dataset = build_multi_season_dataset(
    season_ids=[4759, 4760, 4761],  # Explicit season IDs
    cache_dir=Path("./cache/footystats"),
)

print(f"Total matches: {dataset.total_matches}")
print(f"Seasons: {dataset.seasons}")
print(f"Date range: {dataset.date_range}")
print(f"Coverage: {dataset.get_coverage_summary()}")
```

## Security Boundary

### AI Can

- Inspect historical research results
- Identify patterns in previous experiments
- Suggest candidate features, thresholds, interactions
- Suggest markets and directions
- Explain reasoning for hypotheses
- Produce structured JSON proposals

### AI Cannot

- Declare a strategy profitable
- Bypass walk-forward validation
- Bypass FDR correction
- Bypass governance
- Modify historical results or experiment outcomes
- Promote strategies for live trading
- Access AWS credentials
- Execute code, SQL, or shell commands
- Directly modify the database
- Access the filesystem

### AI Confidence vs Statistical Confidence

AI `confidence` (0.0-1.0) is the model's subjective assessment of research priority. It is **never** used as:
- A p-value
- A probability of profitability
- A governance criterion
- A substitute for statistical testing

## Temporal Safeguards

1. **Feature-level**: ProposalValidator rejects post-match features (home_goals, away_goals, total_goals, result).
2. **Context-level**: ResearchContext carries a `temporal_cutoff` timestamp. Only information available before the cutoff is included.
3. **Season-level**: MultiSeasonDataset maintains strict chronological ordering. Future seasons cannot contaminate training for earlier test periods.
4. **Walk-forward**: The existing WalkForwardOrchestrator enforces past→training, future→test.

## Cost Controls

### Budget Limits

```python
ResearchBudget(
    max_tasks=100,           # Total research tasks
    max_experiments=50,      # Experiment executions
    max_ai_proposals=20,     # AI proposal cycles
    max_candidates=200,      # Total candidates generated
    max_runtime_seconds=3600, # 1 hour total runtime
)
```

### AI Usage Tracking

```python
AIUsageTracker(
    max_calls_per_run=20,
    max_total_input_tokens=100_000,
    max_total_output_tokens=50_000,
    max_total_runtime_seconds=300,  # 5 min AI time
)
```

### Provider Usage Stats

```python
provider.usage_stats  # Returns safe metadata:
# {
#   "provider": "bedrock",
#   "model_id": "...",
#   "request_count": 5,
#   "total_input_tokens": 3500,
#   "total_output_tokens": 1200,
#   "total_latency_ms": 8500.0,
#   "failure_count": 0,
# }
```

## Retry Behavior

| Error Type | Retried? | Backoff |
|------------|----------|---------|
| ThrottlingException | Yes | 2^n seconds, max 30s |
| TooManyRequestsException | Yes | 2^n seconds, max 30s |
| ServiceQuotaExceededException | Yes | 2^n seconds, max 30s |
| InternalServerException | Yes | 2^n seconds, max 30s |
| ModelTimeoutException | Yes | 2^n seconds, max 30s |
| ReadTimeoutError | Yes | 2^n seconds, max 30s |
| AccessDeniedException | No | Immediate failure |
| UnrecognizedClientException | No | Immediate failure |
| ExpiredTokenException | No | Immediate failure |
| ValidationException | No | Immediate failure |
| Malformed response | No | Immediate failure |

Maximum retries: configurable (default 3).

## Failure Modes

| Scenario | Behavior |
|----------|----------|
| boto3 not installed | `is_available()` returns False, research continues without AI |
| Invalid credentials | `BedrockAuthenticationError` raised, no retry |
| Model throttled | Retry with backoff, then `BedrockThrottlingError` |
| Request timeout | Retry with backoff, then `BedrockTimeoutError` |
| Malformed AI response | Proposal silently dropped, loop continues |
| Budget exhausted | Clean stop, state persisted |
| Provider unavailable | AIResearchLoop returns `AI_UNAVAILABLE` status |
| Partial progress + crash | Research memory preserves completed work |

## Multi-Season Ingestion

### Requirements

- Explicit `season_ids` list (no auto-discovery)
- Each season fetched via FootyStatsResearchClient
- Deduplication by match_id across seasons
- Strict chronological ordering maintained
- Per-season coverage reporting
- Content hashing for deterministic identity

### Coverage Reporting

```python
dataset.get_coverage_summary()
# {
#   "total_matches": 1140,
#   "seasons": 3,
#   "teams": 60,
#   "earliest_date_unix": 1597000000,
#   "latest_date_unix": 1655000000,
#   "per_season": [
#     {"season_id": 4759, "matches": 380, "teams": 20, ...},
#     {"season_id": 4760, "matches": 380, "teams": 20, ...},
#     {"season_id": 4761, "matches": 380, "teams": 20, ...},
#   ]
# }
```

## Season-Level Stability

The `build_season_stability_report()` function analyzes walk-forward results by season:

- Positive fold ratio per season
- Aggregate p-value per season
- Mean Brier score per season
- ROI per season
- Regime stability assessment

A hypothesis is considered **regime-stable** if:
- Tested across >= 2 seasons
- >= 50% of seasons show stability (positive_fold_ratio >= 0.6 within that season)
- Overall positive fold ratio >= 50%

## Testing

### Test Categories (115 tests in `test_batch9_bedrock_multiseason.py`)

- Bedrock provider with mocked AWS (5 tests)
- Configuration validation (8 tests)
- Authentication failure handling (2 tests)
- Throttling/retry (2 tests)
- Timeout handling (1 test)
- Malformed JSON handling (7 tests)
- Proposal validation (10 tests)
- AI-disabled behavior (5 tests)
- Multi-season ingestion (5 tests)
- Multi-season deduplication (1 test)
- Multi-season provenance (2 tests)
- Chronological ordering (3 tests)
- Temporal leakage attacks (5 tests)
- AI context cutoff (3 tests)
- Duplicate proposal prevention (4 tests)
- Budget exhaustion (5 tests)
- Queue integration (2 tests)
- Restart/resume (2 tests)
- FDR mandatory (2 tests)
- Governance mandatory (2 tests)
- AI cannot promote (2 tests)
- AI cannot modify results (2 tests)
- AI cannot execute code (2 tests)
- AI cannot execute SQL (1 test)
- Credential non-leakage (5 tests)
- Deterministic identity (3 tests)
- Multi-season walk-forward ordering (2 tests)
- Season-level reporting (4 tests)
- Research loop integration (4 tests)
- Usage tracker (6 tests)
- Prompt versions (6 tests)
- P-hacking prevention (2 tests)

### Running Tests

```bash
# Run Batch 9 tests only
python3 -m pytest tests/research/test_batch9_bedrock_multiseason.py -v

# Run all research tests (excluding slow benchmarks)
python3 -m pytest tests/research/ --ignore=tests/research/test_end_to_end.py --ignore=tests/research/test_walkforward_benchmark.py -q

# Integration tests with real Bedrock (opt-in only)
RUN_BEDROCK_INTEGRATION_TESTS=1 python3 -m pytest tests/integration/ -v
```

### No Network Dependency

All unit tests use `MockLLMProvider` or mocked boto3 clients. The normal test suite **never** calls AWS Bedrock.

## Limitations

1. **AI generation is non-deterministic** — Even with temperature=0.2, Claude may produce different proposals for the same context. This is handled by treating AI output as an external stochastic proposal source with deterministic validation downstream.

2. **No direct model evaluation** — The AI cannot evaluate its own proposals. All evaluation is done by the deterministic pipeline.

3. **Token counting** — Provider-reported token counts are used for tracking but may not exactly match billing.

4. **Near-duplicate detection** — The system uses content_hash for exact deduplication. Near-duplicates (same features, different thresholds) are handled by prompt instructions rather than programmatic detection.

5. **Single model** — Currently supports one model per provider instance. Multi-model ensembles are not implemented.

## Configuration Example

```bash
# .env or environment
export AWS_REGION=us-east-1
export BEDROCK_MODEL_ID=anthropic.claude-sonnet-4-20250514-v1:0
export BEDROCK_TEMPERATURE=0.2
export BEDROCK_MAX_TOKENS=2000
export BEDROCK_MAX_RETRIES=3
export BEDROCK_MAX_AI_CALLS=20
export BEDROCK_TIMEOUT_SECONDS=60
```

## Running a Bounded AI Research Run

```python
from src.research.ai import (
    AIResearchLoop,
    BedrockConfig,
    BedrockLLMProvider,
    ResearchAgent,
    ResearchBudget,
    ResearchContextBuilder,
    build_multi_season_dataset,
)
from src.research.persistence import InMemoryResearchRepository
from src.research.persistence.research_memory import ResearchMemory
from pathlib import Path

# 1. Load multi-season data
dataset = build_multi_season_dataset(
    season_ids=[4759, 4760, 4761],
    cache_dir=Path("./cache"),
)

# 2. Configure Bedrock
config = BedrockConfig.from_env()
provider = BedrockLLMProvider(config=config)

# 3. Setup research infrastructure
repo = InMemoryResearchRepository()
memory = ResearchMemory(repo)
context_builder = ResearchContextBuilder(repository=repo, max_results=15)

# 4. Create agent with safety-bounded prompt
agent = ResearchAgent(provider=provider, prompt_version="v2")

# 5. Configure budget
budget = ResearchBudget(
    max_ai_proposals=10,
    max_experiments=30,
    max_tasks=50,
    max_runtime_seconds=1800,  # 30 min
)

# 6. Run bounded loop
loop = AIResearchLoop(
    agent=agent,
    context_builder=context_builder,
    repository=repo,
    memory=memory,
    budget=budget,
    max_cycles=3,
    max_proposals_per_cycle=5,
)

result = loop.run(
    run_id="multiseason_corners_2024",
    market_type="CORNERS_TOTAL",
    available_features=dataset.matches[0].available_fields if dataset.matches else [],
    available_markets=["CORNERS_TOTAL", "GOALS_TOTAL", "CARDS_TOTAL"],
    dataset_summary=dataset.get_coverage_summary(),
    season_coverage=[sc.to_dict() for sc in dataset.season_coverage],
)

# 7. Results
print(f"Status: {result.status.value}")
print(f"Cycles: {result.cycles_completed}")
print(f"Proposals: {result.total_proposals_generated} generated, {result.total_proposals_valid} valid")
print(f"Tasks queued: {result.total_tasks_queued}")
print(f"Budget: {result.budget_used}")

# 8. Proposals are now in the queue — execute via ResearchOrchestrator
# (existing pipeline handles walk-forward, FDR, governance)
```
