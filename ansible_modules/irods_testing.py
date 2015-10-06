#!/usr/bin/python

import json
import os
import pwd
import socket
import shutil
import subprocess


def run_tests(test_type, use_ssl, output_directory):
    create_irodsauthuser_account()

    test_type_dict = {
        'standalone_icat': '',
        'topology_icat': '--topology_test=icat',
        'topology_resource': '--topology_test=resource',
    }
    test_type_argument = test_type_dict[test_type]

    test_output_file = '/var/lib/irods/tests/test_output.txt'

    ssl_string = '--use_ssl' if use_ssl else '--run_devtesty'

    test_runner_directory = get_test_runner_directory()

    returncode = subprocess.call('sudo su - irods -c "cd {0}; python run_tests.py --run_python_suite --include_auth_tests --xml_output {1} {2} > {3} 2>&1"'.format(test_runner_directory, test_type_argument, ssl_string, test_output_file), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if output_directory:
        output_directory_os_specific = os.path.join(output_directory, socket.gethostname())
        os.makedirs(output_directory_os_specific)
        shutil.copy(test_output_file, output_directory_os_specific)

    return returncode

def create_irodsauthuser_account():
    name, password = get_authuser_name_and_password()
    try:
        pwd.getpwnam(name)
    except KeyError:
        subprocess.check_call("sudo useradd '{0}'".format(name), shell=True)

    p = subprocess.Popen('sudo chpasswd', stdin=subprocess.PIPE, shell=True)
    p.communicate(input='{0}:{1}'.format(name, password))
    if p.returncode != 0:
        raise RuntimeError('failed to change {0} password, return code: {1}'.format(name, p.returncode))

def get_authuser_name_and_password():
    config_locations = ['/var/lib/irods/tests/pydevtest/test_framework_configuration.json',
                        '/var/lib/irods/tests/test_framework_configuration.json',]
    for l in config_locations:
        if os.path.exists(l):
            config_file = l
            break
    else:
        raise RuntimeError('failed to find test_framework_configuration.json')

    try:
        with open(config_file) as f:
            d = json.load(f)
        return d['irods_authuser_name'], d['irods_authuser_password']
    except IOError as e:
        if e.errno == 2:
            return 'irodsauthuser', 'iamnotasecret'
        raise

def get_test_runner_directory():
    test_directories = ['/var/lib/irods/tests/pydevtest',
                      '/var/lib/irods/scripts',]
    for l in test_directories:
        if os.path.exists(os.path.join(l, 'run_tests.py')):
            return l

    raise RuntimeError('failed to find run_tests.py')

def main():
    module = AnsibleModule(
        argument_spec = dict(
            test_type=dict(choices=['standalone_icat', 'topology_icat', 'topology_resource'], type='str', required=True),
            output_directory=dict(type='str'),
            use_ssl=dict(type='bool', required=True),
        ),
        supports_check_mode=False,
    )

    test_returncode = run_tests(module.params['test_type'], module.params['use_ssl'], module.params['output_directory'])

    result = {}
    result['changed'] = True
    result['complex_args'] = module.params
    result['tests_passed'] = test_returncode == 0

    module.exit_json(**result)


from ansible.module_utils.basic import *
main()
