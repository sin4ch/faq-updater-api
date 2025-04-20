import boto3
import json
import os
from collections import Counter
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
comprehend = boto3.client('comprehend')

MESSAGES_TABLE = os.environ['MESSAGES_TABLE']
FAQ_UPDATES_TABLE = os.environ['FAQ_UPDATES_TABLE']

def lambda_handler(event, context):
    messages_table = dynamodb.Table(MESSAGES_TABLE)
    faq_updates_table = dynamodb.Table(FAQ_UPDATES_TABLE)

    all_messages = []
    scan_kwargs = {}

    # Paginate through scan results
    try:
        while True:
            response = messages_table.scan(**scan_kwargs)
            all_messages.extend(response.get('Items', []))
            last_evaluated_key = response.get('LastEvaluatedKey')
            if not last_evaluated_key:
                break
            scan_kwargs['ExclusiveStartKey'] = last_evaluated_key
    except Exception as e:
        print(f"Error scanning MessagesTable: {e}")
        return {'statusCode': 500, 'body': json.dumps({'error': f"Error scanning MessagesTable: {str(e)}"}) }

    if not all_messages:
        print("No messages found in MessagesTable.")
        return {'statusCode': 200, 'body': json.dumps({'message': 'No messages to process'})}

    # Extract text from messages
    texts = [msg.get('Body', '') for msg in all_messages if 'Body' in msg]

    if not texts:
        print("No message bodies found to analyze.")
        return {'statusCode': 200, 'body': json.dumps({'message': 'No message bodies found to analyze'})}

    # Batch process with Comprehend (max 25 texts per batch)
    key_phrases = []
    batch_size = 25
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i:i + batch_size]
        try:
            comprehend_response = comprehend.batch_detect_key_phrases(
                TextList=batch_texts,
                LanguageCode='en'
            )
            for result in comprehend_response.get('ResultList', []):
                key_phrases.extend([phrase['Text'] for phrase in result.get('KeyPhrases', [])])
        except Exception as e:
            print(f"Error calling Comprehend: {e}")
            continue

    if not key_phrases:
        print("No key phrases detected by Comprehend.")
        return {'statusCode': 200, 'body': json.dumps({'message': 'No key phrases detected'})}

    # Count top 10 key phrases
    phrase_counts = Counter(key_phrases)
    top_10_phrases = phrase_counts.most_common(10)

    # Update FaqUpdatesTable
    updated_at = datetime.utcnow().isoformat()
    try:
        with faq_updates_table.batch_writer() as batch:
            for phrase, count in top_10_phrases:
                batch.put_item(
                    Item={
                        'phrase': phrase,
                        'count': count,
                        'updatedAt': updated_at
                    }
                )
        print(f"Successfully updated FaqUpdatesTable with top {len(top_10_phrases)} phrases.")
    except Exception as e:
        print(f"Error writing to FaqUpdatesTable: {e}")
        return {'statusCode': 500, 'body': json.dumps({'error': f"Error writing to FaqUpdatesTable: {str(e)}"}) }

    return {
        'statusCode': 200,
        'body': json.dumps({'message': f'Successfully processed {len(all_messages)} messages and updated top {len(top_10_phrases)} phrases.'})
    }