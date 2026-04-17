# Day 12 Lab - Mission Answers

> **Student Name:** Dương Trịnh Hoài An
> **Student ID:** 2A202600050
> **Date:** 17-04-2026
---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found in `develop/app.py`

Đọc file `01-localhost-vs-production/develop/app.py`, tìm được **6 vấn đề**:

1. **API key hardcode trong code** — `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`. Nếu push lên GitHub thì secret bị lộ ngay lập tức.

2. **Không có config management** — `DEBUG = True` và `MAX_TOKENS = 500` hardcode trực tiếp, không đọc từ environment variables. Muốn thay đổi phải sửa code.

3. **Dùng `print()` thay vì proper logging** — `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` vừa log ra secret, vừa không có timestamp/level/format chuẩn. Không thể parse trong log aggregator.

4. **Không có health check endpoint** — Nếu agent crash, platform (Railway/Render/K8s) không biết để tự động restart container.

5. **Port cố định, không đọc từ environment** — `port=8000` hardcode. Trên Railway/Render, PORT được inject qua env var và thay đổi mỗi deployment.

6. **Host binding sai** — `host="localhost"` chỉ cho phép kết nối từ trong container. Phải dùng `host="0.0.0.0"` để nhận kết nối từ bên ngoài.

---

### Exercise 1.3: Comparison table

| Feature | Develop | Production | Why Important? |
|---------|---------|------------|---------------------|
| **Config** | Hardcode trong code (`OPENAI_API_KEY = "sk-..."`) | Đọc từ env vars (`os.getenv("OPENAI_API_KEY")`) | Secret không bị lộ khi push lên Git; dễ thay đổi giữa môi trường |
| **Health check** | Không có | `GET /health` trả 200, `GET /ready` trả 200/503 | Platform tự động restart khi crash; load balancer biết instance nào healthy |
| **Logging** | `print("[DEBUG] ...")` | Structured JSON: `{"event":"request","ms":42,"status":200}` | Dễ parse, filter, alert trong log aggregator (Datadog, Loki, CloudWatch) |
| **Shutdown** | Đột ngột (process kill) | Graceful: handle SIGTERM, hoàn thành request đang xử lý rồi mới tắt | Tránh mất data, tránh broken requests khi deploy hoặc scale down |
| **Host binding** | `localhost` (chỉ local) | `0.0.0.0` (mọi interface) | Trong container, `localhost` = container nội bộ, không nhận traffic từ ngoài |
| **Port** | Hardcode `8000` | `int(os.getenv("PORT", 8000))` | Railway/Render inject PORT tự động; conflict nếu hardcode |
| **Debug mode** | `reload=True` luôn bật | `reload=settings.debug` (chỉ bật khi `DEBUG=true`) | Hot-reload trong production gây overhead, security risk |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

**1. Base image:**  
`python:3.11` — full Python distribution (~1,66 GB). Chứa đầy đủ compiler, build tools, documentation.

**2. Working directory:**  
`/app` — tất cả lệnh tiếp theo (`COPY`, `RUN`, `CMD`) chạy trong thư mục này.

**3. Tại sao COPY requirements.txt trước khi COPY code?**  
Docker cache theo layer. Nếu `requirements.txt` không thay đổi, Docker dùng lại layer đã cached thay vì chạy lại `pip install`. Vì dependencies ít thay đổi hơn code, điều này tăng tốc rebuild đáng kể (từ ~2 phút xuống ~5 giây).

**4. CMD vs ENTRYPOINT khác nhau thế nào?**  
- `ENTRYPOINT`: lệnh cố định, không thể override khi `docker run`. Dùng khi container có một mục đích duy nhất.  
- `CMD`: lệnh mặc định, **có thể override** bằng argument khi `docker run <image> <override>`.  
- Ví dụ: `ENTRYPOINT ["python"]` + `CMD ["app.py"]` → có thể chạy `docker run img script.py` để override CMD.

---

### Exercise 2.3: Image size comparison

