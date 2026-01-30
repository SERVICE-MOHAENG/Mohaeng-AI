# AI 개발팀 협업 가이드 (Ground Rule & Convention)

## 0. 핵심 철학
> **"AI의 속도(Speed)는 즐기되, AI의 부채(Debt)는 쌓지 않는다."**
- 복잡한 절차는 생략하고 **속도**와 **실용성**을 최우선으로 합니다.
- 단, **최소한의 안전장치(Pre-commit, CI)**는 반드시 준수합니다.

---

## 1. 기술 스택 & 개발 환경
- **Language**: Python 3.12 ≥
- **Package Manager**: `uv` (모든 의존성은 `uv.lock`으로 관리 및 커밋)
- **Linter**: `Ruff` (Black, Isort, Flake8 대체)
- **Editor**: Cursor 또는 VS Code

---

## 2. 브랜치 전략 (Github Flow)
- **Main Only**: `develop` 없음. `main`에서 따서 `main`으로 병합.
- **No Direct Push**: `main` 직접 푸시 금지.
- **Naming**:
    - `feat/`: 기능 추가 (`feat/rag-pipeline`)
    - `fix/`: 버그 수정 (`fix/login-error`)
    - `chore/`: 설정 변경 (`chore/init-ruff`)

---

## 3. 커밋 컨벤션

### 구조
`<Type> <Gitmoji>: <Subject> (#IssueNumber)`

### Type & Gitmoji
| Type | Gitmoji | 설명 |
| :--- | :--- | :--- |
| **feat** | ✨ | 새로운 기능 추가 |
| **fix** | 🐛 | 버그 수정 |
| **docs** | 📝 | 문서 수정 |
| **style**| 💄 | 코드 포맷팅 (로직 변경 없음) |
| **refactor**| ♻️ | 코드 리팩토링 |
| **test** | ✅ | 테스트 코드 |
| **chore**| 🔧 | 빌드/설정/패키지 |
| **design**| 🎨 | UI/UX 디자인 |
| **rename**| 🚚 | 파일 이동/이름 변경 |
| **remove**| 🔥 | 파일 삭제 |

---

## 4. 코드 품질 관리
- **Pre-commit**: `Ruff` 검사 통과 필수.
- **PR 규칙**: AI 생성 코드는 반드시 로직 및 보안 검증 후 PR 생성.

## 5. DevOps
- **Dockerfile**: `uv` 기반 멀티 스테이지 빌드 표준화.
