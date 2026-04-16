# Kubernetes Lab 筆記 / Lab Notes

> **課程：** MLIP — Orchestrating ML Training and Inference with Kubernetes

---

# 中文筆記

## Task 1：持續模型訓練 (CronJob)

### TODO 做了什麼

在 `model_trainer.py` 中，實作了用 **RandomForestRegressor**（100 棵決策樹）對合成使用者行為資料進行訓練：

```python
model = RandomForestRegressor(n_estimators=100, random_state=42)
model.fit(X, y)
```

**訓練資料特徵：**
- `avg_session_duration`：平均每次 session 時長（分鐘）
- `visits_per_week`：每週造訪次數
- `response_rate`：通知回應率（%）
- `feature_usage_depth`：使用功能數量

**目標變數：** `engagement_score`（0–100）

訓練完成後，模型存入 `/shared-volume/model.joblib`（Kubernetes PersistentVolume）。

---

### 步驟關聯

| 步驟 | 說明 |
|------|------|
| ① 合成資料生成 | `generate_synthetic_user_data(250)` 每次產生不同隨機資料 |
| ② RandomForest 訓練 | `model.fit(X, y)` |
| ③ 存入 PVC | `joblib.dump(model_info, '/shared-volume/model.joblib')` |
| ④ CronJob 排程 | `schedule: "*/1 * * * *"` 每分鐘觸發一次 |
| ⑤ Backend 重新載入 | background thread 每 30 秒自動 reload 最新模型 |

Trainer Pod 和 Backend Pod 共用同一個 PVC（`model-pvc`），透過共享儲存空間非同步傳遞模型。

---

### 如何 Demo

```bash
# 確認 CronJob 存在
kubectl get cronjobs

# 看每分鐘產生的 Job
kubectl get jobs

# 看訓練 log
kubectl logs -f job/<trainer-job-id>

# 確認模型每分鐘更新
curl http://127.0.0.1:<port>/model-info
# 觀察 "last_training_time" 每分鐘變化
```

---

### TA 解說重點

- **CronJob** 是 Kubernetes 的批次排程資源，類似 Linux `crontab`
- 每次觸發建立一個短暫的 **Job（Pod）**，執行完畢即結束
- **PersistentVolumeClaim (PVC)** 讓兩個不同 Pod（trainer / backend）共用同一塊儲存，實現模型的非同步傳遞
- `concurrencyPolicy: Forbid` 確保不會同時跑多個訓練 Job

---

## Task 2：後端推論服務 (Deployment + Service)

### TODO 做了什麼

在 `backend.py` 的 `/predict` 端點中，實作模型預測：

```python
engagement_score = float(current_model.predict(features)[0])
```

將請求的 JSON 欄位整理成 DataFrame，送進載入的模型，取回 `engagement_score` 回傳給 client。

---

### 步驟關聯

| 元件 | 角色 |
|------|------|
| Deployment (replicas: 2) | 啟動 2 個 Backend Pod，各自掛載 PVC (readOnly) |
| Background thread | 每 30 秒重新載入最新模型，確保使用最新版本 |
| Service (NodePort 30080) | 統一入口；kube-proxy 用 iptables/IPVS 把流量 round-robin 到各 replica |

---

### 如何 Demo

```bash
# 取得 tunnel URL
minikube service flask-backend-service
# 會印出 http://127.0.0.1:<port>

# 多次打 model-info，觀察 host 欄位切換
curl http://127.0.0.1:<port>/model-info

# 測試 predict
curl --request POST http://127.0.0.1:<port>/predict \
--header 'Content-Type: application/json' \
--data '{
    "avg_session_duration": 30,
    "visits_per_week": 14,
    "response_rate": 4,
    "feature_usage_depth": 6,
    "user_id": 34
}'
```

觀察 `"host"` 欄位在兩個 Pod 名稱之間切換，即代表負載平衡正在運作。

---

### TA 解說重點

