# blog-aws-ec2-scheduled-shutdown-with-postpone
This repository contains code for deploying a solution to schedule shutdown of Amazon EC2 instances.  The part that sets this solution apart from others is that it provides the ability to postpone the shutdown. This helps considerably when the Amazon EC2 instance is about to be automatically be shutdown, however it is still in use.  The backend is deployed using API Gateway and AWS Lambda.  The solution uses AWS Serverless Application Model (SAM) to deploy resources in to an AWS Account. The AWS Lambda function is written in Python 3.7.