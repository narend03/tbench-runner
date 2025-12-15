# Scaling to 750 Runs in <1 Hour

## Summary
- **Target**: 750 runs in <1 hour
- **Solution**: 200 EC2 instances
- **Time**: ~56 minutes (meets <1 hour requirement)
- **Cost**: ~$248 ($15 EC2 + $233 LLM)

## Configuration Changes Made

### 1. Terraform Variables (`terraform.tfvars`)
- Updated `worker_ec2_max_count = 200` (was 25)
- This allows up to 200 EC2 instances

### 2. ECS Autoscaling (`ecs.tf`)
- Updated `max_capacity = 200` (was 100)
- This allows up to 200 ECS worker tasks

## Setup Steps

### Step 1: Request AWS Quota Increase
1. Go to AWS Console → **Service Quotas**
2. Search: "EC2 instances" or "Running On-Demand instances"
3. Request increase to **200+ instances**
4. Usually approved in minutes to hours

### Step 2: Apply Terraform Changes
```bash
cd infrastructure/terraform
terraform plan  # Review changes
terraform apply  # Apply changes
```

### Step 3: Scale Up (Automatic or Manual)

**Automatic (Recommended):**
- ECS will auto-scale based on queue depth
- When 750 runs are queued, it will scale to 200 workers
- Takes ~5-10 minutes to scale up

**Manual (If needed):**
```bash
# Scale EC2 autoscaling group
aws autoscaling set-desired-capacity \
  --auto-scaling-group-name tbench-runner-worker-* \
  --desired-capacity 200

# Scale ECS service
aws ecs update-service \
  --cluster tbench-runner \
  --service tbench-runner-worker \
  --desired-count 200
```

## Execution Timeline

With 200 instances:
- **Batch 1**: Runs 1-200 (0-15 min)
- **Batch 2**: Runs 201-400 (15-30 min)
- **Batch 3**: Runs 401-600 (30-45 min)
- **Batch 4**: Runs 601-750 (45-56 min)
- **Total**: ~56 minutes ✅

## Cost Breakdown

- **EC2**: 200 instances × 0.9 hours × $0.0832/hour = **$15.60**
- **LLM**: 750 runs × $0.31/run = **$232.50**
- **Total**: **$248.10**

## Notes

- LLM cost ($233) dominates - EC2 cost ($15) is small
- If runs are faster (10 min average): Time = ~37.5 minutes (even better!)
- After test completes, scale down to save costs:
  ```bash
  aws autoscaling set-desired-capacity \
    --auto-scaling-group-name tbench-runner-worker-* \
    --desired-capacity 1
  ```

## Verification

After scaling, verify:
1. EC2 instances: `aws ec2 describe-instances --filters "Name=tag:Name,Values=tbench-runner-worker"`
2. ECS tasks: `aws ecs list-tasks --cluster tbench-runner --service-name tbench-runner-worker`
3. Queue depth: Check Redis/Celery queue size
