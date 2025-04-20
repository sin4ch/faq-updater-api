import json
import boto3
import os
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
faq_updates_table = dynamodb.Table(os.environ['FAQ_UPDATES_TABLE'])

def lambda_handler(event, context):
    try:
        response = faq_updates_table.scan()
        faqs = response.get('Items', [])
        
        # Sort FAQs by count in descending order
        sorted_faqs = sorted(faqs, key=lambda x: x['count'], reverse=True)
        
        return {
            'statusCode': 200,
            'body': json.dumps(sorted_faqs)
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }