# this function will postpone the shutdown of an ec2 instance.
import boto3
import os

dynamodb_name = os.environ['DYNAMODB_TABLE_NAME']
hours_to_postpone_shutdown_by = os.environ['POSTPONE_SHUTDOWN_BY_HRS']
minutes_to_send_email_before = os.environ['SEND_EMAIL_BEFORE_MIN']

dynamodb = boto3.resource('dynamodb')
ec2DynamoDBTable = dynamodb.Table(dynamodb_name)

def lambda_handler(event, context):

    # the payload in the API Gateway invocation URL contains the paramaters and their values that we will use.
    # find the token
    for parameter in event['body'].split("&"):
        object = parameter.split("=")
        if object[0] == "token":
            token = object[1]

    instanceId = ""
    message = ""
    statusCode = 200

    try:
        # find out if the token exists in dynamodb. If it does, then retrieve the instance details.
        dynamodb_item = ec2DynamoDBTable.get_item(
            Key={
                'Token': token
            }
        )

        item = dynamodb_item['Item']

        # extract the instance id
        instanceId = item['instanceId']
    except Exception as e:
        print(">Token:" + token + " does not exist in dynamodb table. Error:"+str(e))
        message = "The supplied token cannot be found in our records.\nThis could be due to the following:\n - token is invalid\n - token has been used once already\n - the AWS EC2 instance that the token refers to has already been automatically shutdown"
        statusCode = 400

    if (instanceId != ""):  
        # the token exists in DynamoDb and an instanceId has been obtained
        # find the instance and update its actual_shutdown_time tag so that it is 1 hour in the future
        client = boto3.client('ec2')

        ec2Instance = client.describe_instances(
            Filters=[
                {
                    'Name': 'instance-state-name',
                    'Values': [
                            'running'
                    ]
                }
            ],
            InstanceIds=[
                instanceId,
            ]
        )

        num_instances_found = len(ec2Instance['Reservations'])
        print(">Found " + str(num_instances_found) + ' ec2 instances for InstanceId=' + instanceId)

        if (num_instances_found == 0):
            message = "Error: Token is valid however no running ec2 instance with instanceId " + instanceId + " was found"
            statusCode = 400
            print('>', message)
        else:
            # get all tags for instanceId
            instanceId_tags = client.describe_tags(
                Filters=[{
                    'Name': 'resource-id',
                    'Values': [
                        instanceId
                    ]
                }]
            )

            # find the actual_shutdown_time tag value
            actual_shutdown_time = ""
            ec2_name = "(" + instanceId + ")"

            for tag in instanceId_tags['Tags']:
                key = tag['Key']
                value = tag['Value']

                if (key == 'actual_shutdown_time'):
                    actual_shutdown_time = value
                elif key == 'Name':
                    ec2_name = value + " " + ec2_name

            print('>actual_shutdown_time tag value:', actual_shutdown_time)

            # shutdown time is a string in the format HHMM eg 0900.
            # postpone the actual_shutdown_time by hours_to_postpone_shutdown_by hours. Need to ensure the time is in 24 hour time format and is 4 digits long.
            new_actual_shutdown_time = str((int(actual_shutdown_time) + (int(hours_to_postpone_shutdown_by) * 100)) % 2400).rjust(4, '0')

            message = "The scheduled shutdown time for your AWS EC2 Instance " + ec2_name + " has been successfully postponed by " + hours_to_postpone_shutdown_by + " hour(s)." \
                + "\nIt is now scheduled to automatically shutdown at " + new_actual_shutdown_time + "." \
                + "\nYou will receive an email notification approximately " + minutes_to_send_email_before + " minutes before the scheduled shutdown time."
            statusCode = 200

            # a new notification will be sent closer to the new shutdown time. Clear the tag that states that an email notification was previously sent and also update the
            # actual shutdown time with the new time
            update_actual_shutdown_time_tag_response = client.create_tags(
                Resources=[
                    instanceId
                ],
                Tags=[
                    {
                        'Key': 'actual_shutdown_time',
                        'Value': new_actual_shutdown_time
                    },
                    {
                        'Key': 'email_notification_sent',
                        'Value': 'False'
                    }

                ]
            )
            print('>response after updating actual_shutdown_time_tag', str(update_actual_shutdown_time_tag_response))
            # delete token from dynamodb so that user cannot postpone the ec2 instance more than once using the same token
            deletion_response = ec2DynamoDBTable.delete_item(
                Key={
                    'Token': token
                }
            )
            print(">deleted token from dynamodb. Response:"+ str(deletion_response))
    return {
        "statusCode": statusCode,
        "body": message
    }