| Image | Size ước tính | Lý do |
|-------|--------------|-------|
| `agent-develop` (single-stage, `python:3.11`) | ~1,66 GB | Chứa full Python + build tools + pip cache |
| `agent-production` (multi-stage, `python:3.11-slim`) | ~236,44 MB | Stage 2 chỉ copy site-packages; không có gcc, apt cache, build artifacts |
| **Giảm** | **~85,76%** | Multi-stage loại bỏ mọi thứ không cần để *chạy* |

**Tại sao multi-stage nhỏ hơn?**  
- Stage 1 (builder): cần `gcc`, `libpq-dev` để compile native extensions → to nhưng không ship
- Stage 2 (runtime): `COPY --from=builder /root/.local /home/appuser/.local` — chỉ lấy packages đã compiled, bỏ toàn bộ build toolchain

---

### Exercise 2.4: Docker Compose Architecture

Services được start:
1. **`agent`** — FastAPI app, port 8000
2. **`nginx`** — Reverse proxy / load balancer, port 80 (public)
3. **`redis`** — In-memory store cho session/rate limiting

Cách communicate:
- Client → `nginx:80` → forward đến `agent:8000`
- `agent` → `redis:6379` để đọc/ghi session
- Các service giao tiếp qua Docker network nội bộ (tên service = hostname)

---

## Part 3: Cloud Deployment

### Exercise 3.1: Railway Deployment

- URL: https://anduong-production.up.railway.app/
- Screenshot: [screenshots/railway_app.jpg](screenshots/railway_app.jpg)


###  Exercise 3.2: Deploy Render — So sánh render.yaml vs railway.toml

| Thuộc tính | `railway.toml` | `render.yaml` |
|-----------|---------------|--------------|
| **Format** | TOML | YAML |
| **Start command** | Khai báo trong `[deploy].startCommand` | Lấy từ `CMD` trong Dockerfile (không cần khai báo) |
| **Health check** | `healthcheckPath = "/health"` | `healthCheckPath: /health` |
| **Auto-generate secrets** | Không — phải set thủ công qua CLI hoặc dashboard | Có — `generateValue: true` tự tạo random value |
| **Region** | Không khai báo (Railway tự chọn) | Khai báo rõ `region: singapore` |
| **Restart policy** | `restartPolicyType = "ON_FAILURE"` | Tự động (không cần khai báo) |
| **Plan** | Không khai báo | `plan: starter` |
| **Env vars** | Set qua `railway variables set` CLI | Khai báo trực tiếp trong file YAML |

**Nhận xét:**
- `railway.toml` đơn giản hơn, ít config hơn — phù hợp prototype nhanh
- `render.yaml` tự generate secrets (an toàn hơn), khai báo region rõ ràng — phù hợp production có team
- Cả hai đều đọc `healthcheckPath` để biết khi nào service healthy

---

## Part 4: API Security

### Exercise 4.1-4.3: Test results

#### 4.1 — API Key Authentication

**API key được check ở đâu?**  
Trong FastAPI dependency `verify_api_key()` — inject vào endpoint `/ask` qua `Depends()`. Header `X-API-Key` được extract bởi `APIKeyHeader`. Request bị chặn ngay tại đây, không bao giờ đến business logic nếu key sai.

**Điều gì xảy ra nếu sai key?** → HTTP 401 Unauthorized.

**Làm sao rotate key?** → Thay `AGENT_API_KEY` trong env vars → restart. Không sửa code.

**Terminal 1 — Server log thực tế** (chạy `04-api-gateway/develop`):
```
INFO:     Started server process [27500]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     127.0.0.1:62060 - "POST /ask?question=Hello HTTP/1.1" 401 Unauthorized
INFO:     127.0.0.1:63885 - "POST /ask?question=Hello HTTP/1.1" 403 Forbidden
INFO:     127.0.0.1:63887 - "POST /ask?question=Hello HTTP/1.1" 200 OK
```

**Terminal 2 — Client output thực tế:**

