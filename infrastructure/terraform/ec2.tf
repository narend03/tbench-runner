# EC2 Capacity Provider for ECS Workers
# This enables Docker-in-Docker for Harbor execution

# Get latest ECS-optimized AMI
data "aws_ssm_parameter" "ecs_ami" {
  name = "/aws/service/ecs/optimized-ami/amazon-linux-2/recommended/image_id"
}

# IAM Role for EC2 Instances
resource "aws_iam_role" "ecs_instance" {
  name = "${var.project_name}-ecs-instance"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_instance_role" {
  role       = aws_iam_role.ecs_instance.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

resource "aws_iam_role_policy_attachment" "ecs_instance_ssm" {
  role       = aws_iam_role.ecs_instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "ecs_instance" {
  name = "${var.project_name}-ecs-instance-profile"
  role = aws_iam_role.ecs_instance.name
}

# Security Group for EC2 instances (allow internal traffic)
resource "aws_security_group" "ecs_ec2" {
  name_prefix = "${var.project_name}-ecs-ec2-"
  vpc_id      = module.vpc.vpc_id

  # Allow all traffic from within the VPC (for ECS agent, Docker, etc.)
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Launch Template for ECS EC2 instances
resource "aws_launch_template" "ecs_worker" {
  name_prefix   = "${var.project_name}-worker-"
  image_id      = data.aws_ssm_parameter.ecs_ami.value
  instance_type = var.worker_instance_type

  iam_instance_profile {
    name = aws_iam_instance_profile.ecs_instance.name
  }

  network_interfaces {
    associate_public_ip_address = false
    security_groups             = [aws_security_group.ecs_ec2.id]
  }

  # User data to join ECS cluster and install Docker Compose V2
  user_data = base64encode(<<-EOF
    #!/bin/bash
    
    # Join ECS cluster
    echo "ECS_CLUSTER=${aws_ecs_cluster.main.name}" >> /etc/ecs/ecs.config
    echo "ECS_ENABLE_TASK_IAM_ROLE=true" >> /etc/ecs/ecs.config
    echo "ECS_ENABLE_TASK_ENI=true" >> /etc/ecs/ecs.config
    
    # Ensure Docker is running
    systemctl enable docker
    systemctl start docker
    
    # Install Docker Compose V2 plugin (REQUIRED for Harbor)
    mkdir -p /usr/local/lib/docker/cli-plugins
    curl -SL https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-linux-x86_64 -o /usr/local/lib/docker/cli-plugins/docker-compose
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
    
    # Verify installation
    docker compose version
    
    # Add ec2-user to docker group (for debugging)
    usermod -aG docker ec2-user
  EOF
  )

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "${var.project_name}-worker"
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Auto Scaling Group for ECS EC2 instances
resource "aws_autoscaling_group" "ecs_worker" {
  name_prefix         = "${var.project_name}-worker-"
  vpc_zone_identifier = module.vpc.private_subnets
  
  min_size         = var.worker_ec2_min_count
  max_size         = var.worker_ec2_max_count
  desired_capacity = var.worker_ec2_desired_count

  launch_template {
    id      = aws_launch_template.ecs_worker.id
    version = "$Latest"
  }

  tag {
    key                 = "AmazonECSManaged"
    value               = true
    propagate_at_launch = true
  }

  tag {
    key                 = "Name"
    value               = "${var.project_name}-worker"
    propagate_at_launch = true
  }

  lifecycle {
    create_before_destroy = true
  }

  # Allow instances to be replaced during updates
  instance_refresh {
    strategy = "Rolling"
    preferences {
      min_healthy_percentage = 50
    }
  }
}

# ECS Capacity Provider for EC2
resource "aws_ecs_capacity_provider" "ec2_worker" {
  name = "${var.project_name}-ec2-worker"

  auto_scaling_group_provider {
    auto_scaling_group_arn         = aws_autoscaling_group.ecs_worker.arn
    managed_termination_protection = "DISABLED"

    managed_scaling {
      maximum_scaling_step_size = 10
      minimum_scaling_step_size = 1
      status                    = "ENABLED"
      target_capacity           = 80
    }
  }
}

