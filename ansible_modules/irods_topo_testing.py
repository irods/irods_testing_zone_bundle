#!/usr/bin/python

import json
import os
import pwd
import socket
import shutil
import subprocess


def run_tests(test_type, output_directory, test_args):
    test_runner_directory = get_test_runner_directory()
    
    if get_irods_version() < (4, 2):
        test_output_file = '/var/lib/irods/tests/test_output.txt'
    else:
        test_output_file = '/var/lib/irods/test/test_output.txt'
    returncode = subprocess.call('sudo su - irods -c "cd {0}; python run_tests.py --xml_output {1} > {2} 2>&1"'.format(test_runner_directory, test_args, test_output_file), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
    config_locations = ['/var/lib/irods/test/test_framework_configuration.json',
                        '/var/lib/irods/tests/pydevtest/test_framework_configuration.json',]
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
    test_directories = ['/var/lib/irods/scripts',
                        '/var/lib/irods/tests/pydevtest',]
    for l in test_directories:
        if os.path.exists(os.path.join(l, 'run_tests.py')):
            return l

    raise RuntimeError('failed to find run_tests.py')

def main():
    module = AnsibleModule(
        argument_spec = dict(
            test_type=dict(choices=['standalone_icat', 'topology_icat', 'topology_resource', 'federation'], type='str', required=True),
            test_args=dict(type='str'),
            output_directory=dict(type='str'),
        ),
        supports_check_mode=False,
    )

    test_returncode = run_tests(module.params['test_type'], module.params['output_directory'], module.params['test_args'])

    result = {}
    result['changed'] = True
    result['complex_args'] = module.params
    result['tests_passed'] = test_returncode == 0

    module.exit_json(**result)


from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *
main()
