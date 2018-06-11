import argparse
import json
import os
import sys

import deploy
import destroy
import enable_ssl
import test
import gather
import upgrade
import library

def list_to_dict(l):
    return {l[i]: l[i+1] for i in range(0, len(l), 2)}

def main():
    library.register_log_handlers()
    library.convert_sigterm_to_exception()

    parser = argparse.ArgumentParser(description='Run topology upgrade tests on resource server')
    parser.add_argument('--deployment_name', type=str, required=True)
    parser.add_argument('--zone_bundle_input', type=str, required=True)
    parser.add_argument('--version_to_packages_map', type=str, nargs='+', required=True)
    parser.add_argument('--leak_vms', type=library.make_argparse_true_or_false('--leak_vms'), required=True)
    parser.add_argument('--use_ssl', action='store_true')
    parser.add_argument('--upgrade_packages_root_directory', type=str, required=True)
    parser.add_argument('--test_type', type=str, required=True, choices=['standalone_icat', 'topology_icat', 'topology_resource', 'federation'])
    parser.add_argument('--output_root_directory', type=str, required=True)
    args = parser.parse_args()


    version_to_packages_map = list_to_dict(args.version_to_packages_map)

    if not args.output_directory:
        args.zone_bundle_output

    with open(args.zone_bundle_input) as f:
        zone_bundle = json.load(f)

    zone_bundle_name = args.deployment_name + '.json'
    zone_bundle_output = os.path.join(args.output_directory, zone_bundle_name) 
    deployed_zone_bundle = deploy.deploy(zone_bundle, args.deployment_name, version_to_packages_map, 'None', zone_bundle_output)
    with destroy.deployed_zone_bundle_manager(deployed_zone_bundle, on_exception=not args.leak_vms, on_regular_exit=not args.leak_vms):
         upgrade.upgrade(deployed_zone_bundle, args.upgrade_packages_root_directory)

         if args.use_ssl:
             enable_ssl.enable_ssl(deployed_zone_bundle)
         
         tests_passed = test.test(deployed_zone_bundle, args.test_type, args.use_ssl, False, args.output_directory)
         gather.gather(deployed_zone_bundle, args.output_directory)

    if not tests_passed:
        sys.exit(1)


if __name__ == '__main__':
    main()
