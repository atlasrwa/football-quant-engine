# Batch 7 — Research Queue, Persistence & AI Researcher

## Architecture

```
┌──────────────────────┐
│ Deterministic Engine │  (Batches 1-6, unchanged)
└──────────┬───────────┘
           ↓
   Candidate/Hypothesis
           ↓
┌─────────────────────┐
│   Research Queue    │  task state machine, atomic claiming
└─────────┬───────────┘
           ↓
┌──────────────────────┐
│  AI Researcher       │  OPTIONAL — proposes structured hypotheses
│  (MockLLMProvider)   │
└──────────┬───────────┘
           ↓
  Validated Proposal
           ↓
  Deterministic Evaluation (experiment → walk-forward → FDR → governance)
           ↓
┌──────────────────────┐
│  Research Memory     │  prevents duplicates, provides history
└──────────────────────┘
```

## Key Principle

The AI proposes. The deterministic system validates, evaluates, and decides.

## Database / Persistence

### Repository Interface (`src/research/persistence/repository.py`)

Abstract `ResearchRepository` with methods for:
- Research runs, candidates, hypotheses, experiments, walk-forward results
- Governance decisions, proposals, tasks
- Atomic task claiming, statistics

### In-Memory Implementation (`src/research/persistence/memory.py`)

Thread-safe `InMemoryResearchRepository` using `threading.Lock`.
Used for all tests. PostgreSQL implementation is a future drop-in.

### Schema Design

All persisted objects have:
- Stable identity (content hash, not UUID)
- Created timestamp (metadata, not in identity hash)
- Duplicate prevention (save returns False on conflict)

## Research Memory (`src/research/persistence/research_memory.py`)

High-level query layer answering:
- "Has this candidate been tested?" → `has_candidate(hash)`
- "Has this hypothesis been evaluated?" → `has_hypothesis(hash)`
- "Should we skip this experiment?" → `should_skip_experiment(id)`
- "What was the governance decision?" → `get_governance_history(id)`

## Queue State Machine (`src/research/queue/`)

### Task States

```
PENDING → CLAIMED → RUNNING → COMPLETED (terminal)
                            → FAILED → RETRYABLE → PENDING (retry)
                                     → REJECTED (terminal)
PENDING → CANCELLED (terminal)
```

### Properties

- **Atomic claiming**: `threading.Lock` in memory; database FOR UPDATE in PostgreSQL
- **Idempotent submission**: same content → same task_id, no duplicate
- **Bounded retry**: configurable `max_attempts`
- **Stale recovery**: tasks claimed but not started within timeout return to PENDING
- **Deterministic task_id**: hash of (task_type, candidate_hash, hypothesis_hash, payload)

## AI Researcher (`src/research/ai/`)

### Provider Abstraction

```python
class LLMProvider(ABC):
    def generate(prompt, system_prompt, temperature, max_tokens) → LLMResponse
    def is_available() → bool
```

Implementations:
- `MockLLMProvider` — deterministic responses for testing
- `DisabledProvider` — always unavailable (AI disabled mode)
- Future: `AnthropicProvider`, `OpenAIProvider`

### Research Agent

`ResearchAgent` uses an `LLMProvider` to propose structured hypotheses:
1. Builds prompt from `ResearchContext` (no secrets)
2. Calls LLM
3. Parses JSON response into `ResearchProposal`
4. Validates via `ProposalValidator`
5. Returns validated proposal or None

### Proposal Schema

```python
ResearchProposal(
    source=ProposalSource.AI,
    phase=ResearchPhase.EXPLORATION,
    market_type="CORNERS_TOTAL",
    feature_ids=("dangerous_attacks_home",),
    conditions=(...),
    direction="OVER",
    model_type="historical_frequency",
    prompt_version="v1",
    context_hash="...",
)
```

### Proposal Validation

Every proposal passes `ProposalValidator.validate()` checking:
- Market exists
- Direction valid
- Features exist (not post-match outcomes)
- Operator supported
- Model compatible
- Interaction depth within budget
- Odds mode valid

Invalid proposals → REJECTED (never auto-corrected).

## AI Safety Boundary

The AI **CANNOT**:
- Execute Python code (output parsed as JSON only)
- Execute SQL (output never reaches database directly)
- Access filesystem
- Modify experiment results
- Bypass FDR correction
- Bypass governance
- Promote strategies
- Place bets/orders
- Access credentials (context never includes secrets)

The AI **CAN ONLY**:
- Propose structured hypotheses
- Receive bounded research context
- Return JSON that must pass validation

## Research Context

`ResearchContext` provides bounded information to the AI:
- Available markets and features
- Previous candidates (limited count)
- Previous results summary
- Rejected/promising hypotheses

Never includes: API keys, database credentials, filesystem paths.

## Prompt Versioning

- System prompt versioned: `_SYSTEM_PROMPT_V1`
- Prompt version stored in every proposal: `prompt_version="v1"`
- Context hash stored: enables tracing proposal to exact context

## Budget / Cost Controls

`ResearchBudget` enforces:
- `max_tasks` — total tasks per run
- `max_experiments` — experiments limit
- `max_ai_proposals` — AI calls limit
- `max_candidates` — candidate generation limit
- `max_runtime_seconds` — wall-clock limit

Budget exhaustion is explicit. Never silently continues.

## Exploration vs Validation

Research phases are explicit:
- `EXPLORATION` — AI/initial proposals (no claim of validity)
- `VALIDATION` — multi-fold walk-forward evidence
- `CONFIRMATION` — FDR-corrected, governance-approved

AI proposals always enter EXPLORATION. Only the deterministic pipeline advances phase.

## Idempotency

- Same task content → same task_id (deterministic hash)
- Duplicate submission returns existing task (is_new=False)
- Already-executed experiments are skipped (memory check)
- Same proposal content → same content_hash

## Performance

In-memory benchmarks:
- 10,000 candidate inserts: <1s
- 10,000 task inserts: <1s
- 1,000 experiment inserts: <0.5s
- 1,000 duplicate lookups: <0.1s
- 1,000 sequential claims: <1s

## Known Limitations

1. **In-memory only** — PostgreSQL implementation pending
2. **No real LLM integration** — MockLLMProvider only
3. **No multi-worker distribution** — single-process queue
4. **No persistent task recovery** — in-memory state lost on restart
5. **No research orchestrator service** — manual pipeline execution
6. **No database migrations** — schema is the repository interface
7. **No async support** — synchronous batch operations only
