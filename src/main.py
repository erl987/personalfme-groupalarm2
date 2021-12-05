import sys
from datetime import datetime, timedelta
from typing import List, Tuple

from cerberus import Validator
import requests
import yaml

API_ENDPOINT = 'https://app.groupalarm.com/api/v1'
CONFIG_FILE_PATH = r'../config/config.yaml'

YAML_CONFIG_FILE_SCHEMA = {
    'config': {
        'type': 'dict',
        'schema': {
            'login': {
                'type': 'dict',
                'schema': {
                    'organization-id': {'type': 'integer'},
                    'api-token': {'type': 'string'}
                }
            },
            'alarms': {
                'type': 'dict',
                'keyschema': {'type': 'string', 'minlength': 5, 'maxlength': 5},
                'valueschema': {
                    'type': 'dict',
                    'schema': {
                        'resources': {
                            'type': 'dict',
                            'schema': {
                                'allUsers': {'type': 'boolean', 'excludes': ['labels', 'scenarios', 'units']},
                                'labels': {
                                    'type': 'list',
                                    'excludes': ['allUsers', 'scenarios', 'units'],
                                    'schema': {
                                        'type': 'dict',
                                        'keyschema': {'type': 'string'},
                                        'valueschema': {'type': 'integer', 'min': 1},
                                        'minlength': 1,
                                        'maxlength': 1
                                    }
                                },
                                'scenarios': {
                                    'type': 'list',
                                    'excludes': ['allUsers', 'labels', 'units'],
                                    'schema': {'type': 'string'}
                                },
                                'units': {
                                    'type': 'list',
                                    'excludes': ['allUsers', 'labels', 'scenarios'],
                                    'schema': {'type': 'string'}
                                }
                            }
                        },
                        'message': {'type': 'string', 'excludes': 'messageTemplate'},
                        'messageTemplate': {'type': 'string', 'excludes': 'message'},
                        'closeEventInHours': {'type': 'integer', 'min': 0}
                    }
                }
            }
        }
    }

}


def get_header(api_token):
    return {
        'Content-Type': 'application/json',
        'API-Token': api_token
    }


def read_config_file():
    with open(CONFIG_FILE_PATH) as yaml_file:
        config = yaml.load(yaml_file, Loader=yaml.FullLoader)

    v = Validator(require_all=True)
    if not v.validate({'config': config}, YAML_CONFIG_FILE_SCHEMA):
        raise SyntaxError(v.errors)

    return config


def _get_entity_ids_from_endpoint(entity_names, organization_id, api_token, sub_endpoint,
                                  organization_param='organization') -> List[int]:
    r = requests.get(API_ENDPOINT + f'/{sub_endpoint}?{organization_param}={organization_id}',
                     headers=get_header(api_token))
    json_response = _get_json_response(r)
    r.raise_for_status()

    entity_id_map = {}
    for entry in json_response:
        entity_id_map[entry['name']] = entry['id']

    found_entity_names = []
    entity_ids = []
    for entity_name in entity_names:
        if entity_name in entity_id_map:
            entity_ids.append(entity_id_map[entity_name])
            found_entity_names.append(entity_name)

    if len(entity_ids) != len(entity_names):
        missing_entities = set(entity_names).difference(set(found_entity_names))
        raise ValueError(f'Did not find the following *{sub_endpoint}* in the Groupalarm '
                         f'organization {organization_id}: ' + ', '.join(missing_entities))

    return entity_ids


def _get_json_response(r):
    if 'Content-Type' in r.headers and r.headers.get('Content-Type').startswith('application/json'):
        response = r.json()
        if 'success' in response and 'error' in response and not response['success']:
            message = response['message']
            details = response['error']
            print(f'Error message: {message}, details: {details}', file=sys.stderr)
    else:
        response = None

    return response


def get_ids_for_units(unit_names, organization_id, api_token) -> List[int]:
    return _get_entity_ids_from_endpoint(unit_names, organization_id, api_token, 'units')


def get_ids_for_labels(label_names, organization_id, api_token) -> List[int]:
    return _get_entity_ids_from_endpoint(label_names, organization_id, api_token, 'labels')


def get_ids_for_users(user_names, organization_id, api_token) -> List[int]:
    return _get_entity_ids_from_endpoint(user_names, organization_id, api_token, 'users')


