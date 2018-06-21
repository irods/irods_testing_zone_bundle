import argparse
import contextlib
import copy
import json
import multiprocessing
import os
import shutil
import sys
import tempfile

import configuration
import library


@contextlib.contextmanager
def directory_deleter(dirname):
    try:
        yield dirname
    finally:
        shutil.rmtree(dirname)

def test(zone_bundle, test_type, use_ssl, use_mungefs, output_directory):
    return test_zone_bundle(zone_bundle, test_type, use_ssl, use_mungefs, output_directory)

def test_zone_bundle(zone_bundle, test_type, use_ssl, use_mungefs, output_directory):
    library.makedirs_catch_preexisting(output_directory)
    if test_type == 'federation':
        return test_federation(zone_bundle, use_ssl, use_mungefs, output_directory)
    return test_zone(zone_bundle['zones'][0], test_type, use_ssl, use_mungefs, output_directory)

def test_federation(zone_bundle, use_ssl, use_mungefs, output_directory):
    zone0 = zone_bundle['zones'][0]
    zone1 = zone_bundle['zones'][1]

    data = test_federation_zone_to_zone(zone0, zone1, use_ssl, use_mungefs, output_directory)
    if not data['contacted'][zone0['icat_server']['deployment_information']['ip_address']]['tests_passed']:
        return False

    copy_testing_code(zone0, zone1)
    data = test_federation_zone_to_zone(zone1, zone0, use_ssl, use_mungefs, output_directory)
    return data['contacted'][zone1['icat_server']['deployment_information']['ip_address']]['tests_passed']

def test_federation_zone_to_zone(local_zone, remote_zone, use_ssl, use_mungefs, output_directory):
    complex_args = {
        'username': 'zonehopper#{0}'.format(local_zone['icat_server']['server_config']['zone_name'])
    }
    remote_icat_ip = remote_zone['icat_server']['deployment_information']['ip_address']
    library.run_ansible(module_name='irods_configuration_federation_testing', complex_args=complex_args, host_list=[remote_icat_ip], sudo=True)

    complex_args = {
        'test_type': 'federation',
        'output_directory': output_directory,
        'use_ssl': use_ssl,
        'use_mungefs': use_mungefs,
        'federation_args': [remote_zone['icat_server']['version']['irods_version'],
                            remote_zone['icat_server']['server_config']['zone_name'],
                            remote_zone['icat_server']['hostname'],]
    }
    local_icat_ip = local_zone['icat_server']['deployment_information']['ip_address']
    data = library.run_ansible(module_name='irods_testing', complex_args=complex_args, host_list=[local_icat_ip])
    return data

def copy_testing_code(source_zone, target_zone):
    ip_address_source = source_zone['icat_server']['deployment_information']['ip_address']
    ip_address_dest = target_zone['icat_server']['deployment_information']['ip_address']
    temp_dir = tempfile.mkdtemp()
    with directory_deleter(temp_dir):
        def get_complex_args_fetch(dirname, filename):
            return {
                'dest': temp_dir + '/',
                'flat': 'yes',
                'src': os.path.join(dirname, filename),
                'fail_on_missing': 'yes',
            }

        def get_complex_args_copy(filename):
            return {
                'dest': os.path.join('/var/lib/irods/tests/pydevtest', filename),
                'src': os.path.join(temp_dir, filename),
            }

        def get_complex_args_synchronize_pull():
            return {
                'recursive': 'yes',
                'src': '/var/lib/irods/scripts',
                'dest': temp_dir + '/',
                'mode': 'pull',
            }

        def get_complex_args_synchronize_push():
            return {
                'recursive': 'yes',
                'src': temp_dir + '/scripts',
                'dest': '/var/lib/irods/',
                'mode': 'push',
            }

        def get_complex_args_file():
            return {
                'mode': 0777,
                'path': '/var/lib/irods/scripts',
                'recurse': 'yes',
                'owner': 'irods',
                'group': 'irods',
            }

        data = library.run_ansible(module_name='stat', complex_args={'path':'/var/lib/irods/scripts/run_tests.py'}, host_list=[ip_address_source], sudo=True)
        if data['contacted'][ip_address_source]['stat']['exists']:
            library.run_ansible(module_name='synchronize', complex_args=get_complex_args_synchronize_pull(), host_list=[ip_address_source], sudo=True)
            library.run_ansible(module_name='synchronize', complex_args=get_complex_args_synchronize_push(), host_list=[ip_address_dest], sudo=True)
            library.run_ansible(module_name='file', complex_args=get_complex_args_file(), host_list=[ip_address_dest], sudo=True)
        else:
            library.run_ansible(module_name='file', complex_args={'mode':'u=rwx,g=rwx,o=rwx', 'path':'/var/lib/irods/tests/pydevtest', 'state':'directory'}, host_list=[ip_address_dest], sudo=True)
            for f in ['run_tests.py', 'configuration.py', 'test_federation.py', 'lib.py', 'test_framework_configuration.json']:
                library.run_ansible(module_name='fetch', complex_args=get_complex_args_fetch('/var/lib/irods/tests/pydevtest', f), host_list=[ip_address_source], sudo=True)
                library.run_ansible(module_name='copy', complex_args=get_complex_args_copy(f), host_list=[ip_address_dest], sudo=True)

def get_first_zone_irods_version(zone_bundle):
    icat_ip = zone_bundle['zones'][0]['icat_server']['deployment_information']['ip_address']
    data = library.run_ansible(module_name='irods_version', complex_args={}, host_list=[icat_ip])
    return data['contacted'][icat_ip]['irods_version']

def test_zone(zone, test_type, use_ssl, use_mungefs, output_directory):
    test_server_ip = get_test_server_ip(zone, test_type)

    complex_args = {
        'test_type': test_type,
        'output_directory': output_directory,
        'use_ssl': use_ssl,
        'use_mungefs': use_mungefs,
    }

    data = library.run_ansible(module_name='irods_testing', complex_args=complex_args, host_list=[test_server_ip])
    return data['contacted'][test_server_ip]['tests_passed']

def get_test_server_ip(zone, test_type):
    if test_type in {'standalone_icat', 'topology_icat'}:
        return zone['icat_server']['deployment_information']['ip_address']

    if test_type == 'topology_resource':
        return zone['resource_servers'][0]['deployment_information']['ip_address']

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Test deployed Zone')
    parser.add_argument('--zone_bundle_input', type=str, required=True)
    parser.add_argument('--test_type', type=str, required=True, choices=['standalone_icat', 'topology_icat', 'topology_resource', 'federation'])
    parser.add_argument('--output_directory', type=str, required=True)
    parser.add_argument('--use_ssl', action='store_true')
    parser.add_argument('--use_mungefs', action='store_true')

    args = parser.parse_args()

    with open(args.zone_bundle_input) as f:
        zone_bundle = json.load(f)

    library.register_log_handlers()
    library.convert_sigterm_to_exception()

    if not test_zone_bundle(zone_bundle, args.test_type, args.use_ssl, args.use_mungefs, args.output_directory):
        sys.exit(1)
