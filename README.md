# Memory Fabric: Shared Memory & Coordination Layer for AI Agents

Memory Fabric is a shared memory and coordination infrastructure built on FalkorDB, exposed to autonomous agent crews via the Model Context Protocol (MCP).

## Overview

A customer-support agent crew (Triage, Billing, Technical Specialists) coordinates seamlessly across sessions with:
- **Episodic Memory**: Past session contexts and summarized incident learnings.
- **Semantic Memory**: Long-term facts with provenance, temporal validity, and supersession chains.
- **Procedural Memory**: Reusable operational workflows that are learned from execution outcomes and promoted upon repeated success.
- **Multi-Tenant Graph Isolation**: Hard security boundary with one dedicated FalkorDB graph (`mem_<tenant_id>`) per tenant.

## Hackathon Track
- **Graph Hacks 2026**: *Agent Memory and Coordination*
