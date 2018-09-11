import argparse
import json
import os
import sys
import logging
import deploy
import destroy
import library

def list_to_dict(l):
    return {l[i]: l[i+1] for i in range(0, len(l), 2)}

def install_plugin_and_run_tests(zone_bundle, plugin_packages_directory, test_type, output_directory):
    zone = zone_bundle['zones'][0]
    install_plugin(zone, plugin_packages_directory)
    run_tests(zone, test_type, output_directory)

def install_plugin(zone, plugin_packages_directory):
    install_plugin_on_icat_server(zone['icat_server'], plugin_packages_directory)
    install_plugin_on_resource_servers(zone['resource_servers'], plugin_packages_directory)

def run_tests(zone, test_type, output_directory):
    if test_type == 'topology_resource':
        ip_address = zone['resource_servers'][0]['deployment_information']['ip_address']
        complex_args = {
            'test_type': test_type,
            'test_args': '--run_specific_test test_native_rule_engine_plugin.Test_Native_Rule_Engine_Plugin.test_remote_rule_execution --topology_test resource',
            'output_directory': output_directory,
        }
        library.run_ansible(module_name='irods_topo_testing', complex_args=complex_args, host_list=[ip_address])

def install_plugin_on_icat_server(icat_server, plugin_packages_directory):
    server_ip = icat_server['deployment_information']['ip_address']
    install_plugin_on_server(server_ip, plugin_packages_directory)

def install_plugin_on_resource_servers(resource_servers, plugin_packages_directory):
    if len(resource_servers) > 0:
        for server in resource_servers:
           server_ip = server['deployment_information']['ip_address']
           install_plugin_on_server(server_ip, plugin_packages_directory)

def install_plugin_on_server(server_ip, plugin_packages_directory):
     logger = logging.getLogger(__name__)
     logger.info('jaspreet ' + server_ip)
     complex_args = {
        'irods_plugin_packages_directory': plugin_packages_directory,
     }
     library.run_ansible(module_name='irods_install_plugin', complex_args=complex_args, host_list=[server_ip])

def main():
    library.register_log_handlers()
    library.convert_sigterm_to_exception()

    parser = argparse.ArgumentParser(description='Run tests on resource server')
    parser.add_argument('--deployment_name', type=str, required=True)
    parser.add_argument('--zone_bundle_input', type=str, required=True)
    parser.add_argument('--version_to_packages_map', type=str, nargs='+', required=True)
    parser.add_argument('--install_dev_package', type=library.make_argparse_true_or_false('--install_dev_package'), required=True)
    parser.add_argument('--leak_vms', type=library.make_argparse_true_or_false('--leak_vms'), required=True)
    parser.add_argument('--test_type', type=str, required=True, choices=['standalone_icat', 'topology_icat', 'topology_resource', 'federation'])
    parser.add_argument('--irods_plugin_packages_directory', type=str, required=True)
    parser.add_argument('--mungefs_packages_dir', type=str)
    parser.add_argument('--output_directory', type=str, required=True)

    args = parser.parse_args()

    version_to_packages_map = list_to_dict(args.version_to_packages_map)

    with open(args.zone_bundle_input) as f:
        zone_bundle = json.load(f)

    deployed_zone_bundle = deploy.deploy(zone_bundle, args.deployment_name, version_to_packages_map, args.mungefs_packages_dir, install_dev_package=args.install_dev_package)

    with destroy.deployed_zone_bundle_manager(deployed_zone_bundle, on_exception=not args.leak_vms, on_regular_exit=not args.leak_vms):
         install_plugin_and_run_tests(deployed_zone_bundle, args.irods_plugin_packages_directory, args.test_type, args.output_directory)
         

if __name__ == '__main__':
    main()