def get_ids_for_scenarios(scenario_names, organization_id, api_token) -> List[int]:
    return _get_entity_ids_from_endpoint(scenario_names, organization_id, api_token, 'scenarios')


def get_alarm_template_id(alarm_template_name, organization_id, api_token) -> int:
    return _get_entity_ids_from_endpoint([alarm_template_name], organization_id, api_token, 'alarms/templates',
                                         'organization_id')[0]


def to_isoformat_string(time_point: datetime):
    return time_point.isoformat() + 'Z'


def get_close_event_time_period(alarm_code, config) -> timedelta:
    _check_alarm_code_has_config(alarm_code, config)

    return timedelta(hours=config['alarms'][alarm_code]['closeEventInHours'])


def send_alarm(config, alarm_time_point, alarm_code, alarm_type):
    organization_id = config['login']['organization-id']
    api_token = config['login']['api-token']

    alarm_resources = get_alarm_resources(alarm_code, api_token, config, organization_id)
    alarm_template_id, message = get_alarm_message(alarm_code, config, organization_id, api_token)

    request_body = {
        'alarmResources': alarm_resources,
        'organizationID': organization_id,
        'startTime': to_isoformat_string(datetime.utcnow()),
        'scheduledEndTime': to_isoformat_string(datetime.utcnow() + get_close_event_time_period(alarm_code, config)),
        'eventName': f'[Funkmelderalarm] Schleife {alarm_code} {alarm_time_point} ({alarm_type})'
    }

    if message:
        request_body['message'] = message
    elif alarm_template_id:
        request_body['alarmTemplateID'] = alarm_template_id

    r = requests.post(API_ENDPOINT + '/alarm', headers=get_header(api_token), json=request_body)
    json_response = _get_json_response(r)
    r.raise_for_status()
    return json_response


def get_alarm_message(alarm_code, config, organization_id, api_token):
    _check_alarm_code_has_config(alarm_code, config)

    message = None
    alarm_template_id = None

    alarm_config = config['alarms'][alarm_code]
    if 'message' in alarm_config:
        message = alarm_config['message']
    elif 'messageTemplate' in alarm_config:
        alarm_template_id = get_alarm_template_id(alarm_config['messageTemplate'], organization_id, api_token)
    else:
        raise AssertionError('Incorrect YAML configuration file: no alarm message')

    return alarm_template_id, message


def get_alarm_resources(alarm_code, api_token, config, organization_id):
    _check_alarm_code_has_config(alarm_code, config)

    resources = config['alarms'][alarm_code]['resources']
    if 'allUsers' in resources and resources['allUsers']:
        alarm_resources = {'allUsers': True}
    elif 'labels' in resources:
        label_names = []
        for entry in resources['labels']:
            label_names.append(list(entry.keys())[0])
        label_ids = get_ids_for_labels(label_names, organization_id, api_token)
        labels_array = []
        for index, entry in enumerate(resources['labels']):
            labels_array.append({'amount': list(entry.values())[0], 'labelID': label_ids[index]})
        alarm_resources = {'labels': labels_array}
    elif 'units' in resources:
        unit_ids = get_ids_for_units(resources['units'], organization_id, api_token)
        alarm_resources = {'units': unit_ids}
    elif 'users' in resources:
        user_ids = get_ids_for_users(resources['users'], organization_id, api_token)
        alarm_resources = {'users': user_ids}
    elif 'scenarios' in resources:
        scenario_ids = get_ids_for_scenarios(resources['scenarios'], organization_id, api_token)
        alarm_resources = {'scenarios': scenario_ids}
    else:
        raise AssertionError('Incorrect YAML configuration file: no alarm resources')

    return alarm_resources


def _check_alarm_code_has_config(alarm_code, config):
    if alarm_code not in config['alarms']:
        raise ValueError(f'No alarm configuration for the alarm code {alarm_code}')


def get_command_line_arguments() -> Tuple[str, str, str]:
    alarm_code = sys.argv[1]
    alarm_time_point = sys.argv[2]
    alarm_type = sys.argv[3]

    return alarm_time_point, alarm_code, alarm_type


def main():
    try:
        alarm_time_point, alarm_code, alarm_type = get_command_line_arguments()
        config = read_config_file()
        send_alarm(config, alarm_time_point, alarm_code, alarm_type)
    except Exception as e:
        print(f'Error: {e}', file=sys.stderr)


if __name__ == '__main__':
    main()
