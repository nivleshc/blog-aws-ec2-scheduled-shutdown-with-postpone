# define variables
aws_profile = myawsprofile
aws_s3_bucket = mys3bucket
PROJECT_NAME = EC2ScheduledShutdownWithPostpone
SEQUENCE_NUMBER = 1
aws_s3_bucket_prefix = ${PROJECT_NAME}
aws_stack_name = sam-${PROJECT_NAME}-${SEQUENCE_NUMBER}
aws_stack_iam_capabilities = CAPABILITY_IAM CAPABILITY_NAMED_IAM
sam_package_template_file = template.yaml
sam_package_output_template_file = package.yaml
EMAIL_FROM_ADDRESS = email_from_address@mydomain.com

.PHONY: all usage package deploy update validate clean

all: usage

usage:
	@echo
	@echo make package - package the sam application and copy it to the s3 bucket [s3://${aws_s3_bucket}/${aws_s3_bucket_prefix}/]
	@echo make deploy  - deploy the packaged sam application to AWS
	@echo make update  - package the sam application and then deploy it to AWS
	@echo make validate - validate template file [${sam_package_template_file}]
	@echo make clean   - delete local package.yml file
	@echo make delete  - delete the AWS CloudFormation Stack that was created by this AWS SAM template

package:
	sam package --template-file ${sam_package_template_file} --output-template-file ${sam_package_output_template_file} --s3-bucket ${aws_s3_bucket} --s3-prefix ${aws_s3_bucket_prefix} --profile ${aws_profile}

deploy:
	sam deploy \
	--template-file ${sam_package_output_template_file} \
	--stack-name ${aws_stack_name} \
	--capabilities ${aws_stack_iam_capabilities} \
	--profile ${aws_profile} \
	--parameter-overrides \
	'ParameterKey=SequenceNumber,ParameterValue=${SEQUENCE_NUMBER}' \
	'ParameterKey=EmailFromAddress,ParameterValue=${EMAIL_FROM_ADDRESS}'

update:
	make clean
	make package
	make deploy

validate:
	sam validate --template-file ${sam_package_template_file}

clean:
	rm -f ./${sam_package_output_template_file}

delete:
	read -p 'Delete CloudFormation Stack:${aws_stack_name}? CTRL+C to abort or any other key to continue.'
	aws cloudformation delete-stack --stack-name ${aws_stack_name}