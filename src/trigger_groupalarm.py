#  personalfme-groupalarm2 - Trigger alarms via groupalarm.com on the command line
#   Copyright (C) 2021 Ralf Rettig (info@personalfme.de)
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.

import argparse
import os
import sys
import traceback
from datetime import datetime, timedelta
from typing import List

import requests
import yaml
from cerberus import Validator

API_ENDPOINT = 'https://app.groupalarm.com/api/v1'
DEFAULT_CONFIG_FILE_PATH = r'../config/config.yaml'
YAML_CONFIG_FILE_SCHEMA = {
    'config': {
        'type': 'dict',
        'schema': {
            'login': {
                'type': 'dict',
                'required': False,
                'schema': {
                    'organization-id': {'type': 'integer', 'required': False},
                    'api-token': {'type': 'string', 'required': False}
                }
            },
            'proxy': {
                'type': 'dict',
                'required': False,
                'schema': {
                    'address': {'type': 'string'},
                    'port': {'type': 'integer'},
                    'username': {'type': 'string', 'required': False},
                    'password': {'type': 'string', 'required': False}
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
                        'closeEventInHours': {'type': 'integer', 'required': False, 'min': 0}
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


def read_config_file(config_file_path):
    try:
        with open(config_file_path) as yaml_file:
            config = yaml.load(yaml_file, Loader=yaml.FullLoader)

        v = Validator(require_all=True)
        if not v.validate({'config': config}, YAML_CONFIG_FILE_SCHEMA):
            raise SyntaxError(v.errors)

        if 'login' not in config:
            config['login'] = {}

        if 'organization-id' not in config['login']:
            if 'ORGANIZATION_ID' not in os.environ:
                raise EnvironmentError('The Groupalarm organization id either needs to be provided in the environment '
                                       'variable ORGANIZATION_ID or in the YAML configuration file')
            config['login']['organization-id'] = int(os.getenv('ORGANIZATION_ID'))
        else:
            if 'ORGANIZATION_ID' in os.environ:
                raise EnvironmentError('The Groupalarm organization id is both provided in the environment variable '
                                       'ORGANIZATION_ID as well as in the YAML configuration file')

        if 'api-token' not in config['login']:
            if 'API_TOKEN' not in os.environ:
                raise EnvironmentError('The Groupalarm API token either needs to be provided in the environment '
                                       'variable API-TOKEN or in the YAML configuration file')
            config['login']['api-token'] = os.getenv('API_TOKEN')
        else:
            if 'API_TOKEN' in os.environ:
                raise EnvironmentError('The Groupalarm API token is both provided in the environment variable '
                                       'API_TOKEN as well as in the YAML configuration file')

        return config
    except Exception as e:
        print(f'Fehler beim Lesen der Konfigurationsdatei: {e}', file=sys.stderr)
        raise


def _get_proxies(proxy_config):
    if not proxy_config:
        return {}

    if 'username' in proxy_config:
        user = proxy_config['username']
    else:
        user = None
    if 'password' in proxy_config:
        password = proxy_config['password']
    else:
        password = None
    address = proxy_config['address']
    port = proxy_config['port']

    if user and password:
        return {'https': f'https://{user}:{password}@{address}:{port}'}
    elif user:
        return {'https': f'https://{user}@{address}:{port}'}
    else:
        return {'https': f'https://{address}:{port}'}


def _get_entity_ids_from_endpoint(entity_names, organization_id, api_token, proxy_config, sub_endpoint,
                                  organization_param='organization') -> List[int]:
    r = requests.get(API_ENDPOINT + f'/{sub_endpoint}?{organization_param}={organization_id}',
                     headers=get_header(api_token), proxies=_get_proxies(proxy_config))
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
            print(f'Information vom Server Groupalarm.com: {message}, Details: {details}', file=sys.stderr)
    else:
        response = None

    return response


def get_ids_for_units(unit_names, organization_id, api_token, proxy_config) -> List[int]:
    return _get_entity_ids_from_endpoint(unit_names, organization_id, api_token, proxy_config, 'units')


def get_ids_for_labels(label_names, organization_id, api_token, proxy_config) -> List[int]:
    return _get_entity_ids_from_endpoint(label_names, organization_id, api_token, proxy_config, 'labels')


def get_ids_for_users(user_names, organization_id, api_token, proxy_config) -> List[int]:
    return _get_entity_ids_from_endpoint(user_names, organization_id, api_token, proxy_config, 'users')


def get_ids_for_scenarios(scenario_names, organization_id, api_token, proxy_config) -> List[int]:
    return _get_entity_ids_from_endpoint(scenario_names, organization_id, api_token, proxy_config, 'scenarios')


def get_alarm_template_id(alarm_template_name, organization_id, api_token, proxy_config) -> int:
    return _get_entity_ids_from_endpoint([alarm_template_name], organization_id, api_token, proxy_config,
                                         'alarms/templates', 'organization_id')[0]


def to_isoformat_string(time_point: datetime):
    return time_point.isoformat() + 'Z'


def get_close_event_time_period(alarm_code, config):
    _check_alarm_code_has_config(alarm_code, config)

    if 'closeEventInHours' not in config['alarms'][alarm_code]:
        return None

    return timedelta(hours=config['alarms'][alarm_code]['closeEventInHours'])


def send_alarm(config, alarm_time_point, alarm_code, alarm_type, do_emit_alarm):
    try:
        organization_id = config['login']['organization-id']
        api_token = config['login']['api-token']
        if 'proxy' in config:
            proxy_config = config['proxy']
        else:
            proxy_config = None

        alarm_resources = get_alarm_resources(alarm_code, api_token, config, organization_id, proxy_config)
        alarm_template_id, message = get_alarm_message(alarm_code, config, organization_id, api_token, proxy_config)

        request_body = {
            'alarmResources': alarm_resources,
            'organizationID': organization_id,
            'startTime': to_isoformat_string(datetime.utcnow()),
            'eventName': f'[Funkmelderalarm] Schleife {alarm_code} {alarm_time_point} ({alarm_type})'
        }

        close_event_time_period = get_close_event_time_period(alarm_code, config)
        if close_event_time_period:
            request_body['scheduledEndTime'] = to_isoformat_string(datetime.utcnow() + close_event_time_period)

        if message:
            request_body['message'] = message
        elif alarm_template_id:
            request_body['alarmTemplateID'] = alarm_template_id

        preview_endpoint = ''
        if not do_emit_alarm:
            preview_endpoint = '/preview'
        r = requests.post(API_ENDPOINT + '/alarm' + preview_endpoint, headers=get_header(api_token), json=request_body,
                          proxies=_get_proxies(proxy_config))
        _get_json_response(r)
        r.raise_for_status()

        if do_emit_alarm:
            print('Alarm erfolgreich ausgelöst')
        else:
            print('Die Alarmkonfiguration wurde auf Groupalarm.com getestet und ist gültig')
    except Exception as e:
        print(f'Fehler beim Versand der Alarmierung: {e}', file=sys.stderr)
        raise


def get_alarm_message(alarm_code, config, organization_id, api_token, proxy_config):
    _check_alarm_code_has_config(alarm_code, config)

    message = None
    alarm_template_id = None

    alarm_config = config['alarms'][alarm_code]
    if 'message' in alarm_config:
        message = alarm_config['message']
    elif 'messageTemplate' in alarm_config:
        alarm_template_id = get_alarm_template_id(alarm_config['messageTemplate'], organization_id, api_token,
                                                  proxy_config)
    else:
        raise ValueError('Incorrect YAML configuration file: no alarm message')

    return alarm_template_id, message


def get_alarm_resources(alarm_code, api_token, config, organization_id, proxy_config):
    _check_alarm_code_has_config(alarm_code, config)

    resources = config['alarms'][alarm_code]['resources']
    if 'allUsers' in resources and resources['allUsers']:
        alarm_resources = {'allUsers': True}
    elif 'labels' in resources:
        label_names = []
        for entry in resources['labels']:
            label_names.append(list(entry.keys())[0])
        label_ids = get_ids_for_labels(label_names, organization_id, api_token, proxy_config)
        labels_array = []
        for index, entry in enumerate(resources['labels']):
            labels_array.append({'amount': list(entry.values())[0], 'labelID': label_ids[index]})
        alarm_resources = {'labels': labels_array}
    elif 'units' in resources:
        unit_ids = get_ids_for_units(resources['units'], organization_id, api_token, proxy_config)
        alarm_resources = {'units': unit_ids}
    elif 'users' in resources:
        user_ids = get_ids_for_users(resources['users'], organization_id, api_token, proxy_config)
        alarm_resources = {'users': user_ids}
    elif 'scenarios' in resources:
        scenario_ids = get_ids_for_scenarios(resources['scenarios'], organization_id, api_token, proxy_config)
        alarm_resources = {'scenarios': scenario_ids}
    else:
        raise ValueError('Incorrect YAML configuration file: no alarm resources')

    return alarm_resources


def _check_alarm_code_has_config(alarm_code, config):
    if alarm_code not in config['alarms']:
        raise ValueError(f'No alarm configuration for the alarm code {alarm_code}')


def get_command_line_arguments():
    try:
        parser = argparse.ArgumentParser(description='Trigger a GroupAlarm.com alarm')
        parser.add_argument('code', type=str, help='The selcall alarm code (e.g. 09234)')
        parser.add_argument('time_point', type=str, help='The time point where the alarm has been received, '
                                                         'e.g. "05.12.2021 19:51:52"')
        parser.add_argument('type', type=str, help='The type of the alarm (e.g. "Einsatzalarmierung" or "Probealarm")')
        parser.add_argument('-t', '--test', action='store_true',
                            help='Only tests if this configuration would be valid - '
                                 'no alarm is actually emitted')
        parser.add_argument('-d', '--debug', action='store_true',
                            help='Print additional debug information')
        parser.add_argument('-c', '--config-file',
                            help='Path to the YAML configuration file, if not provided the default '
                                 'configuration file `config/config.yaml` is used')

        args = parser.parse_args()
        do_emit_alarm = not args.test

        if args.config_file:
            config_file_path = args.config_file
        else:
            config_file_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                            DEFAULT_CONFIG_FILE_PATH))

        return args.time_point, args.code, args.type, do_emit_alarm, config_file_path, args.debug
    except Exception as e:
        print(f'Fehler beim Verarbeiten der Aufrufparameter: {e}', file=sys.stderr)
        raise


def main():
    is_debug_mode = True  # only valid until overwritten by the command line arguments
    # noinspection PyBroadException
    try:
        alarm_time_point, alarm_code, alarm_type, do_emit_alarm, config_file_path, is_debug_mode = \
            get_command_line_arguments()

        if is_debug_mode:
            print('Aufrufparameter: ' + ','.join(sys.argv))

        config = read_config_file(config_file_path)
        send_alarm(config, alarm_time_point, alarm_code, alarm_type, do_emit_alarm)
    except Exception:
        if is_debug_mode:
            traceback.print_exc(file=sys.stderr)
        exit(-1)


if __name__ == '__main__':
    main()
