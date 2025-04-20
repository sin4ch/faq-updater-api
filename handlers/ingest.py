import json
import boto3
import os
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
messages_table = dynamodb.Table(os.environ['MESSAGES_TABLE'])

def lambda_handler(event, context):
    try:
        body = json.loads(event['body'])
        message_id = body['MessageSid']
        from_number = body['From']
        message_body = body['Body']
        timestamp = datetime.utcnow().isoformat()

        # Write to DynamoDB
        messages_table.put_item(
            Item={
                'messageId': message_id,
                'from': from_number,
                'body': message_body,
                'timestamp': timestamp
            }
        )

        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Message ingested successfully'})
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }