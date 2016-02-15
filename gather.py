import argparse
import json
import os

import configuration
import library


def gather(zone_bundle, output_root_directory):
    gather_zone_bundle(zone_bundle, output_root_directory)

def gather_zone_bundle(zone_bundle, output_root_directory):
    for zone in zone_bundle['zones']:
        gather_zone(zone, output_root_directory)

def gather_zone(zone, output_root_directory):
    servers = library.get_servers_from_zone(zone)
    host_list = [server['deployment_information']['ip_address'] for server in servers]

    complex_args = {
        'output_root_directory': output_root_directory,
    }

    library.run_ansible(module_name='irods_gathering', complex_args=complex_args, host_list=host_list)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Consolidate iRODS files from Zone')
    parser.add_argument('--zone_bundle_input', type=str, required=True)
    parser.add_argument('--output_root_directory', type=str, required=True)
    args = parser.parse_args()

    with open(args.zone_bundle_input) as f:
        zone_bundle = json.load(f)

    library.register_log_handlers()
    library.convert_sigterm_to_exception()

    gather(zone_bundle, args.output_root_directory)
