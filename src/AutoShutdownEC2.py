import json
import boto3
import math
import os
import uuid
from datetime import datetime

# global variables and constants
send_email_before_minutes = os.environ['SEND_EMAIL_BEFORE_MIN'] # Send an email this many minutes before the scheduled shutdown to ask if the the shutdown needs to be postponed
ec2_shutdown_window = os.environ['EC2_SHUTDOWN_WINDOW'] # If an ec2 instance has a scheduled shutdown time and it is turned on within this many minutes after scheduled shutdown, it will be shutdown again.
email_from_address = os.environ['EMAIL_FROM_ADDRESS'] # this is the FROM address of the emails that will be sent for postponing the scheduled shutdown
api_gateway_postpone_url = os.environ['API_GATEWAY_POSTPONE_ENDPOINT']
dynamodb_table_name = os.environ['DYNAMODB_TABLE_NAME']
dynamodb_item_expiry_in_min = os.environ['TOKEN_TTL_MIN'] # expire items in dynamodb after this many minutes - TTL

#link to the EC2ShutDown DynamoDB Table
dynamodb = boto3.resource('dynamodb')
ec2DynamoDBTable = dynamodb.Table(dynamodb_table_name)

def send_email(message_type, recipient_addr, ec2_name, token, time_to_shutdown, additional_message):
    postpone_email_subject = ec2_name + " will be shutdown in " + str(time_to_shutdown) + " minute(s)"
    postpone_email_body = '<!DOCTYPE html><html><head><title>'+ ec2_name + ' will be shutdown in ' + str(time_to_shutdown) + ' minute(s)</title> \
                          </head><body>Your AWS EC2 Instance <strong>' + ec2_name + '</strong> will be automatically shutdown in ' + str(time_to_shutdown) + \
                          ' minute(s). Click the button below to postpone the shutdown. \
                          <form action="' + api_gateway_postpone_url + '" method="POST">\
                          <input type="hidden" id="token" name="token" value="' + token + '"> \
                          <br><input type="submit" value="Postpone shutdown by 1 hour"></form></body></html>'

    shutdown_email_subject = ec2_name + " has been automatically shutdown"
    shutdown_email_body = '<!DOCTYPE html><html><head><title>' + ec2_name + ' autoshutdown complete</title></head><body><strong>' + ec2_name + \
                          '</strong> has been successfully shutdown. <br>' + additional_message + '</body> </html>'

    send_email = True # boolean to signal if email should be sent

    if (message_type == 'postpone'):
        email_subject = postpone_email_subject
        email_body = postpone_email_body
    elif (message_type == 'shutdown'):
        email_subject = shutdown_email_subject
        email_body = shutdown_email_body
    else:
        print('send_email:Invalid message type[' + message_type + '] provided. No email will be sent')
        send_email = False

    if (send_email):
        ses = boto3.client('ses', 'ap-southeast-2')
        ses_send_email_response = ses.send_email(
            Destination={
                'ToAddresses': [recipient_addr]
            },
            Message={
                'Body': {
                    'Html': {
                        'Charset': 'UTF-8',
                        'Data': email_body,
                    },
                },
                'Subject': {
                    'Charset': 'UTF-8',
                    'Data': email_subject,
                },
            },
            Source=email_from_address,
        )
        print(">send_email:Email sent message_type=" + message_type + " recipient=" + recipient_addr + " ses_response:" + str(ses_send_email_response))

# add entry to dynamodb
def add_to_dynamodb(uuid_str, instanceId, expirationTime):
    response = ec2DynamoDBTable.put_item(
        Item={
            'Token':uuid_str,
            'instanceId':instanceId,
            'ExpirationTime': expirationTime
        }
    )
    print('>add_to_dynamodb: Added record to dynamodb table. Token=' + uuid_str + ' instanceId=' + str(instanceId) + ' TTL=' + str(expirationTime) + ' DynamoDBResponse='+ str(response))

