import argparse
import copy
import json
import logging
import multiprocessing
import os

import configuration
import library


def upgrade(zone_bundle_input, packages_root_directory):
    upgrade_zone(zone_bundle_input['zones'][0], packages_root_directory)

def upgrade_zone(zone, packages_root_directory):
    upgrade_icat(zone['icat_server'], packages_root_directory)
    upgrade_resource_servers(zone['resource_servers'], packages_root_directory)

def upgrade_icat(icat_server, packages_root_directory):
    host_list = [icat_server['deployment_information']['ip_address']]
    complex_args = {
        'irods_packages_root_directory': packages_root_directory,
        'icat_database_type': icat_server['database_config']['catalog_database_type'],
    }
    library.run_ansible(module_name='irods_upgrading_icat_server', complex_args=complex_args, host_list=host_list)

def upgrade_resource_servers(resource_servers, packages_root_directory):
    if len(resource_servers) > 0:
        host_list = [server['deployment_information']['ip_address'] for server in resource_servers]
        complex_args = {
            'irods_packages_root_directory': packages_root_directory,
        }
        library.run_ansible(module_name='irods_upgrading_resource_server', complex_args=complex_args, host_list=host_list)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Interact with zone-bundles.json')
    parser.add_argument('--zone_bundle_input', type=str, required=True)
    parser.add_argument('--packages_root_directory', type=str, required=True)
    args = parser.parse_args()

    with open(args.zone_bundle_input) as f:
        zone_bundle = json.load(f)

    library.register_log_handlers()
    library.convert_sigterm_to_exception()

    upgrade(zone_bundle, args.packages_root_directory)