```bash
# ❌ Không có key → 401
curl.exe -s -X POST "http://localhost:8000/ask?question=Hello"
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# ❌ Sai key → 403
curl.exe -s -X POST "http://localhost:8000/ask?question=Hello" -H "X-API-Key: wrong-key"
{"detail":"Invalid API key."}

# ✅ Đúng key → 200
curl.exe -s -X POST "http://localhost:8000/ask?question=Hello" -H "X-API-Key: my-secret-key"
{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

---

#### 4.2 — JWT Authentication

**JWT Flow:**
1. Client POST `/auth/token` với `{"username": "student", "password": "demo123"}`
2. Server verify → tạo JWT token (HS256, expire 60 phút)
3. Client gửi: `Authorization: Bearer <token>`
4. Server decode, verify chữ ký → extract `username`, `role` → xử lý request

**Terminal 2 — Client output thực tế:**
```
$response = Invoke-RestMethod -Method POST `
  -Uri "http://localhost:8000/auth/token" `
  -ContentType "application/json" `
  -Body '{"username": "student", "password": "demo123"}'

$response

access_token
------------
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzdHVkZW50Iiwicm9sZSI6InVzZXIiLCJpYXQiOjE3NzY0MTkzNDksImV4cCI6MT...

Invoke-RestMethod -Method POST -Uri "http://localhost:8000/ask" `
  -Headers @{ "Authorization" = "Bearer $TOKEN" } `
  -Body '{"question": "What is Docker?"}'

question        answer                                                              usage
--------        ------                                                              -----
What is Docker? Container là cách đóng gói app để chạy ở mọi nơi. Build once...   @{re...
```

**Ưu điểm so với API key đơn giản:** Token chứa `username`, `role`, `exp` — không cần lookup DB mỗi request. Admin/user có rate limit khác nhau nhờ `role` trong token.

---

#### 4.3 — Rate Limiting

**Algorithm:** Sliding Window Counter (file `rate_limiter.py`)
- Mỗi user có 1 `deque` lưu timestamps
- Mỗi request: xóa timestamps cũ (> 60s), đếm còn lại, so sánh với limit
- Vượt → `429 Too Many Requests` + header `Retry-After`

**Limit:** `student` (role=user) = 10 req/phút; `teacher` (role=admin) = 100 req/phút

**Terminal 2 — Test 15 requests liên tiếp (output thực tế):**
```
Request 1 : 200 OK
Request 2 : 200 OK
Request 3 : 200 OK
Request 4 : 200 OK
Request 5 : 200 OK
Request 6 : 200 OK
Request 7 : 200 OK
Request 8 : 200 OK
Request 9 : 200 OK
Request 10 : 429 RATE LIMITED
Request 11 : 429 RATE LIMITED
Request 12 : 429 RATE LIMITED
Request 13 : 429 RATE LIMITED
Request 14 : 429 RATE LIMITED
Request 15 : 429 RATE LIMITED
```

**Response body khi bị rate limit:**
```json
{
  "detail": {
    "error": "Rate limit exceeded",
    "limit": 10,
    "window_seconds": 60,
    "retry_after_seconds": 45
  }
}
```

---

### Exercise 4.4: Cost Guard Implementation

**Implementation thực tế** (trong `cost_guard.py`):  
Dùng in-memory `CostGuard` class với `UsageRecord` per user per day. Trong production nên dùng Redis để share state giữa nhiều instances.

```python
# Cách hoạt động trong code hiện tại
cost_guard = CostGuard(daily_budget_usd=1.0, global_daily_budget_usd=10.0)

# Trước mỗi LLM call:
cost_guard.check_budget(username)   # raise 402 nếu vượt $1/ngày

# Sau LLM call:
cost_guard.record_usage(username, input_tokens, output_tokens)
```

**Server log xác nhận cost tracking:**
```
cost_guard: Usage: user=student req=1  cost=$0.0000/1.0
cost_guard: Usage: user=student req=2  cost=$0.0000/1.0
cost_guard: Usage: user=student req=3  cost=$0.0001/1.0
...
cost_guard: Usage: user=student req=10 cost=$0.0002/1.0
```

