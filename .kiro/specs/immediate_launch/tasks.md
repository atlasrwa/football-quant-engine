# Tasks: Frontend Strategy Builder UI, Community Signal Pipeline & Execution Deep-Linker

#[[file:design.md]]

## Phase 1: Builder Templates API

- [x] Task 1: Create `src/api/routes/builder_ui.py` with benchmark template data
- [x] Task 2: Implement `get_templates()` and `get_template_by_metric()` endpoints

## Phase 2: Community Broadcaster

- [x] Task 3: Create `src/engine/signals/community_broadcaster.py`
- [x] Task 4: Implement `BroadcastConfig` and `CommunityBroadcaster` class
- [x] Task 5: Implement `run_once()` — process signals and format broadcasts
- [x] Task 6: Implement `format_broadcast_telegram()` with deep-link buttons
- [x] Task 7: Implement `format_broadcast_discord()` with rich embeds

## Phase 3: Deep-Linker

- [x] Task 8: Create `src/engine/signals/deeplinker.py`
- [x] Task 9: Implement `DeepLinker.generate_links()` for Stake/Rollbit/Polymarket
- [x] Task 10: Implement `generate_telegram_buttons()` inline keyboard
- [x] Task 11: Implement affiliate tag injection

## Phase 4: Benchmark Strategies

- [x] Task 12: Create 4× xC Corner Pressure strategy JSONs
- [x] Task 13: Create 3× xB Booking Friction strategy JSONs
- [x] Task 14: Create 3× xO High-Line Offside strategy JSONs

## Phase 5: Tests

- [x] Task 15: Create `tests/test_community_broadcaster.py`
- [x] Task 16: Create `tests/test_deeplinker.py`

## Phase 6: Integration

- [x] Task 17: Verify all tests pass and push to main
