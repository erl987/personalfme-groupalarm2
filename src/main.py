import sys
from datetime import datetime, timedelta
from typing import List

import requests
import yaml

API_ENDPOINT = 'https://app.groupalarm.com/api/v1'
CONFIG_FILE_PATH = r'../config/config.yaml'


def get_header(api_token):
    return {
        'Content-Type': 'application/json',
        'API-Token': api_token
    }


def read_config_file():
    with open(CONFIG_FILE_PATH) as yaml_file:
        config = yaml.load(yaml_file, Loader=yaml.FullLoader)

    return config


def _get_entity_ids_from_endpoint(entity_names, organization_id, api_token, sub_endpoint,
                                  organization_param='organization') -> List[int]:
    r = requests.get(API_ENDPOINT + f'/{sub_endpoint}?{organization_param}={organization_id}',
                     headers=get_header(api_token))
    response = r.json()
    r.raise_for_status()

    entity_id_map = {}

    for entry in response:
        entity_id_map[entry['name']] = entry['id']

    entity_ids = []
    for entity_name in entity_names:
        if entity_name in entity_id_map:
            entity_ids.append(entity_id_map[entity_name])

    if len(entity_ids) != len(entity_names):
        raise ValueError(f'No all entities {sub_endpoint} found in the Groupalarm organization')

    return entity_ids


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
    print(r.status_code)
    #r.raise_for_status()
    print(r.json())


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


def get_command_line_arguments():
    alarm_code = int(sys.argv[1])
    alarm_time_point = sys.argv[2]
    alarm_type = sys.argv[3]

    return alarm_time_point, alarm_code, alarm_type


def main():
    alarm_time_point, alarm_code, alarm_type = get_command_line_arguments()
    config = read_config_file()
    send_alarm(config, alarm_time_point, alarm_code, alarm_type)


if __name__ == '__main__':
    main()