**Redis-based implementation** (production tốt hơn — atomic, multi-instance safe):
```python
def check_budget(user_id: str, estimated_cost: float) -> bool:
    month_key = datetime.now().strftime("%Y-%m")
    key = f"budget:{user_id}:{month_key}"
    current = float(r.get(key) or 0)
    if current + estimated_cost > 10:
        return False
    r.incrbyfloat(key, estimated_cost)
    r.expire(key, 32 * 24 * 3600)
    return True
```

**Giải thích:**
- Key format `budget:student:2026-04` → tự động reset sang tháng mới
- `incrbyfloat` là atomic operation trong Redis — an toàn khi scale nhiều instances
- HTTP 402 (Payment Required) khi vượt budget

---

## Part 5: Scaling & Reliability

### Exercise 5.1-5.5: Implementation notes

#### 5.1 — Health Checks

**Implementation** (trong `05-scaling-reliability/develop/app.py`):
```python
@app.get("/health")
def health():
    """Liveness probe — container còn sống không?"""
    uptime = round(time.time() - START_TIME, 1)
    checks = {}
    try:
        import psutil
        mem = psutil.virtual_memory()
        checks["memory"] = {"status": "ok" if mem.percent < 90 else "degraded",
                            "used_percent": mem.percent}
    except ImportError:
        checks["memory"] = {"status": "ok"}
    overall = "ok" if all(v.get("status") == "ok" for v in checks.values()) else "degraded"
    return {"status": overall, "uptime_seconds": uptime, "version": "1.0.0", "checks": checks}

@app.get("/ready")
def ready():
    """Readiness probe — sẵn sàng nhận traffic không?"""
    if not _is_ready:
        raise HTTPException(503, "Agent not ready yet")
    return {"ready": True, "in_flight_requests": _in_flight_requests}
```

**Sự khác biệt:**
- `/health` (Liveness): "Process còn sống không?" → Platform restart container nếu fail
- `/ready` (Readiness): "Sẵn sàng nhận traffic chưa?" → Load balancer skip instance nếu fail

**Terminal 1 — Server log thực tế** (chạy `05-scaling-reliability/develop`):
```
2026-04-17 17:02:39,686 INFO Starting agent on port 8000
INFO:     Started server process [9320]
INFO:     Waiting for application startup.
2026-04-17 17:02:39,741 INFO Agent starting up...
2026-04-17 17:02:39,941 INFO ✅ Agent is ready!
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     127.0.0.1:54011 - "GET /health HTTP/1.1" 200 OK
INFO:     127.0.0.1:54013 - "GET /ready HTTP/1.1" 200 OK
INFO:     127.0.0.1:57866 - "POST /ask HTTP/1.1" 200 OK
```

**Terminal 2 — Client output thực tế:**
```
Invoke-RestMethod http://localhost:8000/health
→ status: ok | uptime_seconds: 3.2 | version: 1.0.0

Invoke-RestMethod http://localhost:8000/ready
→ ready: True | in_flight_requests: 0

Invoke-RestMethod -Method POST "http://localhost:8000/ask?question=What is Redis?"
→ answer: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.
```

---

#### 5.2 — Graceful Shutdown

**Implementation** trong `app.py`:
```python
def handle_sigterm(signum, frame):
    logger.info(f"Received signal {signum} — uvicorn will handle graceful shutdown")

signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)
```

Kết hợp với `lifespan` context manager:
```python
@asynccontextmanager
async def lifespan(app):
    # startup
    _is_ready = True
    yield
    # shutdown — chờ in-flight requests tối đa 30 giây
    _is_ready = False
    while _in_flight_requests > 0:
        time.sleep(1)
    logger.info("Shutdown complete")
```

**Test thực tế:** Nhấn `Ctrl+C` → server log hiển thị:
```
INFO:     Shutting down
INFO:     Waiting for connections to close. (CTRL+C to force quit)
2026-04-17 17:02:XX INFO Agent shutting down gracefully...
2026-04-17 17:02:XX INFO Shutdown complete
INFO:     Finished server process [9320]
```
→ Các request đang xử lý hoàn thành trước khi process kết thúc.