- Kubernetes **Service** 用 label selector（`app: flask-backend`）找到所有對應的 Pod endpoints
- **kube-proxy** 維護 iptables 規則，每個進來的 TCP 連線依 round-robin 分配到其中一個 Pod
- `socket.gethostname()` 回傳 Pod 名稱，因此 `host` 欄位可直觀地觀察流量分散狀況
- 參考：[Kubernetes Services Networking](https://kubernetes.io/docs/concepts/services-networking/)

---

## Task 3：preStop Lifecycle Hook

### TODO 做了什麼

在 `backend-deployment.yaml` 的 `preStop` hook 設定：

```yaml
lifecycle:
  preStop:
    exec:
      command: ["/bin/sh", "-c", "kill -USR1 1 && sleep 5"]
```

| 指令 | 作用 |
|------|------|
| `kill -USR1 1` | 對 PID 1（Flask process）發送 SIGUSR1，觸發 `_handle_sigusr1`，印出準備關機的 log |
| `sleep 5` | 等待 5 秒，讓 in-flight 請求完成後再讓 Kubernetes 發 SIGTERM |

---

### Graceful Shutdown 完整順序

```
① Kubernetes 決定終止 Pod（rollout restart / scale down）
        ↓
② 執行 preStop hook
   → kill -USR1 1
   → 印出 "preStop signal received (SIGUSR1). Host preparing for shutdown: <pod-name>"
        ↓
③ sleep 5 秒（等待 in-flight 請求處理完畢）
        ↓
④ preStop hook 結束，Kubernetes 發送 SIGTERM
   → 印出 "SIGTERM received. Host being terminated: <pod-name>"
        ↓
⑤ sys.exit(0) 正常退出
```

---

### 如何 Demo

```bash
# Terminal A — 先開始監聽 log
kubectl logs -l app=flask-backend -f

# Terminal B — 觸發 rollout restart
kubectl rollout restart deployment/flask-backend-deployment
```

**預期 log 順序：**
```
preStop signal received (SIGUSR1). Host preparing for shutdown: flask-backend-deployment-...-7hg2m ...
preStop signal received (SIGUSR1). Host preparing for shutdown: flask-backend-deployment-...-wvp6j ...
  （約 5 秒後）
SIGTERM received. Host being terminated: flask-backend-deployment-...-7hg2m ...
SIGTERM received. Host being terminated: flask-backend-deployment-...-wvp6j ...
```

---

### TA 解說重點

- **preStop hook 在 SIGTERM 之前執行**，保證 app 有時間做清理工作
- **實際應用場景：**
  1. 關閉 DB 連線
  2. Flush 未寫入的 log buffer
  3. 通知 service discovery 下線（deregister）
  4. 完成正在處理的 batch job
- 這是 Kubernetes 實現 **zero-downtime deployment** 的關鍵機制之一
- 參考：[Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/)

---

# English Notes

## Task 1: Continuous Model Training (CronJob)

### What the TODO Implemented

In `model_trainer.py`, trained a **RandomForestRegressor** (100 trees) on synthetic user behavior data to predict `engagement_score`:

```python
model = RandomForestRegressor(n_estimators=100, random_state=42)
model.fit(X, y)
```

**Features:** `avg_session_duration`, `visits_per_week`, `response_rate`, `feature_usage_depth`

**Target:** `engagement_score` (0–100)

The trained model is saved to `/shared-volume/model.joblib` on a shared PersistentVolume.

---

### Step Sequence & Relationships

| Step | Description |
|------|-------------|
| ① Generate data | `generate_synthetic_user_data(250)` — new random samples each run |
| ② Train model | `model.fit(X, y)` |
| ③ Save to PVC | `joblib.dump(model_info, '/shared-volume/model.joblib')` |
| ④ CronJob schedule | `"*/1 * * * *"` — triggers a new Job every minute |
| ⑤ Backend reloads | Background thread reloads latest model from PVC every 30s |

The Trainer Pod and Backend Pod share the same PVC (`model-pvc`), enabling asynchronous model hand-off via shared storage.

---

### How to Demo

```bash
kubectl get cronjobs          # confirm model-trainer-job exists
kubectl get jobs              # see a new Job every minute
kubectl logs -f job/<id>      # see "Model trained and saved"
curl http://127.0.0.1:<port>/model-info   # last_training_time updates each minute
```

---

### Key Points for TA

- A **CronJob** is a Kubernetes resource for scheduled batch work, similar to Linux `crontab`
- Each trigger creates a short-lived **Job (Pod)** that runs to completion
- A **PersistentVolumeClaim (PVC)** allows two separate Pods to share storage, enabling async model delivery
- `concurrencyPolicy: Forbid` prevents multiple training Jobs from running simultaneously

---

## Task 2: Backend Inference Service (Deployment + Service)

### What the TODO Implemented

In `backend.py`'s `/predict` endpoint:

```python
engagement_score = float(current_model.predict(features)[0])
```

Assembles the incoming JSON fields into a DataFrame, runs inference with the loaded model, and returns the `engagement_score`.

---

### Step Sequence & Relationships

| Component | Role |
|-----------|------|
| Deployment (replicas: 2) | Runs 2 Backend Pods, each mounting the PVC (readOnly) |
| Background thread | Reloads latest model every 30s |
| Service (NodePort 30080) | Single entry point; kube-proxy distributes traffic round-robin via iptables/IPVS |

---

### How to Demo

```bash
minikube service flask-backend-service   # get tunnel URL: http://127.0.0.1:<port>

# Hit multiple times and watch "host" field alternate between 2 pod names
curl http://127.0.0.1:<port>/model-info

# Test prediction
curl --request POST http://127.0.0.1:<port>/predict \
--header 'Content-Type: application/json' \
--data '{"avg_session_duration": 30, "visits_per_week": 14, "response_rate": 4, "feature_usage_depth": 6, "user_id": 34}'
```

---

### Key Points for TA

- A Kubernetes **Service** uses a label selector (`app: flask-backend`) to discover all matching Pod endpoints
- **kube-proxy** maintains iptables rules so each TCP connection is distributed round-robin among Pods
- `socket.gethostname()` returns the Pod name — the `host` field makes load-balancing directly observable
- Reference: [Kubernetes Services Networking](https://kubernetes.io/docs/concepts/services-networking/)

---

## Task 3: preStop Lifecycle Hook

### What the TODO Implemented

In `backend-deployment.yaml`:

```yaml
lifecycle:
  preStop:
    exec:
      command: ["/bin/sh", "-c", "kill -USR1 1 && sleep 5"]
```

| Command | Effect |
|---------|--------|
| `kill -USR1 1` | Sends SIGUSR1 to PID 1 (Flask process), triggering `_handle_sigusr1` to log shutdown preparation |
| `sleep 5` | Waits 5 seconds for in-flight requests to complete before Kubernetes sends SIGTERM |

---

### Full Graceful Shutdown Sequence

```
① Kubernetes decides to terminate the Pod (rollout restart / scale down)
        ↓
② preStop hook runs
   → kill -USR1 1
   → logs "preStop signal received (SIGUSR1). Host preparing for shutdown: <pod-name>"
        ↓
③ sleep 5s (in-flight requests finish)
        ↓
④ preStop completes → Kubernetes sends SIGTERM
   → logs "SIGTERM received. Host being terminated: <pod-name>"
        ↓
⑤ sys.exit(0) — clean exit
```

---

### How to Demo

```bash
# Terminal A — start watching logs first
kubectl logs -l app=flask-backend -f

# Terminal B — trigger restart
kubectl rollout restart deployment/flask-backend-deployment
```

**Expected log order:**
```
preStop signal received (SIGUSR1). Host preparing for shutdown: ...
  (~5 seconds later)
SIGTERM received. Host being terminated: ...
```

---

### Key Points for TA

- **preStop runs before SIGTERM** — gives the app time to clean up gracefully
- **Practical use cases:**
  1. Close database connections
  2. Flush unwritten log buffers
  3. Deregister from service discovery
  4. Finish an in-progress batch job
- This is a key mechanism for **zero-downtime deployments** in Kubernetes
- References: [Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/) · [Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination)
