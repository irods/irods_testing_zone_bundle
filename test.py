import argparse
import json
import multiprocessing
import os
import sys

import configuration
import library


def test(zone_bundle, test_type, use_ssl, output_directory):
    return test_zone_bundle(zone_bundle, test_type, use_ssl, output_directory)

def test_zone_bundle(zone_bundle, test_type, use_ssl, output_directory):
    library.makedirs_catch_preexisting(output_directory)
    return test_zone(zone_bundle['zones'][0], test_type, use_ssl, output_directory)

def test_zone(zone, test_type, use_ssl, output_directory):
    test_server_ip = get_test_server_ip(zone, test_type)

    complex_args = {
        'test_type': test_type,
        'output_directory': output_directory,
        'use_ssl': use_ssl,
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
    parser.add_argument('--test_type', type=str, required=True, choices=['standalone_icat', 'topology_icat', 'topology_resource'])
    parser.add_argument('--output_directory', type=str, required=True)
    parser.add_argument('--use_ssl', action='store_true')

    args = parser.parse_args()

    with open(args.zone_bundle_input) as f:
        zone_bundle = json.load(f)

    library.register_log_handlers()
    library.convert_sigterm_to_exception()

    if not test_zone_bundle(zone_bundle, args.test_type, args.use_ssl, args.output_directory):
        sys.exit(1)