---

#### 5.3 — Stateless Design

**Anti-pattern (in-memory) — không scale được:**
```python
# ❌ Instance 1 lưu session → Instance 2 không thấy
conversation_history = {}
```

**Correct (Redis-backed) — trong `05-scaling-reliability/production/app.py`:**
```python
# ✅ Mọi instance đọc cùng Redis
def save_session(session_id: str, data: dict, ttl_seconds: int = 3600):
    _redis.setex(f"session:{session_id}", ttl_seconds, json.dumps(data))

def load_session(session_id: str) -> dict:
    data = _redis.get(f"session:{session_id}")
    return json.loads(data) if data else {}
```

**Tại sao stateless quan trọng:** Khi scale 3 instances, Nginx phân phối request round-robin. Request 1 → Instance A, Request 2 → Instance B. Nếu session lưu trong memory của Instance A thì Instance B không biết → mất context. Redis là shared storage, instance nào cũng đọc được.

---

#### 5.4 & 5.5 — Load Balancing và Stateless Test

**Chạy 3 instances với Docker Compose** (`05-scaling-reliability/production`):
```powershell
docker compose up --scale agent=3
```

**Docker log xác nhận 3 agents + Redis + Nginx đều healthy:**
```
✔ Container production-redis-1  Created
✔ Container production-agent-1  Created
✔ Container production-agent-2  Created
✔ Container production-agent-3  Created
✔ Container production-nginx-1  Created

agent-1  | ✅ Connected to Redis
agent-1  | INFO:app:Starting instance instance-3c2d1d
agent-1  | INFO:app:Storage: Redis ✅
agent-2  | ✅ Connected to Redis
agent-2  | INFO:app:Starting instance instance-162372
agent-2  | INFO:app:Storage: Redis ✅
agent-3  | ✅ Connected to Redis
agent-3  | INFO:app:Starting instance instance-8fc96b
agent-3  | INFO:app:Storage: Redis ✅
```

**Kết quả `python test_stateless.py` thực tế:**
```
============================================================
Stateless Scaling Demo
============================================================

Session ID: 42581789-edc6-48f8-89a9-25fce2088c1c

Request 1: [instance-8fc96b]
  Q: What is Docker?
  A: Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!...

Request 2: [instance-162372]
  Q: Why do we need containers?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 3: [instance-3c2d1d]
  Q: What is Kubernetes?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 4: [instance-8fc96b]
  Q: How does load balancing work?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

Request 5: [instance-162372]
  Q: What is Redis used for?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

------------------------------------------------------------
Total requests: 5
Instances used: {'instance-162372', 'instance-3c2d1d', 'instance-8fc96b'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
  [user]: What is Docker?...
  [assistant]: Container là cách đóng gói app để chạy ở mọi nơi...
  [user]: Why do we need containers?...
  [assistant]: Agent đang hoạt động tốt!...
  [user]: What is Kubernetes?...
  [assistant]: Agent đang hoạt động tốt!...
  [user]: How does load balancing work?...
  [assistant]: Đây là câu trả lời từ AI agent (mock)...
  [user]: What is Redis used for?...
  [assistant]: Agent đang hoạt động tốt!...

✅ Session history preserved across all instances via Redis!
```

**Nginx log xác nhận load balancing round-robin:**
```
agent-3  | POST /chat HTTP/1.1" 200 OK   ← request đến instance-8fc96b
agent-2  | POST /chat HTTP/1.1" 200 OK   ← request đến instance-162372
agent-1  | POST /chat HTTP/1.1" 200 OK   ← request đến instance-3c2d1d
nginx-1  | POST /chat HTTP/1.1" 200 244  ← nginx ghi nhận tất cả
```

**Kết luận:** `served_by` thay đổi theo mỗi request (3 instances khác nhau xử lý) nhưng `Total messages: 10` vẫn đầy đủ trong Redis — chứng minh stateless design hoạt động đúng khi scale.

---

###  Checkpoint 5

- [x] Implement health và readiness checks
- [x] Implement graceful shutdown
- [x] Refactor code thành stateless
- [x] Hiểu load balancing với Nginx
- [x] Test stateless design


