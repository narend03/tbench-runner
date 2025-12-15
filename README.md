# TBench Runner

A production-grade, scalable platform for running Terminal-Bench (Harbor) tasks at scale. Upload a task, run multiple agent episodes, and view detailed logs and test results.

## 🎯 Features

- **Task Upload**: Upload Terminal-Bench 2.0 tasks as ZIP files
- **Multi-Run Execution**: Run 10+ episodes per task with independent execution
- **Multiple Agents**: Support for `terminus-2`, `oracle`, and custom agents
- **Multiple Models**: Integration with OpenRouter for GPT-5.2, GPT-4o, Claude, and more
- **Real-time Monitoring**: View execution logs, test results, and statistics
- **Auto-scaling**: Queue-based auto-scaling for handling 750+ concurrent runs
- **Production-ready**: Deployed on AWS with ECS, RDS, Redis, S3, and more

## 🏗️ Architecture

```
┌─────────────┐
│   Frontend   │ (Next.js)
│  (Port 3000) │
└──────┬───────┘
       │
       ▼
┌─────────────┐
│   API       │ (FastAPI)
│  (Port 8000)│
└──────┬───────┘
       │
       ├──► PostgreSQL (RDS) ──► Tasks, Runs, Results
       │
       ├──► Redis (ElastiCache) ──► Celery Queue
       │
       └──► S3 ──► Task ZIP files
       
       │
       ▼
┌─────────────┐
│   Celery    │ (Background Workers)
│   Workers   │
└──────┬───────┘
       │
       ▼
┌─────────────┐
│   Harbor    │ (Terminal-Bench Execution)
│   + LLM     │
└─────────────┘
```

### Tech Stack

**Backend:**
- FastAPI (Python) - REST API
- Celery - Async task queue
- PostgreSQL - Database
- Redis - Message broker
- Harbor - Terminal-Bench execution harness
- LiteLLM - LLM interface

**Frontend:**
- Next.js (TypeScript) - React framework
- Tailwind CSS - Styling

**Infrastructure:**
- AWS ECS - Container orchestration
- AWS EC2 - Worker instances (Docker-in-Docker)
- AWS RDS - PostgreSQL database
- AWS ElastiCache - Redis
- AWS S3 - File storage
- AWS ALB - Load balancer
- Terraform - Infrastructure as code

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- PostgreSQL (or use Docker Compose)
- Redis (or use Docker Compose)
- OpenRouter API key (for LLM agents)

### Local Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/narend03/tbench-runner.git
   cd tbench-runner
   ```

2. **Set up backend:**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure environment:**
   ```bash
   cp env.example .env
   # Edit .env with your settings
   ```

4. **Set up frontend:**
   ```bash
   cd ../frontend
   npm install
   ```

5. **Start services with Docker Compose:**
   ```bash
   cd ..
   docker-compose up -d
   ```

   This starts:
   - PostgreSQL on port 5432
   - Redis on port 6379
   - Backend API on port 8000
   - Frontend on port 3000

6. **Start Celery worker (in separate terminal):**
   ```bash
   cd backend
   source venv/bin/activate
   celery -A app.celery_app worker --loglevel=info
   ```

7. **Access the application:**
   - Frontend: http://localhost:3000
   - API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

## 📦 Task Format

Tasks must be Terminal-Bench 2.0 compatible ZIP files containing:

```
task-name/
├── task.toml          # Task configuration
├── instruction.md     # Task instructions
├── environment/       # Docker environment
│   └── Dockerfile
├── tests/            # Test files
│   ├── test.sh
│   └── test_outputs.py
└── solution/         # (Optional) Solution script
    └── solve.sh
