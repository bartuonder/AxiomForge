# Project: AxiomForge - Autonomous AI Research Agent

## Architecture & Tech Stack
- **LLM:** OpenAI API (GPT-4o serisi). Tüm API çağrıları için `.env` dosyasındaki `OPENAI_API_KEY` kullanılacaktır.
- **Orchestration:** LangGraph + PostgreSQL.
- **Sandbox:** E2B or Modal.
- **Tracking:** MLflow.
- **Backend/Queue:** FastAPI + Celery & Redis.
- **Frontend:** Next.js.

## Cursor Development Directive (CRITICAL)
NEVER attempt to build the entire system at once. We will proceed step-by-step. 
1. Always check the `.env` file for credentials like `OPENAI_API_KEY`.
2. Do not leave "TODO" or placeholder code. Write complete, production-ready code for the specific small task I give you.
3. Wait for my confirmation before moving to the next logical step.