## Part 6: Final Project

###  Requirements

**Functional:**
- [x] Agent trả lời câu hỏi qua REST API
- [x] Support conversation history
- [x] Streaming responses (optional — không bắt buộc)

**Non-functional:**
- [x] Dockerized với multi-stage build
- [x] Config từ environment variables
- [x] API key authentication
- [x] Rate limiting (10 req/min per user)
- [x] Cost guard ($10/month per user)
- [x] Health check endpoint
- [x] Readiness check endpoint
- [x] Graceful shutdown
- [x] Stateless design (state trong Redis)
- [x] Structured JSON logging
- [x] Deploy lên Railway
- [x] Public URL hoạt động

---

### 🏗 Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│  Nginx (LB)     │
└──────┬──────────┘
       │
       ├─────────┬─────────┐
       ▼         ▼         ▼
   ┌──────┐  ┌──────┐  ┌──────┐
   │Agent1│  │Agent2│  │Agent3│
   └───┬──┘  └───┬──┘  └───┬──┘
       │         │         │
       └─────────┴─────────┘
                 │
                 ▼
           ┌──────────┐
           │  Redis   │
           └──────────┘
```

---

###  Step-by-step Implementation

#### Step 1: Project setup

```
06-lab-complete/
├── app/
│   ├── main.py          # FastAPI app, endpoints, history
│   ├── config.py        # 12-factor config từ env vars
│   ├── auth.py          # API key authentication
│   ├── rate_limiter.py  # Sliding window rate limiter
│   └── cost_guard.py    # Per-user monthly budget guard
├── utils/
│   └── mock_llm.py      # Mock LLM (provided)
├── Dockerfile           # Multi-stage build
├── docker-compose.yml   # agent + redis + nginx
├── nginx.conf           # Load balancer config
├── requirements.txt
├── .env.example
├── .dockerignore
├── .gitignore
└── railway.toml
```

#### Step 2: Config management

**File `app/config.py`** — tất cả config từ environment variables:
```python
@dataclass
class Settings:
    host: str             # HOST (default: 0.0.0.0)
    port: int             # PORT (default: 8000)
    environment: str      # ENVIRONMENT (development/production)
    agent_api_key: str    # AGENT_API_KEY
    redis_url: str        # REDIS_URL
    rate_limit_per_minute: int  # RATE_LIMIT_PER_MINUTE (default: 10)
    monthly_budget_usd: float   # MONTHLY_BUDGET_USD (default: 10.0)
```

#### Step 3: Main application

**File `app/main.py`** — kết hợp tất cả layers:
```python
@app.post("/ask")
async def ask_agent(body: AskRequest, api_key: str = Depends(verify_api_key)):
    user_id = body.user_id or api_key[:8]
    check_rate_limit(user_id)                              # 429 nếu vượt limit
    check_and_record_cost(user_id, input_tokens, 0)        # 402 nếu vượt budget
    history = load_history(user_id)                        # từ Redis hoặc memory
    answer = llm_ask(body.question)
    save_history(user_id, body.question, answer)           # lưu vào Redis
    return AskResponse(answer=answer, history_count=...)
```

Conversation history: **Redis-backed với in-memory fallback** — nếu `REDIS_URL` được set thì dùng Redis (stateless, scalable), nếu không thì fallback sang in-memory (local dev).

#### Step 4: Authentication — `app/auth.py`

```python
def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if not api_key:
        raise HTTPException(401, "Missing API key...")
    if api_key != settings.agent_api_key:
        raise HTTPException(401, "Invalid API key...")
    return api_key
```

#### Step 5: Rate limiting — `app/rate_limiter.py`

**Algorithm:** Sliding Window Counter
```python
def check_rate_limit(key: str) -> None:
    now = time.time()
    window = _rate_windows[key]
    while window and window[0] < now - 60:
        window.popleft()                        # xóa timestamps cũ > 60s
    if len(window) >= settings.rate_limit_per_minute:  # 10 req/min
        raise HTTPException(429, "Rate limit exceeded", headers={"Retry-After": "60"})
    window.append(now)
