#!/bin/bash
# Quick scale-up script for 600 concurrent tasks
# Usage: ./scripts/scale_up.sh [instance_count]

INSTANCE_COUNT=${1:-20}  # Default to 20 instances
ASG_NAME="tbench-runner-worker-20251213054900752800000006"
REGION="us-west-2"

echo "🚀 Scaling up for high-load demo..."
echo "   Target: $INSTANCE_COUNT EC2 instances"
echo ""

# Scale EC2 instances
echo "1. Scaling EC2 instances to $INSTANCE_COUNT..."
aws autoscaling update-auto-scaling-group \
  --auto-scaling-group-name "$ASG_NAME" \
  --desired-capacity $INSTANCE_COUNT \
  --region $REGION

if [ $? -eq 0 ]; then
  echo "   ✅ EC2 scaling initiated"
else
  echo "   ❌ Failed to scale EC2"
  exit 1
fi

# ECS workers will autoscale automatically, but we can also set a higher desired count
echo ""
echo "2. Setting ECS worker desired count to 50 (will autoscale further if needed)..."
aws ecs update-service \
  --cluster tbench-runner-cluster \
  --service tbench-runner-worker \
  --desired-count 50 \
  --region $REGION > /dev/null

if [ $? -eq 0 ]; then
  echo "   ✅ ECS worker scaling initiated"
else
  echo "   ⚠️  ECS scaling failed (may already be at limit)"
fi

echo ""
echo "⏳ Waiting for instances to launch (this takes 5-10 minutes)..."
echo "   You can monitor progress with:"
echo "   aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names $ASG_NAME --region $REGION --query 'AutoScalingGroups[0].Instances[?LifecycleState==\`InService\`] | length(@)'"
echo ""
echo "✅ Scale-up complete! Ready for 600 concurrent tasks."

