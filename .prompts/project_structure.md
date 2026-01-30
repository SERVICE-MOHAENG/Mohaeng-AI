# Project Directory Structure

## Root
- `app/`: 메인 소스 코드
- `scripts/`: 데이터 파이프라인 스크립트
- `tests/`: 테스트 코드
- `.prompts/`: AI 컨텍스트 문서 (본 폴더)
- `.github/`: GitHub 설정 (Issue 템플릿, CI 워크플로우)

## Key Directories
- `app/services/`: 비즈니스 로직 (`crawler.py`, `embedding.py`)
- `app/core/`: 설정 (`config.py`)
- `app/graph/`: LangGraph 워크플로우
- `app/models/`: DB 모델 (`city.py`)
- `app/api/`: FastAPI 엔드포인트
- `app/schemas/`: Pydantic 스키마
- `app/tools/`: LangGraph 도구

## Tree Context
```
.
├── app
│   ├── api
│   ├── core
│   ├── graph
│   ├── models
│   ├── schemas
│   ├── services
│   └── tools
├── scripts
├── tests
├── .github
│   ├── ISSUE_TEMPLATE
│   └── workflows
├── .prompts
├── Dockerfile
├── pyproject.toml
├── README.md
└── uv.lock
```

## Database
- **Vector DB**: PostgreSQL + pgvector (코사인 유사도 검색)
