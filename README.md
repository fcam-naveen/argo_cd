# FastAPI Blue-Green Deployment with Argo CD & Argo Rollouts

A complete example of blue-green deployments for a FastAPI application using
**Argo Rollouts** (for traffic management) and **Argo CD** (for GitOps delivery).

---

## Repository Structure

```
fastapi-blue-green/
├── app/
│   ├── main.py              # FastAPI application (exposes /health, /info)
│   ├── requirements.txt
│   └── Dockerfile
├── helm/
│   └── fastapi-app/
│       ├── Chart.yaml
│       ├── values.yaml          # Default values
│       ├── values-v1.yaml       # Stable (blue) overrides
│       ├── values-v2.yaml       # New (green) overrides
│       └── templates/
│           ├── _helpers.tpl
│           ├── rollout.yaml     # Argo Rollouts Rollout resource
│           ├── services.yaml    # Active + Preview services
│           └── ingress.yaml     # Optional ingress
├── argocd/
│   ├── application.yaml         # Argo CD Application
│   └── appproject.yaml          # Argo CD AppProject (optional)
└── README.md
```

---

## How Blue-Green Works Here

```
                        ┌─────────────────────────────────┐
                        │          Argo CD                 │
                        │  Watches Git → syncs Helm chart  │
                        └────────────────┬────────────────┘
                                         │ applies
                                         ▼
                        ┌─────────────────────────────────┐
                        │       Argo Rollouts              │
                        │   (manages the Rollout CRD)      │
                        └────────────┬────────────────────┘
                    creates/scales   │
               ┌─────────────────────┴──────────────────────┐
               ▼                                             ▼
   ┌─────────────────────┐                     ┌────────────────────────┐
   │  ReplicaSet BLUE     │                     │  ReplicaSet GREEN      │
   │  (current stable)   │                     │  (new candidate)       │
   │  image: v1.0.0       │                     │  image: v2.0.0         │
   └─────────┬───────────┘                     └───────────┬────────────┘
             │                                             │
             ▼                                             ▼
   ┌─────────────────┐                         ┌──────────────────────┐
   │  fastapi-active  │  ← production traffic   │  fastapi-preview     │
   │  (ClusterIP svc) │                         │  (ClusterIP svc)     │
   └─────────────────┘                         └──────────────────────┘
```

**Key insight:** Argo Rollouts automatically injects a `rollouts-pod-template-hash`
label selector on both services, ensuring `fastapi-active` always points to the
stable ReplicaSet and `fastapi-preview` always points to the new one — without
any manual service patching.

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| `kubectl` | ≥ 1.27 | Cluster access |
| `helm` | ≥ 3.12 | Chart rendering/install |
| Argo CD | ≥ 2.9 | GitOps controller |
| Argo Rollouts | ≥ 1.6 | Blue-green controller |
| `kubectl-argo-rollouts` plugin | ≥ 1.6 | CLI for promotions |
| Docker | any | Building images |

---

## Step-by-Step Setup

### Step 1 — Fork & Clone This Repo

```bash
# Fork on GitHub, then:
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO/fastapi-blue-green
```

Update the `repoURL` in `argocd/application.yaml`:
```yaml
source:
  repoURL: https://github.com/YOUR_USERNAME/YOUR_REPO.git
```

---

### Step 2 — Build & Push the Docker Images

Build two image tags — one for each version you will deploy:

```bash
cd app/

# v1 — the initial stable (blue) version
docker build -t YOUR_DOCKERHUB_USERNAME/fastapi-blue-green:v1.0.0 .
docker push YOUR_DOCKERHUB_USERNAME/fastapi-blue-green:v1.0.0

# v2 — the new candidate (green) version
# (In a real workflow, this is built from updated code on a new commit)
docker build -t YOUR_DOCKERHUB_USERNAME/fastapi-blue-green:v2.0.0 .
docker push YOUR_DOCKERHUB_USERNAME/fastapi-blue-green:v2.0.0
```

Update `helm/fastapi-app/values.yaml` with your repository:
```yaml
image:
  repository: YOUR_DOCKERHUB_USERNAME/fastapi-blue-green
```