```

Example tasks are available in `sample-tasks/`:
- `break-filter-js-from-html.zip`
- `chess-best-move.zip`
- `code-from-image.zip`

## 🔌 API Documentation

### Endpoints

#### Task Management

- `POST /api/tasks` - Upload a new task
  - Parameters: `file` (ZIP), `name`, `model`, `agent`, `num_runs`
  - Returns: Task object with ID

- `GET /api/tasks` - List all tasks
  - Query params: `skip`, `limit`, `status`
  - Returns: List of tasks

- `GET /api/tasks/{task_id}` - Get task details
  - Returns: Task with all runs and statistics

- `POST /api/tasks/{task_id}/execute-async` - Execute task (10 runs)
  - Parameters: `openrouter_api_key`
  - Returns: Execution status

#### Models & Agents

- `GET /api/models` - List available models
- `GET /api/agents` - List available agents

#### Run Details

- `GET /api/tasks/{task_id}/runs/{run_id}/logs` - Get run execution logs

### Interactive API Docs

Visit http://localhost:8000/docs for Swagger UI with full API documentation.

## 🌐 AWS Deployment

### Prerequisites

- AWS account with appropriate permissions
- Terraform installed
- AWS CLI configured
- Docker for building images

### Deployment Steps

1. **Configure Terraform:**
   ```bash
   cd infrastructure/terraform
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with your values
   ```

2. **Initialize Terraform:**
   ```bash
   terraform init
   ```

3. **Review plan:**
   ```bash
   terraform plan
   ```

4. **Deploy infrastructure:**
   ```bash
   terraform apply
   ```

5. **Build and push Docker images:**
   ```bash
   cd ../../scripts
   ./deploy.sh
   ```

### Infrastructure Components

The Terraform configuration creates:

- **VPC** with public/private subnets
- **RDS PostgreSQL** database
- **ElastiCache Redis** cluster
- **S3 bucket** for file storage
- **ECS Cluster** with:
  - API service (Fargate)
  - Frontend service (Fargate)
  - Worker service (EC2)
- **Application Load Balancer**
- **Auto Scaling Groups** for EC2 workers
- **CloudWatch** for monitoring
- **Secrets Manager** for API keys

### Scaling Configuration

- **EC2 Workers**: Auto-scales from 1-200 instances based on queue depth
- **ECS Workers**: Auto-scales based on CPU and queue depth
- **Target**: Handle 750 concurrent runs (15 users × 5 tasks × 10 runs)

See `SCALE_750_RUNS.md` for detailed scaling information.

## ⚙️ Configuration

### Environment Variables

**Backend (`backend/.env`):**
```bash
# Database
DATABASE_URL=postgresql://user:password@host:5432/dbname

# Redis
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Storage
STORAGE_BACKEND=local  # or "s3" for production
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET_NAME=...

# OpenRouter
OPENROUTER_API_KEY=sk-or-v1-...

