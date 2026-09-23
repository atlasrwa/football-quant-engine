"""ITEM 6 STAGE 2: incremental out-of-sample value of the frozen LLM-discovered search space.

DESIGN/BUILD/FREEZE ONLY. Nothing in this package calls an LLM, reads a target outcome, reads a
market price, or computes an out-of-sample metric. Stage-2 execution requires separate explicit
human authorization.
"""
STAGE2_PACKAGE_VERSION = "item6_stage2_v1"