Commit and push:
```bash
git add helm/fastapi-app/values.yaml argocd/application.yaml
git commit -m "chore: set image repo and argocd repoURL"
git push
```

---

### Step 3 — Install Argo CD (if not already installed)

```bash
kubectl create namespace argocd
kubectl apply -n argocd \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for pods to be ready
kubectl wait --for=condition=Ready pods --all -n argocd --timeout=120s

# Get initial admin password
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d && echo
```

---

### Step 4 — Install Argo Rollouts

```bash
kubectl create namespace argo-rollouts
kubectl apply -n argo-rollouts \
  -f https://github.com/argoproj/argo-rollouts/releases/latest/download/install.yaml

# Install the kubectl plugin (macOS)
brew install argoproj/tap/kubectl-argo-rollouts

# Verify
kubectl argo rollouts version
```

---

### Step 5 — Deploy the Argo CD Application

```bash
# Apply the AppProject (optional but recommended)
kubectl apply -f argocd/appproject.yaml

# Apply the Application — Argo CD will immediately sync the Helm chart
kubectl apply -f argocd/application.yaml
```

Watch the sync:
```bash
kubectl -n argocd get application fastapi-blue-green -w
# Or open the Argo CD UI: kubectl port-forward svc/argocd-server -n argocd 8080:443
```

After sync, verify pods are running:
```bash
kubectl -n fastapi-demo get pods
kubectl -n fastapi-demo get rollout
kubectl -n fastapi-demo get svc
```

Test the active (blue) endpoint:
```bash
kubectl -n fastapi-demo port-forward svc/fastapi-active 8080:80
# In another terminal:
curl http://localhost:8080/
# {"message":"...", "version":"v1.0.0", "color":"blue"}
```

---

## Step-by-Step: Performing a Blue-Green Deployment

### Step 6 — Trigger the Green Deployment (Git Push)

Edit `helm/fastapi-app/values.yaml` (or update `argocd/application.yaml` to add
`values-v2.yaml`):

```yaml
# helm/fastapi-app/values.yaml  — change these two fields:
image:
  tag: "v2.0.0"

app:
  color: "green"
  version: "v2.0.0"
```

Or, to keep v1/v2 values separate, update the Argo CD application to reference `values-v2.yaml`:
```yaml
# argocd/application.yaml
helm:
  valueFiles:
    - values.yaml
    - values-v2.yaml    # <-- add this line
```

Commit and push:
```bash
git add helm/fastapi-app/values.yaml   # or argocd/application.yaml
git commit -m "feat: deploy v2.0.0 green candidate"
git push
```

**What happens next (automatically):**
1. Argo CD detects the Git change and syncs the Helm chart.
2. Argo Rollouts sees the new pod template and creates a **new ReplicaSet** (green, v2.0.0).
3. Green pods come up and pass readiness probes.
4. `fastapi-preview` service is updated to point to the green ReplicaSet.
5. `fastapi-active` service **still** points to the blue (v1.0.0) ReplicaSet.
6. The Rollout enters **Paused** state, waiting for manual promotion.

Verify the state:
```bash
kubectl argo rollouts get rollout release-fastapi-app -n fastapi-demo --watch
```

You should see output like:
```
Name:            release-fastapi-app
Namespace:       fastapi-demo
Status:          ॥ Paused
Strategy:        BlueGreen
  Active Service: fastapi-active   (pointing to blue v1.0.0)
  Preview Service: fastapi-preview (pointing to green v2.0.0)
Images:
  your-repo/fastapi-blue-green:v1.0.0 (stable)
  your-repo/fastapi-blue-green:v2.0.0 (canary)
```

---

### Step 7 — Test the Green (Preview) Version

While blue is still serving production traffic, test green via the preview service:

```bash
# Terminal 1: active (blue) — still serving production
kubectl -n fastapi-demo port-forward svc/fastapi-active 8080:80 &
curl http://localhost:8080/info
# {"version":"v1.0.0","color":"blue",...}

# Terminal 2: preview (green) — new candidate for testing
kubectl -n fastapi-demo port-forward svc/fastapi-preview 8081:80 &
curl http://localhost:8081/info
# {"version":"v2.0.0","color":"green",...}
```

Run any smoke tests, integration tests, or manual verification against port 8081
**without affecting any production traffic**.

