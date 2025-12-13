#!/bin/bash
# TBench Runner Deployment Script
# Usage: ./deploy.sh [api|worker|frontend|all]

set -e

# Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
PROJECT_NAME="${PROJECT_NAME:-tbench-runner}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# ECR URLs
ECR_API="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${PROJECT_NAME}-api"
ECR_WORKER="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${PROJECT_NAME}-worker"
ECR_FRONTEND="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${PROJECT_NAME}-frontend"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# Login to ECR
ecr_login() {
    log "Logging into ECR..."
    aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com
}

# Build and push API
deploy_api() {
    log "Building API image..."
    docker build -t ${PROJECT_NAME}-api ./backend
    
    log "Tagging API image..."
    docker tag ${PROJECT_NAME}-api:latest ${ECR_API}:latest
    
    log "Pushing API image to ECR..."
    docker push ${ECR_API}:latest
    
    log "Updating API ECS service..."
    aws ecs update-service --cluster ${PROJECT_NAME}-cluster --service ${PROJECT_NAME}-api --force-new-deployment --region $AWS_REGION
    
    log "API deployed successfully!"
}

# Build and push Worker
deploy_worker() {
    log "Building Worker image..."
    docker build -t ${PROJECT_NAME}-worker -f ./backend/Dockerfile.worker ./backend
    
    log "Tagging Worker image..."
    docker tag ${PROJECT_NAME}-worker:latest ${ECR_WORKER}:latest
    
    log "Pushing Worker image to ECR..."
    docker push ${ECR_WORKER}:latest
    
    log "Updating Worker ECS service..."
    aws ecs update-service --cluster ${PROJECT_NAME}-cluster --service ${PROJECT_NAME}-worker --force-new-deployment --region $AWS_REGION
    
    log "Worker deployed successfully!"
}

# Build and push Frontend
deploy_frontend() {
    log "Building Frontend image..."
    
    # Get ALB URL for API
    ALB_DNS=$(aws elbv2 describe-load-balancers --names ${PROJECT_NAME}-alb --query 'LoadBalancers[0].DNSName' --output text --region $AWS_REGION 2>/dev/null || echo "localhost:8000")
    
    docker build -t ${PROJECT_NAME}-frontend --build-arg NEXT_PUBLIC_API_URL=http://${ALB_DNS} ./frontend
    
    log "Tagging Frontend image..."
    docker tag ${PROJECT_NAME}-frontend:latest ${ECR_FRONTEND}:latest
    
    log "Pushing Frontend image to ECR..."
    docker push ${ECR_FRONTEND}:latest
    
    log "Frontend deployed successfully!"
    log "Note: For production, consider deploying frontend to S3/CloudFront or Vercel"
}

# Main
case "${1:-all}" in
    api)
        ecr_login
        deploy_api
        ;;
    worker)
        ecr_login
        deploy_worker
        ;;
    frontend)
        ecr_login
        deploy_frontend
        ;;
    all)
        ecr_login
        deploy_api
        deploy_worker
        deploy_frontend
        ;;
    *)
        echo "Usage: $0 [api|worker|frontend|all]"
        exit 1
        ;;
esac

log "Deployment complete!"

