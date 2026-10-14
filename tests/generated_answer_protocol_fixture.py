"""Synthetic subprocess for stored-answer acceptance. No auth/network/live AI."""
import json
import os
import sys


def send(value):
    print(json.dumps(value), flush=True)


for line in sys.stdin:
    message = json.loads(line)
    method = message['method']
    if method == 'initialize':
        send({'id': message['id'], 'result': {
            'userAgent': 'discord_helper/0.162.1 (storage-fixture)',
            'codexHome': os.environ['CODEX_HOME']}})
    elif method == 'initialized':
        pass
    elif method == 'account/read':
        assert message['params'] == {'refreshToken': False}
        send({'id': message['id'], 'result': {'account': {'type': 'chatgpt',
              'email': 'fixture@example.invalid', 'planType': 'plus'}, 'requiresOpenaiAuth': True}})
    elif method == 'thread/start':
        assert message['params']['ephemeral'] is True
        send({'id': message['id'], 'result': {'thread': {'id': 'storage-thread', 'ephemeral': True, 'path': None}}})
    elif method == 'turn/start':
        data = json.loads(message['params']['input'][0]['text'])
        assert data['question'] == 'capacitor question'
        text = json.dumps({'text': 'Synthetic capacitor answer — NOT live AI',
                           'case_ids': [row['id'] for row in data['evidence']]})
        send({'id': message['id'], 'result': {'turn': {'id': 'storage-turn', 'status': 'inProgress', 'items': []}}})
        scope = {'threadId': 'storage-thread', 'turnId': 'storage-turn'}
        send({'method': 'item/agentMessage/delta', 'params': dict(scope, itemId='storage-item', delta=text)})
        send({'method': 'item/completed', 'params': dict(scope, item={
              'id': 'storage-item', 'type': 'agentMessage', 'phase': 'final_answer', 'text': text})})
        send({'method': 'turn/completed', 'params': {'threadId': 'storage-thread', 'turn': {
              'id': 'storage-turn', 'status': 'completed', 'error': None, 'items': []}}})
    else:
        raise AssertionError('unexpected fixture method')
