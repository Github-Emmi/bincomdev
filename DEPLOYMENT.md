# BincomDevCenter: Deployment Runbook

**Version**: 1.0 | **Last Updated**: April 3, 2026 | **Audience**: DevOps/Engineers

---

## Table of Contents
1. [Quick Start](#quick-start)
2. [Deployment Methods](#deployment-methods)
3. [Pre-Deployment Checklist](#pre-deployment-checklist)
4. [Render Manual Deployment](#render-manual-deployment)
5. [Automated CI/CD Deployment](#automated-cicd-deployment)
6. [Post-Deployment Verification](#post-deployment-verification)
7. [Rollback Procedures](#rollback-procedures)
8. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Local Development Setup
```bash
# Clone repository
git clone <repo-url>
cd BincomDevCenter

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Initialize database
python manage.py migrate
python manage.py seed_demo_data

# Run development server
python manage.py runserver
# Visit http://127.0.0.1:8000/
```

### Install Development Tools
```bash
# Add testing & linting tools
pip install -r requirements-dev.txt

# Run tests
pytest elections/tests.py -v --cov=elections

# Run linting
ruff check elections config
black --check elections config
```

---

## Deployment Methods

### Option 1: Automated CI/CD (Recommended)
- **Trigger**: Push to `main` branch
- **Process**: GitHub Actions → Render auto-deploy
- **Tests**: Automatic (failure blocks deploy)
- **Time**: ~2-5 minutes

### Option 2: Manual Render Deployment
- **Trigger**: Manual via Render dashboard
- **Process**: Connect to repository, trigger redeploy
- **Tests**: Manual pre-deployment required
- **Time**: ~3-5 minutes

### Option 3: Roll Back
- **Trigger**: Manual via Render dashboard
- **Process**: Redeploy previous commit
- **Time**: ~2-3 minutes

---

## Pre-Deployment Checklist

Before deploying to production:

- [ ] **Tests pass locally**
  ```bash
  python manage.py test elections.tests --no-input
  # Expect: "Ran X tests in Y.XXXs ... OK"
  ```

- [ ] **No linting errors**
  ```bash
  ruff check elections config --select=E,F,W
  # Expect: No output (clean)
  ```

- [ ] **Static files collected**
  ```bash
  python manage.py collectstatic --noinput
  # Expect: "X static files copied to ..."
  ```

- [ ] **Django system check passes**
  ```bash
  python manage.py check
  # Expect: "System check identified no issues"
  ```

- [ ] **Git branch is clean**
  ```bash
  git status
  # Expect: "On branch main" and "nothing to commit"
  ```

- [ ] **Commit message is clear**
  ```bash
  git log -1 --oneline
  # Example: "feat: add comprehensive test suite and CI/CD"
  ```

---

## Render Manual Deployment

### Step 1: Access Render Dashboard
1. Go to https://dashboard.render.com
2. Login with your Render credentials
3. Select project: **bincom-election-explorer**

### Step 2: Trigger Redeployment
1. Click **"Manual Deploy"** button (top-right)
2. Select branch: **main**
3. Click **"Deploy"**
4. Wait for build to complete (2-5 minutes)

### Step 3: Monitor Build Progress
- **Building**: Watch log output in real-time
- **Expected steps**:
  ```
  1. Installing dependencies (pip install -r requirements.txt)
  2. Running migrations (python manage.py migrate)
  3. Seeding data (python manage.py seed_demo_data)
  4. Collecting static files (python manage.py collectstatic)
  5. Starting gunicorn (gunicorn config.wsgi:application)
  ```

### Step 4: Verify Deployment
After deployment shows **"Live"** status:
```bash
# Test the app
curl https://bincom-election-explorer.onrender.com/
# Expected: HTML response with "Bincom Election Result Explorer"

# Check dashboard
open https://bincom-election-explorer.onrender.com/
```

---

## Automated CI/CD Deployment

### How It Works
1. **Commit & Push** code to `main` branch
2. **GitHub Actions** runs:
   - Test suite (`pytest`)
   - Linting (`ruff`, `black`)
   - Coverage report
3. **If tests pass**:
   - Render detects new commit
   - Automatically redeployed
4. **Monitor** at Render dashboard

### Triggering CI/CD
```bash
# Make changes
nano elections/views.py

# Commit
git add elections/views.py
git commit -m "fix: improve error handling in views"

# Push to main (triggers CI/CD)
git push origin main

# Watch GitHub Actions
open https://github.com/your-repo/actions

# Watch Render deployment
open https://dashboard.render.com
```

### CI/CD Workflows

**Test & Lint Workflow** (`.github/workflows/test-and-lint.yml`):
- Runs on: Every push to `main` or `develop`, every PR
- Steps:
  - Setup Python 3.10
  - Install dev dependencies
  - Lint with ruff
  - Format check with black
  - Run pytest with coverage
  - Upload coverage report

**Deploy Workflow** (`.github/workflows/deploy-render.yml`):
- Runs on: Successful push to `main` AFTER tests pass
- Steps:
  - Run full test suite
  - If tests pass, trigger Render deployment
  - Post deployment status

---

## Post-Deployment Verification

### Smoke Tests (5-10 minutes)

#### 1. Dashboard Loads
```bash
curl -I https://bincom-election-explorer.onrender.com/
# Expected: HTTP/2 200
# Expected: Content-Type: text/html

# Or visit in browser
open https://bincom-election-explorer.onrender.com/
```

#### 2. Dashboard Shows Content
```bash
curl https://bincom-election-explorer.onrender.com/ | grep -c "Bincom Election"
# Expected: X > 0 (appears multiple times)
```

#### 3. Polling Unit Results Page Works
```bash
curl https://bincom-election-explorer.onrender.com/polling-units/
# Expected: HTTP 200, contains form elements
```

#### 4. LGA Results Page Works
```bash
curl https://bincom-election-explorer.onrender.com/lga-results/
# Expected: HTTP 200, contains LGA selector
```

#### 5. New Submission Form Loads
```bash
curl https://bincom-election-explorer.onrender.com/polling-units/new/
# Expected: HTTP 200, contains form fields
```

#### 6. Static Files Serve
```bash
curl https://bincom-election-explorer.onrender.com/static/css/app.css
# Expected: HTTP 200, contains CSS content
```

### Detailed Verification

#### Check Logs
1. Go to Render dashboard
2. Click project → **"Logs"** tab
3. Look for:
   - ✅ `INFO: Application startup complete`
   - ❌ **No** `ERROR` or `CRITICAL` messages
   - ⚠️ Any `WARNING` messages should be Django-standard (e.g., deprecation)

#### Verify Database
```bash
# SSH into Render container (if available)
# Check database initialized:
sqlite3 db.sqlite3 "SELECT COUNT(*) FROM lga;"
# Expected: "25" rows
```

#### Check Performance
- **Response time**: Should be < 500ms for homepage
- **CSS loads**: Visual check in browser
- **Forms functional**: Can expand selectors, select options

---

## Rollback Procedures

### Scenario: Deployment breaks the app

#### Option 1: Rollback via Render Dashboard (Fastest)
1. Go to https://dashboard.render.com → bincom-election-explorer
2. Click **"Deploys"** tab
3. Find previous working deployment
4. Click **"Redeploy"** button
5. Wait for deployment to complete
6. Verify with smoke tests

#### Option 2: Rollback via Git + GitHub Actions
```bash
# Identify last good commit
git log --oneline | head -5

# Revert to previous version
git revert HEAD
# OR
git reset --hard <good-commit-sha>

# Push to main (triggers CI/CD)
git push origin main --force-with-lease

# Watch deployment complete
open https://dashboard.render.com
```

#### Option 3: Emergency Fix (Hotfix Branch)
```bash
# Create hotfix branch
git checkout -b hotfix/emergency-fix

# Make fix
nano elections/views.py

# Test locally
python manage.py test elections.tests --no-input

# Commit
git add .
git commit -m "fix: emergency fix for deploy issue"

# Push to main
git push origin hotfix/emergency-fix
git checkout main
git pull origin hotfix/emergency-fix
git push origin main
```

---

## Troubleshooting

### Symptom 1: "502 Bad Gateway"

**Cause 1**: App crashed during startup
**Fix**:
```bash
# Check Render logs
# Look for: ERROR in DATABASE INITIALIZATION, MIGRATION FAILURE, etc.
# Common: Missing migration, database corruption

# Local reproduction
python manage.py migrate
python manage.py check
```

**Cause 2**: Gunicorn workers misconfigured
**Fix**:
```yaml
# In render.yaml, adjust:
startCommand: gunicorn config.wsgi:application --workers 2 --timeout 30
```

### Symptom 2: "500 Internal Server Error"

**Cause 1**: Template rendering issue
**Fix**:
- Check Render logs for template error
- Test locally: `python manage.py runserver`
- Look for missing template tags or variables

**Cause 2**: Import or syntax error
**Fix**:
```bash
# Local test
python manage.py check
python -m py_compile elections/*.py
```

### Symptom 3: Static Files Not Loading (CSS/JS missing)

**Cause**: `collectstatic` didn't run or WhiteNoise not configured
**Fix**:
```bash
# Verify in render.yaml buildCommand:
# Must include: python manage.py collectstatic --noinput

# Test locally
python manage.py collectstatic --noinput
ls -la staticfiles/
# Should contain: css/, js/, admin/, etc.
```

### Symptom 4: Forms Not Submitting

**Cause 1**: CSRF token missing or invalid
**Fix**:
- Check `CSRF_TRUSTED_ORIGINS` in render.yaml
- Verify form includes `{% csrf_token %}`
- Test locally with correct ALLOWED_HOSTS

**Cause 2**: Database write failed
**Fix**:
```bash
python manage.py dbshell
# Check if elections_polling_unit table exists
.tables
.schema elections_polling_unit
```

### Symptom 5: Tests Fail in CI/CD but Pass Locally

**Cause**: Environment variable differences
**Fix**:
```bash
# ✅ CI test environment
DEBUG=False python manage.py test elections.tests --no-input

# Compare with latest CI logs
open https://github.com/your-repo/actions
```

### Getting Help

1. **Check Render Logs**: Dashboard → Logs tab (most useful)
2. **Check GitHub Actions**: Actions tab → Test & Lint workflow
3. **Manual Test**: SSH into Render console (if available)
4. **Rollback**: Use procedures in "Rollback Procedures" section
5. **Contact**: Render support at support@render.com

---

## Environment Variables

### Required for Production (Render)
```
DEBUG=False
SECRET_KEY=<generated by Render>
ALLOWED_HOSTS=.onrender.com
CSRF_TRUSTED_ORIGINS=https://bincom-election-explorer.onrender.com
```

### Optional
```
SENTRY_DSN=<for error tracking>
LOG_LEVEL=WARNING
```

### Development (local .env)
```
DEBUG=True
SECRET_KEY=dev-key-change-in-production
ALLOWED_HOSTS=127.0.0.1,localhost
```

---

## Monitoring & Alerts

### Recommended Additions (Future)
- [ ] **Error logging**: Sentry.io for crash tracking
- [ ] **Performance monitoring**: New Relic or similar
- [ ] **Uptime checks**: Pingdom or Render health checks
- [ ] **Log aggregation**: CloudWatch or LogRocket

---

## References

- [Render Django Guide](https://render.com/docs/deploy-django)
- [Django Deployment Checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [WhiteNoise Documentation](http://whitenoise.evans.io/)

---

**Last Reviewed**: April 3, 2026  
**Next Review**: After first production deployment
