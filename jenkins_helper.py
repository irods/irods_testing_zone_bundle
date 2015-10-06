import argparse
import json
import os
import sys

import deploy
import destroy
import enable_ssl
import gather
import library
import test
import upgrade


if __name__ == '__main__':
    library.register_log_handlers()
    library.convert_sigterm_to_exception()

    parser = argparse.ArgumentParser(description='Run iRODS tests from Jenkins')
    parser.add_argument('--zone_bundle_input', type=str, required=True)
    parser.add_argument('--deployment_name', type=str, required=True)
    parser.add_argument('--packages_root_directory', type=str, required=True)
    parser.add_argument('--test_type', type=str, required=True, choices=['standalone_icat', 'topology_icat', 'topology_resource'])
    parser.add_argument('--use_ssl', action='store_true')
    parser.add_argument('--upgrade_test', nargs='+')
    parser.add_argument('--output_directory', type=str, required=True)
    args = parser.parse_args()

    with open(args.zone_bundle_input) as f:
        zone_bundle = json.load(f)

    zone_bundle_output = os.path.join(args.output_directory, 'deployed_zone_bundle.json')

    if args.upgrade_test:
        package_directories = args.upgrade_test
        deployed_zone_bundle = deploy.deploy(zone_bundle, args.deployment_name, package_directories[0], zone_bundle_output)
        for pd in package_directories[1:]:
            upgrade.upgrade(deployed_zone_bundle, pd)
        upgrade.upgrade(deployed_zone_bundle, args.packages_root_directory)
    else:
        deployed_zone_bundle = deploy.deploy(zone_bundle, args.deployment_name, args.packages_root_directory, zone_bundle_output)

    with destroy.deployed_zone_bundle_manager(deployed_zone_bundle):
        if args.use_ssl:
            enable_ssl.enable_ssl(deployed_zone_bundle)
        tests_passed = test.test(deployed_zone_bundle, args.test_type, args.use_ssl, args.output_directory)
        gather.gather(deployed_zone_bundle, args.output_directory)

    if not tests_passed:
        sys.exit(1)