---

### Step 8 — Promote Green to Active (Blue → Green Cutover)

Once satisfied with the green version, promote it:

```bash
kubectl argo rollouts promote release-fastapi-app -n fastapi-demo
```

**What happens:**
1. `fastapi-active` service selector is updated to point to the green ReplicaSet.
2. Green is now serving 100% of production traffic.
3. The old blue ReplicaSet is kept scaled-down for `scaleDownDelaySeconds` (30s by default).
4. After the delay, the blue ReplicaSet is scaled to 0 (but retained for rollback).

Verify:
```bash
curl http://localhost:8080/info   # port-forward still on fastapi-active
# {"version":"v2.0.0","color":"green",...}   ← green is now live!
```

---

### Step 9 — Rollback (if needed)

If you discover a problem **before** promotion:
```bash
# Abort the rollout — active stays on blue, green is torn down
kubectl argo rollouts abort release-fastapi-app -n fastapi-demo
```

If you discover a problem **after** promotion:
```bash
# Undo to the previous ReplicaSet (blue is still scaled-down, not deleted)
kubectl argo rollouts undo release-fastapi-app -n fastapi-demo
```

Or roll back via Git (the GitOps way — preferred):
```bash
# Revert the values change in Git
git revert HEAD
git push
# Argo CD syncs, Argo Rollouts performs a new blue-green cycle back to v1
```

---

## State Machine Summary

```
Git push (new image tag)
        │
        ▼
[Argo CD syncs Helm chart]
        │
        ▼
[Argo Rollouts creates GREEN ReplicaSet]
        │
        ▼
[GREEN pods pass readiness] ──── FAIL ──→ Rollout stuck in Degraded
        │                                  kubectl argo rollouts abort
        ▼ PASS
[fastapi-preview → GREEN]
[fastapi-active  → BLUE  ]  ← production still on BLUE
        │
        ▼
  [Paused — awaiting promotion]
        │
   promote / abort
        │
  ┌─────┴─────────────────────┐
  ▼ promote                   ▼ abort
[fastapi-active → GREEN]   [GREEN torn down]
[BLUE scaled down]         [BLUE stays active]
        │
        ▼
[scaleDownDelay expires]
[BLUE ReplicaSet → 0 replicas]
     (retained for fast rollback)
```

---

## Useful Commands Reference

```bash
# Watch rollout status
kubectl argo rollouts get rollout release-fastapi-app -n fastapi-demo --watch

# List all rollouts
kubectl argo rollouts list rollouts -n fastapi-demo

# Promote (green → active)
kubectl argo rollouts promote release-fastapi-app -n fastapi-demo

# Abort (scrap green, keep blue)
kubectl argo rollouts abort release-fastapi-app -n fastapi-demo

# Undo (revert to previous version after promotion)
kubectl argo rollouts undo release-fastapi-app -n fastapi-demo

# Pause a running rollout
kubectl argo rollouts pause release-fastapi-app -n fastapi-demo

# Resume a paused rollout
kubectl argo rollouts resume release-fastapi-app -n fastapi-demo

# Open Argo Rollouts dashboard
kubectl argo rollouts dashboard
```

---

## Argo CD Sync Notes

- Argo CD is configured with `automated.selfHeal: true` — manual cluster changes
  will be reverted. Always make changes through Git.
- Argo CD does **not** manage the promotion step — that is Argo Rollouts' job.
  Argo CD's sync status will show `Healthy` even while the Rollout is Paused.
- To trigger a manual sync: `argocd app sync fastapi-blue-green`

---

## Customisation

| What to change | Where |
|---|---|
| Image tag for new release | `helm/fastapi-app/values.yaml` → `image.tag` |
| Auto-promote without approval | `values.yaml` → `rollout.autoPromotionEnabled: true` |
| Auto-promote delay | `values.yaml` → `rollout.autoPromotionSeconds` |
| Number of replicas | `values.yaml` → `replicaCount` |
| Enable Ingress | `values.yaml` → `ingress.enabled: true` + set `ingress.host` |
| Add analysis (automated verification) | Add `AnalysisTemplate` + `prePromotionAnalysis` to `rollout.yaml` |
