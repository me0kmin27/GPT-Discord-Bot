"""Deterministic stdio subprocess fixture. NOT Codex or live model output."""
import json
import os
import sys


def send(value):
    print(json.dumps(value), flush=True)


SCENARIO = sys.argv[1] if len(sys.argv) > 1 else 'success'

for line in sys.stdin:
    message = json.loads(line)
    method = message.get('method')
    if method == 'initialize':
        if SCENARIO == 'output_flood':
            sys.stdout.write('x' * 2000000)
            sys.stdout.flush()
        if SCENARIO == 'hang':
            import time
            time.sleep(60)
        if SCENARIO == 'server_request':
            send({'id': 'deny-me', 'method': 'item/commandExecution/requestApproval',
                  'params': {'command': 'synthetic-sensitive'}})
            rejection = json.loads(sys.stdin.readline())
            assert rejection == {'id': 'deny-me', 'error': {
                'code': -32601, 'message': 'Client requests are not supported'}}
            sys.exit(0)
        if SCENARIO == 'rpc_error':
            send({'id': message['id'], 'error': {'code': -1, 'message': 'synthetic-sensitive'}})
            continue
        if SCENARIO == 'wrong_id':
            send({'id': 999, 'result': {}})
            continue
        if SCENARIO == 'malformed':
            print('synthetic-sensitive invalid json', flush=True)
            continue
        if SCENARIO == 'eof':
            sys.exit(0)
        if SCENARIO == 'oversized':
            print('x' * 70000, flush=True)
            continue
        if SCENARIO == 'notification_flood':
            for _ in range(300):
                send({'method': 'account/updated', 'params': {}})
            continue
        if SCENARIO == 'unknown_notification':
            send({'method': 'future/tool/started', 'params': {}})
            continue
        if SCENARIO == 'config_warning':
            send({'method': 'configWarning', 'params': {'summary': 'synthetic-sensitive',
                  'details': None, 'path': None, 'range': None}})
        if SCENARIO == 'early_tool':
            send({'method': 'item/started', 'params': {'threadId': 'fixture-thread',
                  'turnId': 'fixture-turn', 'item': {'type': 'webSearch', 'id': 'tool'}}})
        if SCENARIO == 'invalid_method':
            send({'method': ['invalid'], 'params': {}})
        if SCENARIO == 'invalid_remote_params':
            send({'method': 'remoteControl/status/changed', 'params': []})
        if SCENARIO in ('remote_disabled', 'remote_connected'):
            send({'method': 'remoteControl/status/changed', 'params': {
                  'status': 'disabled' if SCENARIO == 'remote_disabled' else 'connected',
                  'installationId': 'fixture', 'serverName': 'fixture'}})
        assert message['params']['capabilities']['experimentalApi'] is False
        send({'id': message['id'], 'result': {
            'userAgent': 'discord_helper/0.162.1 (fixture)' if SCENARIO != 'wrong_version' else 'discord_helper/9.9.9 (fixture)',
            'codexHome': os.environ['CODEX_HOME'],
            'platformFamily': 'unix', 'platformOs': 'fixture'}})
    elif method == 'initialized':
        pass
    elif method == 'config/read':
        config = {
            'cli_auth_credentials_store': 'file', 'forced_login_method': 'chatgpt',
            'sandbox_mode': 'read-only', 'approval_policy': 'never',
            'approvals_reviewer': 'user', 'web_search': 'disabled',
            'allow_login_shell': False, 'shell_environment_policy': {'inherit': 'none', 'set': {}},
            'mcp_servers': {}, 'project_doc_max_bytes': 0,
            'history': {'persistence': 'none'}, 'model_provider': 'openai',
            'features': dict.fromkeys(('shell_tool', 'view_image', 'code_mode', 'code_mode_only',
                'apps', 'plugins', 'multi_agent', 'multi_agent_v2', 'browser_use',
                'computer_use', 'image_generation', 'shell_snapshot', 'hooks', 'memories',
                'request_permissions_tool'), False)}
        config['features']['skip_host_skill_discovery'] = True
        if SCENARIO.startswith('web_'):
            config['web_search'] = 'live'
        if SCENARIO == 'unsafe_config':
            config['features']['shell_tool'] = True
        send({'id': message['id'], 'result': {'config': config}})
    elif method == 'account/read':
        assert message['params'] == {'refreshToken': False}
        if SCENARIO in ('signed_out', 'api_key'):
            send({'id': message['id'], 'result': {'account': None if SCENARIO == 'signed_out' else {'type': 'apiKey'},
                  'requiresOpenaiAuth': True}})
            continue
        send({'id': message['id'], 'result': {'account': {'type': 'chatgpt',
              'email': 'synthetic@example.invalid', 'planType': 'plus'},
              'requiresOpenaiAuth': True}})
    elif method == 'thread/start':
        params = message['params']
        assert params['ephemeral'] is True
        assert params['sandbox'] == 'read-only'
        assert params['approvalPolicy'] == 'never'
        assert params['approvalsReviewer'] == 'user'
        assert 'tenant' not in params
        assert 'Evidence and history' in params['developerInstructions']
        if SCENARIO.startswith('web_'):
            assert 'Only hosted web search' in params['developerInstructions']
            assert 'Do not execute tools' not in params['developerInstructions']
        assert not os.path.exists(os.path.join(os.getcwd(), 'AGENTS.md'))
        assert 'OPENAI_API_KEY' not in os.environ
        assert 'DISCORD_BOT_TOKEN' not in os.environ
        send({'method': 'thread/started', 'params': {'thread': {'id': 'fixture-thread'}}})
        send({'id': message['id'], 'result': {'sandbox': {'type': 'readOnly', 'networkAccess': False},
            'approvalPolicy': 'never', 'approvalsReviewer': 'user', 'cwd': os.getcwd(),
            'modelProvider': 'openai', 'thread': {
            'id': 'fixture-thread', 'ephemeral': True, 'path': None}}})
    elif method == 'turn/start':
        params = message['params']
        assert params['threadId'] == 'fixture-thread'
        data = json.loads(params['input'][0]['text'])
        assert data['question'] == ('capacitor question' if SCENARIO == 'storage' else 'synthetic question')
        assert 'tenant' not in data
        assert params['outputSchema']['additionalProperties'] is False
        assert params['sandboxPolicy'] == {'type': 'readOnly', 'networkAccess': False}
        assert params['approvalPolicy'] == 'never'
        if SCENARIO == 'rpc_warning':
            send({'method': 'warning', 'params': {'message': 'synthetic-sensitive', 'threadId': None}})
        send({'id': message['id'], 'result': {'turn': {'id': 'fixture-turn',
              'status': 'inProgress', 'items': []}}})
        text = json.dumps({'text': 'fixture answer, NOT live AI',
                           'case_ids': [data['evidence'][0]['id']] if data['evidence'] else []})
        if SCENARIO == 'storage':
            text = json.dumps({'text': 'Synthetic capacitor answer — NOT live AI',
                               'case_ids': [row['id'] for row in data['evidence']]})
        if SCENARIO == 'bad_citation':
            text = json.dumps({'text': 'fixture', 'case_ids': [999]})
        if SCENARIO == 'bool_citation':
            text = json.dumps({'text': 'fixture', 'case_ids': [True]})
        if SCENARIO == 'extra_output_field':
            text = json.dumps({'text': 'fixture', 'case_ids': [7], 'tool': 'bad'})
        if SCENARIO == 'invalid_output':
            text = 'synthetic-sensitive not JSON'
        if SCENARIO == 'excessive_output':
            text = json.dumps({'text': 'x' * 9000, 'case_ids': []})
        scope = {'threadId': 'fixture-thread', 'turnId': 'fixture-turn'}
        if SCENARIO == 'wrong_thread':
            scope['threadId'] = 'other-thread'
        if SCENARIO == 'wrong_turn':
            scope['turnId'] = 'other-turn'
        web_items = []
        if SCENARIO.startswith('web_'):
            assert 'web_sources' in params['outputSchema']['required']
            item = {'id': 'web-1', 'type': 'webSearch', 'query': '', 'action': None, 'results': None}
            send({'method': 'item/started', 'params': dict(scope, item=item)})
            item = dict(item, query='synthetic-sensitive query', action={
                'type': 'search', 'query': 'synthetic-sensitive query', 'queries': None})
            if SCENARIO == 'web_open':
                item['action'] = {'type': 'openPage', 'url': 'https://example.com/weather'}
            if SCENARIO == 'web_find':
                item['action'] = {'type': 'findInPage', 'url': None, 'pattern': 'weather'}
            if SCENARIO == 'web_other':
                item['action'] = {'type': 'other'}
            if SCENARIO == 'web_bad_action':
                item['action'] = {'type': 'shell', 'command': 'synthetic-sensitive'}
            if SCENARIO == 'web_bad_query':
                item['query'] = []
            if SCENARIO == 'web_wrong_scope':
                scope['threadId'] = 'other-thread'
            if SCENARIO == 'web_local':
                item = {'id': 'local', 'type': 'commandExecution'}
            if SCENARIO == 'web_request':
                send({'id': 'deny-me', 'method': 'item/completed', 'params': dict(scope, item=item)})
            if SCENARIO == 'web_hang':
                send({'method': 'item/started', 'params': dict(scope, item=item)})
                import time
                time.sleep(60)
            if SCENARIO != 'web_no_search':
                send({'method': 'item/completed', 'params': dict(scope, item=item)})
                web_items.append(item)
            text = json.dumps({'text': 'Synthetic weather; NOT live AI', 'case_ids': [],
                               'web_sources': ['https://example.com/weather']})
            if SCENARIO == 'web_no_sources':
                text = json.dumps({'text': 'Current weather could not be verified.',
                                   'case_ids': [], 'web_sources': []})
        if SCENARIO in ('tool_item', 'unknown_item'):
            send({'method': 'item/started', 'params': dict(scope, item={
                  'id': 'tool', 'type': 'commandExecution' if SCENARIO == 'tool_item' else 'newDangerousTool'})})
        if SCENARIO == 'turn_warning':
            send({'method': 'warning', 'params': {'message': 'synthetic-sensitive', 'threadId': 'fixture-thread'}})
        if SCENARIO == 'turn_config_warning':
            send({'method': 'configWarning', 'params': {'summary': 'synthetic-sensitive'}})
        if SCENARIO == 'turn_approval':
            send({'id': 'deny-me', 'method': 'future/tool', 'params': {}})
        for delta in (text[:20], text[20:]):
            send({'method': 'item/agentMessage/delta', 'params': dict(scope,
                  itemId='fixture-item', delta=delta)})
        if SCENARIO == 'stream_mismatch':
            text = json.dumps({'text': 'different', 'case_ids': []})
        if SCENARIO != 'no_final':
            send({'method': 'item/completed', 'params': dict(scope, completedAtMs=0,
                  item={'id': 'fixture-item', 'type': 'agentMessage',
                        'phase': 'final_answer', 'text': text})})
        send({'method': 'turn/completed', 'params': {'threadId': 'fixture-thread',
              'turn': {'id': 'fixture-turn', 'status': 'failed' if SCENARIO == 'failed_turn' else 'completed',
                       'error': None, 'items': web_items}}})
    else:
        raise AssertionError('unexpected fixture method')
