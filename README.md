# AWS EC2 Scheduled Shutdown with ability to postpone

This repository contains code for deploying a solution to schedule shutdown of Amazon EC2 instances.

The part that sets this solution apart from others is that it provides the ability to postpone the shutdown. This helps considerably when the Amazon EC2 instance is still in use, however it is about to be automatically shutdown due to a schedule.

The backend is deployed using Amazon API Gateway, Amazon DynamoDB, Amazon EventBridge and AWS Lambda.

The solution uses AWS Serverless Application Model (SAM) to deploy resources in to an AWS Account. The AWS Lambda function is written in Python 3.7.

For detailed instructions, please visit https://nivleshc.wordpress.com/2022/08/01/scheduled-shutdown-of-amazon-ec2-instances-with-the-ability-to-postpone-backend/

# Backend  
## Preparation
Clone this repository using the following command.
```
git clone https://github.com/nivleshc/blog-aws-ec2-scheduled-shutdown-with-postpone.git
```
Update the **Makefile** with appropriate values for the following: 

**EMAIL_FROM_ADDRESS** - The FROM address that will be used to send emails to EC2 owners. You must have access to this email's inbox since a verification email will be sent to it.

**aws_profile** - update this with the name of your AWS CLI profile that will be used to deploy the backend into your AWS environment

**aws_s3_bucket** - update this with the name of the Amazon S3 bucket where the AWS SAM artefacts will be uploaded to. This Amazon S3 bucket must exist.

## Commands
For help, run the following command:
```
make
```
To deploy the code in this repository to your AWS account, use the following steps:

```
make package
make deploy
```

If you make any changes to **template.yaml**, first validate the changes by using the following command (validation is not required if you change other files):
```
make validate
```

After validation is successful, use the following command to deploy the changes:
```
make update
```

To delete all resources provisioned in AWS, run the following command. At the prompt, press CTRL+C to abort otherwise any other key to continue with the deletion.
```
make delete
```