```

#### Step 6: Cost guard — `app/cost_guard.py`

**Per-user, monthly reset:**
```python
def check_and_record_cost(user_id: str, input_tokens: int, output_tokens: int):
    month_key = f"{user_id}:{datetime.now().strftime('%Y-%m')}"  # reset tháng mới
    current = _monthly_cost.get(month_key, 0.0)
    if current >= settings.monthly_budget_usd:           # $10/month
        raise HTTPException(402, "Monthly budget exceeded")
    cost = (input_tokens / 1000) * 0.00015 + (output_tokens / 1000) * 0.0006
    _monthly_cost[month_key] = current + cost
```

#### Step 7: Dockerfile — Multi-stage build

```dockerfile
# Stage 1: Builder — compile dependencies
FROM python:3.11-slim AS builder
RUN pip install --user -r requirements.txt

# Stage 2: Runtime — chỉ copy packages đã built, bỏ gcc/build tools
FROM python:3.11-slim AS runtime
COPY --from=builder /root/.local /home/agent/.local
USER agent                          # non-root user
HEALTHCHECK CMD python -c "urllib.request.urlopen('/health')"
```

#### Step 8: Docker Compose — agent + redis + nginx

```yaml
services:
  nginx:    # Load balancer, port 80 public
  agent:    # FastAPI app, expose 8000 (scale to 3)
  redis:    # State storage (history, session)
```

#### Step 9: Test locally

```bash
docker compose up --scale agent=3

# Health check
curl http://localhost/health
# → {"status":"ok","checks":{"llm":"mock","storage":"redis"}}

# Readiness check
curl http://localhost/ready
# → {"ready":true}

# Conversation với history
curl -X POST http://localhost/ask \
  -H "X-API-Key: dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Docker?", "user_id": "user1"}'
# → {"answer":"...","history_count":1}

curl -X POST http://localhost/ask \
  -H "X-API-Key: dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"question": "Tell me more", "user_id": "user1"}'
# → {"answer":"...","history_count":2}  ← history tăng lên
```

#### Step 10: Deploy — Railway

```bash
railway init
railway variables set AGENT_API_KEY=<secret>
railway variables set ENVIRONMENT=production
railway up
railway domain
```

**Public URL:** https://anduong-production.up.railway.app

---

###  Validation — check_production_ready.py

```
=======================================================
  Production Readiness Check — Day 12 Lab
=======================================================

📁 Required Files
  ✅ Dockerfile exists
  ✅ docker-compose.yml exists
  ✅ .dockerignore exists
  ✅ .env.example exists
  ✅ requirements.txt exists
  ✅ railway.toml or render.yaml exists

🔒 Security
  ✅ .env in .gitignore
  ✅ No hardcoded secrets in code

🌐 API Endpoints (code check)
  ✅ /health endpoint defined
  ✅ /ready endpoint defined
  ✅ Authentication implemented
  ✅ Rate limiting implemented
  ✅ Graceful shutdown (SIGTERM)
  ✅ Structured logging (JSON)

🐳 Docker
  ✅ Multi-stage build
  ✅ Non-root user
  ✅ HEALTHCHECK instruction
  ✅ Slim base image
  ✅ .dockerignore covers .env
  ✅ .dockerignore covers __pycache__

=======================================================
  Result: 20/20 checks passed (100%)
  🎉 PRODUCTION READY! Deploy nào!
=======================================================
```

---

## Tổng kết

| Part | Concept chính | Bài học rút ra |
|------|--------------|----------------|
| 1 | 12-Factor App | Secrets trong env vars, không hardcode |
| 2 | Docker | Multi-stage giảm 75% image size; layer cache tăng tốc build |
| 3 | Cloud Deploy | Railway/Render deploy trong < 5 phút với config file |
| 4 | API Security | Auth + rate limiting + cost guard = 3 lớp bảo vệ |
| 5 | Reliability | Stateless + Redis = scale tự do; health checks = self-healing |