def process_ec2_shutdown_events():
    client = boto3.client("ec2")

    # find all instances that satisfy the following conditions (tag key/value is case-sensitive)
    # - have the tag autoshutdown=true
    # - is running

    ec2Instances = client.describe_instances(
        Filters=[
            {
                'Name': 'tag:autoshutdown',
                'Values': [
                    'true'
                ]
            },
            {
                'Name': 'instance-state-name',
                'Values': [
                    'running'
                ]
            }

        ],
        MaxResults=1000,
    )

    # if no ec2 instances matched filter, output a message to say so
    num_instances_found = len(ec2Instances['Reservations'])

    if ( num_instances_found == 0):
        print(">process_ec2_shutdown_events. No running ec2 instances with tag autoshutdown=true were found. Exiting")
    else:
        print(">Found " + str(num_instances_found) + " running instance(s) with tag autoshutdown=true")
        # process each ec2 instance matching filter
        for ec2Instance in ec2Instances['Reservations']:
            instance = ec2Instance['Instances'][0]

            instanceId = instance['InstanceId']
            instanceType = instance['InstanceType']
            privateIpAddress = instance['PrivateIpAddress']
            state = instance['State']['Name']

            # get all the tags on this ec2 instance, then find those that we are looking for
            tags = instance['Tags']
            shutdown_time = ""
            shutdown_time_tag_exists = False
            actual_shutdown_time = ""
            actual_shutdown_time_tag_exists = False
            owner_email_address = ""
            email_notification_sent = False
            name = ""

            for tag in tags:
                key = tag['Key']
                value = tag['Value']

                if key == "shutdown_time":
                    shutdown_time_tag_exists = True
                    shutdown_time = value
                elif key == 'owner_email':
                    owner_email_address = value
                elif key == 'actual_shutdown_time':
                    actual_shutdown_time_tag_exists = True
                    actual_shutdown_time = value
                elif key == 'email_notification_sent':
                    email_notification_sent = (value == 'True') # convert the tag from string to boolean
                elif key == 'Name':
                    name = value

            msg = ">process_ec2_shutdown_events: InstanceId:" + instanceId + " Name:" + name + " InstanceType:" + instanceType + \
                " PrivateIpAddress:" + privateIpAddress + " State:" + state + \
                " Shutdown_Time:" + shutdown_time + " Actual_Shutdown_Time:" + \
                actual_shutdown_time + " Owner Email Address:" + owner_email_address + " email_notification_previously_sent:" + str(email_notification_sent)
            print(msg)

            # if this ec2 instance has a friendly name, use that with the instanceId to make it more recognizable
            if (name != ""):
                ec2_name = name + "(" + instanceId + ")"
            else:
                ec2_name = instanceId

            # When checking to see if an ec2 instance needs to be shutdown, a tag 'actual_shutdown_time' will be checked. This will contain the time when this ec2 instance 
            # should actually be shutdown. This is the value that will be incremented when the owner of the ec2 instance decides to postpone the shutdown time.
            if (not actual_shutdown_time_tag_exists) and shutdown_time_tag_exists:
                create_tag_response = client.create_tags(
                    Resources = [
                        instanceId
                    ],
                    Tags=[
                        {
                            'Key':'actual_shutdown_time',
                            'Value': shutdown_time
                        }
                    ]
                )
                actual_shutdown_time_tag_exists = True
                actual_shutdown_time = shutdown_time
                print(">process_ec2_shutdown_events: actual_shutdown_time tag not found. Created tag. Response when creating tag:"+str(create_tag_response))

            # if actual_shutdown_time_tag exists then check if its value is within 15min of now
            # use todays date and shutdown time to create a datetime object of the actual shutdown time
            if actual_shutdown_time_tag_exists:
                actual_shutdown_time_dateobj = datetime.strptime(str(datetime.date(datetime.now())) + ':' + actual_shutdown_time, '%Y-%m-%d:%H%M')
                time_diff = actual_shutdown_time_dateobj - datetime.now()
                print(">process_ec2_shutdown_events:time_now:"+str(datetime.now()) + " actual_shutdowntime:"+str(actual_shutdown_time_dateobj) + " time_diff(actualshutdown-now)min:"+str(time_diff))

                if time_diff.days == 0:
                    # This means that actual_shudowntime is in the future, within a day. 
                    # Also check if its less than send_email_before seconds in the future, since we will need to send an email to the owner to postone the automatic shutdown.
                    # However, do not send the postponement email, if it has already been sent.
                    if (time_diff.seconds <= (int(send_email_before_minutes) * 60)) and (not email_notification_sent):
                        time_to_shutdown = math.floor(time_diff.seconds/60) # be conservative and round down the remaining time
                        
                        # update dynamodb with details about this instance
                        uuid_str = str(uuid.uuid4())

                        # calculate the TTL for the item that will be inserted into DynamoDB
                        time_now = datetime.now()
                        epoch_time_now = time_now.timestamp()
                        expirationTime = int(epoch_time_now + (int(dynamodb_item_expiry_in_min) * 60))   # convert expiry days to seconds

                        # add this entry to dynamodb
                        add_to_dynamodb(uuid_str, instanceId, expirationTime)
                        print(">process_ec2_shutdown_events: sending email notification. EC2 shutdown in: " + str(time_to_shutdown) + " minute(s)")
                        
                        send_email('postpone',owner_email_address,ec2_name,uuid_str,time_to_shutdown,'')

                        # add a tag to the ec2 instance to signal that an email regarding postponing the automtated shutdown has been sent
                        email_notification_sent_tag_creation_response = client.create_tags(
                            Resources = [
                                instanceId
                            ],
                            Tags=[
                                {
                                    'Key': 'email_notification_sent',
                                    'Value': 'True'
                                }
                            ]
                        )
                        print(">process_ec2_shutdown_events: email_notification_sent tag created. Response:"+str(email_notification_sent_tag_creation_response))
                elif time_diff.days == -1: 
                    # This ec2 instance's scheduled shutdown time was sometime in the last 24 hours. Find out if it had to be shutdown
                    # in the last ec2_shutdown_window minutes. If so, then shut it down.

                    # Unfortunately this means that if an ec2 instance has been automatically shutdown and someone manually starts it within ec2_shutdown_window minutes of 
                    # its actual shutdown time, it will be automatically shutdown again. Owners need to be informed about this.

                    # when shutdown time is in the past, the diff is shown as 24hr - (datetime.now() - actual_shutdown_time_dateobj). To get the 
                    # difference, we need to subtract this from 24h
                    minutes_since_scheduled_shutdown = (24 - (time_diff.seconds/3600))*60
                    print(">process_ec2_shutdown_events: ec2 shutdown time was "+ str(minutes_since_scheduled_shutdown) + " minutes ago.")
                    if (minutes_since_scheduled_shutdown <= int(ec2_shutdown_window)):
                        print(">process_ec2_shutdown_events: ec2 scheduled shutdown time is within the shutdown window. This ec2 instance will now be shutdown")
                        instance_shutdown_response = client.stop_instances(
                            InstanceIds=[
                                instanceId
                            ]
                        )
                        # delete all tags that are used to track instance shutdown. These will be automatically populated by this script when the ec2 instance gets 
                        # started again.
                        delete_shutdown_tracking_tags_response = client.delete_tags(
                            Resources = [
                                instanceId
                            ],
                            Tags=[
                                {
                                    'Key': 'email_notification_sent'
                                },
                                {
                                    'Key': 'actual_shutdown_time'
                                },
                            ]
                        )
                        print(">Process_ec2_shutdown_events: Instance shutdown response:"+ str(instance_shutdown_response))
                        print(">Process_ec2_shutdown_events: Deletion of shutdown tracking tags response:" + str(delete_shutdown_tracking_tags_response))
                        additional_message = '<strong>Shutdown response</strong>: ' + str(instance_shutdown_response)
              
                        send_email('shutdown', owner_email_address, ec2_name, instanceId,'', additional_message)
                    else:
                        print(">Process_ec2_shutdown_events: ec2 scheduled shutdown time is outside the shutdown window (" + ec2_shutdown_window + "). This ec2 instance WILL NOT be shutdown")

def lambda_handler(event, context):
    process_ec2_shutdown_events()
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": ">successfully checked and actioned any ec2 shutdown events",
        }),
    }