# CORS
CORS_ORIGINS=http://localhost:3000
```

**Frontend (`frontend/.env.local`):**
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Terraform Variables

See `infrastructure/terraform/variables.tf` for all available variables.

Key variables in `terraform.tfvars`:
- `aws_region` - AWS region
- `project_name` - Project name
- `db_password` - Database password
- `openrouter_api_key` - OpenRouter API key
- `worker_ec2_max_count` - Max EC2 instances (default: 200)

## 📊 Usage Examples

### Upload and Execute a Task

1. **Via Frontend:**
   - Go to http://localhost:3000
   - Enter your OpenRouter API key
   - Upload a task ZIP file
   - Select model and agent
   - Click "Execute"
   - View results and logs

2. **Via API:**
   ```bash
   # Upload task
   curl -X POST "http://localhost:8000/api/tasks?name=my-task&model=openrouter/openai/gpt-5.2&agent=terminus-2&num_runs=10" \
     -F "file=@sample-tasks/break-filter-js-from-html.zip"
   
   # Execute (replace {task_id} and {api_key})
   curl -X POST "http://localhost:8000/api/tasks/{task_id}/execute-async?openrouter_api_key={api_key}"
   
   # Check status
   curl "http://localhost:8000/api/tasks/{task_id}"
   ```

### Load Testing

Scripts are available in `scripts/`:

- `test_25_tabs.py` - Simulates 25 concurrent users (250 runs)
- `test_oracle_750.py` - Tests 750 oracle runs (no LLM costs)
- `load_test.py` - General load testing script

## 🧪 Testing

### Local Testing

1. **Start services:**
   ```bash
   docker-compose up -d
   ```

2. **Run a test task:**
   ```bash
   python scripts/load_test.py \
     --url http://localhost:8000 \
     --api-key YOUR_API_KEY \
     --task-zip sample-tasks/break-filter-js-from-html.zip
   ```

### Oracle Agent (Free Testing)

The oracle agent uses hardcoded solutions and doesn't require LLM API calls:

```bash
python scripts/test_oracle_750.py
```

## 📈 Monitoring

### CloudWatch Metrics

- **Queue Depth**: Custom metric for Celery queue depth
- **CPU Utilization**: ECS service CPU usage
- **Task Execution**: Run duration and success rates

### Logs

- **API Logs**: CloudWatch Logs for API service
- **Worker Logs**: CloudWatch Logs for worker service
- **Application Logs**: Stored in database and accessible via API

## 🔒 Security

- **API Keys**: Stored in AWS Secrets Manager (production)
- **Database**: RDS with encrypted storage
- **Network**: VPC with security groups
- **HTTPS**: ALB with SSL/TLS termination
- **CORS**: Configurable origins

## 🐛 Troubleshooting

### Common Issues

1. **Workers not processing tasks:**
   - Check Celery worker is running: `celery -A app.celery_app inspect active`
   - Check Redis connection
   - Check worker logs

2. **Tasks timing out:**
   - Default timeout is 1200 seconds (20 minutes)
   - Check Harbor execution logs
   - Verify LLM API key is valid

3. **Docker-in-Docker issues:**
   - Ensure Docker socket is mounted: `/var/run/docker.sock`
   - Check EC2 instances have Docker installed

4. **Database connection errors:**
   - Verify DATABASE_URL is correct
   - Check RDS security groups allow connections
   - Verify database is running

## 📚 Additional Documentation

### Core Documentation
- `SCALE_750_RUNS.md` - Scaling to 750 concurrent runs
- `TIMEOUT_ANALYSIS.md` - Timeout configuration and troubleshooting
- `COMMIT_GUIDE.md` - Development guidelines

### System Design & Architecture
- [`docs/SYSTEM_ARCHITECTURE_PRESENTATION.md`](docs/SYSTEM_ARCHITECTURE_PRESENTATION.md) - Complete system architecture with all services, tradeoffs, and design decisions
- [`docs/PRESENTATION_GUIDE.md`](docs/PRESENTATION_GUIDE.md) - How to present the system, key talking points, and Q&A answers
- [`docs/QUICK_REFERENCE.md`](docs/QUICK_REFERENCE.md) - Quick reference card with all services and key decisions
- [`docs/AWS_OPENROUTER_WALKTHROUGH.md`](docs/AWS_OPENROUTER_WALKTHROUGH.md) - Detailed walkthrough of AWS services and OpenRouter setup
- [`docs/AWS_SERVICE_COSTS.md`](docs/AWS_SERVICE_COSTS.md) - Detailed cost breakdown for all AWS services
- [`docs/SCALING_BEST_PRACTICES.md`](docs/SCALING_BEST_PRACTICES.md) - Scaling strategies and best practices

### Infrastructure
- `infrastructure/terraform/` - Infrastructure as code (Terraform)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📄 License

[Add your license here - e.g., MIT, Apache 2.0]

## 🙏 Acknowledgments

- [Terminal-Bench](https://github.com/laude-institute/terminal-bench-2) - Benchmark dataset
- [Harbor](https://github.com/laude-institute/harbor) - Execution harness
- [OpenRouter](https://openrouter.ai/) - LLM API gateway

## 📧 Contact

For questions or issues, please open an issue on GitHub.

---

**Built with ❤️ for scalable Terminal-Bench execution**
