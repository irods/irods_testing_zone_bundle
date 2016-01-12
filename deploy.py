import argparse
import copy
import json
import logging
import os

import configuration
import destroy
import library


def deploy(zone_bundle_input, deployment_name, version_to_packages_map, zone_bundle_output_file=None, destroy_vm_on_failure=True):
    zone_bundle_deployed = deploy_zone_bundle(zone_bundle_input, deployment_name)
    with destroy.deployed_zone_bundle_manager(zone_bundle_deployed, on_regular_exit=False, on_exception=destroy_vm_on_failure):
        if zone_bundle_output_file:
            save_zone_bundle_deployed(zone_bundle_output_file, zone_bundle_deployed)
        configure_zone_bundle_networking(zone_bundle_deployed)
        install_irods_on_zone_bundle(zone_bundle_deployed, version_to_packages_map)
        configure_federation_on_zone_bundle(zone_bundle_deployed)
    return zone_bundle_deployed

def deploy_zone_bundle(zone_bundle_input, deployment_name):
    zone_bundle = copy.deepcopy(zone_bundle_input)
    proc_pool = library.RecursiveMultiprocessingPool(len(zone_bundle['zones']))
    proc_pool_results = [proc_pool.apply_async(deploy_zone_set_server_ip,
                                               (zone, deployment_name))
                         for zone in zone_bundle['zones']]
    zone_bundle['zones'] = [result.get() for result in proc_pool_results]
    return zone_bundle

def deploy_zone_set_server_ip(zone_input, deployment_name):
    logger = logging.getLogger(__name__)
    zone = copy.deepcopy(zone_input)
    def generate_vm_name(server, deployment_name):
        zone_name = server['server_config']['zone_name']
        hostname = server['hostname']
        return '{0} :: {1} :: {2}'.format(deployment_name, zone_name, hostname)

    for server in library.get_servers_from_zone(zone):
        if 'deployment_information' not in server:
            server['deployment_information'] = {}
        server['deployment_information']['vm_name'] = generate_vm_name(server, deployment_name)

    servers = library.get_servers_from_zone(zone)
    proc_pool = library.RecursiveMultiprocessingPool(len(servers))
    proc_pool_results = [proc_pool.apply_async(library.deploy_vm_return_ip,
                                               (server['deployment_information']['vm_name'],
                                                (server['host_system_information']['os_distribution_name'],
                                                 server['host_system_information']['os_distribution_version'].split('.')[0])))
                         for server in servers]

    for server, result in zip(servers, proc_pool_results):
        ip_address = result.get()
        server['deployment_information']['ip_address'] = ip_address
        logger.info(server['hostname'] + ' :: ' + ip_address)

    database_config = zone['icat_server']['database_config']
    if database_config['catalog_database_type'] == 'oracle':
        zone_name = zone['icat_server']['server_config']['zone_name']
        db_vm_name = '{0} :: {1} :: Oracle DB'.format(deployment_name, zone_name)
        db_ip_address = library.deploy_vm_return_ip(db_vm_name, 'Oracle')
        if 'deployment_information' not in database_config:
            database_config['deployment_information'] = {}
        database_config['deployment_information']['vm_name'] = db_vm_name
        database_config['deployment_information']['ip_address'] = db_ip_address
    return zone

def save_zone_bundle_deployed(zone_bundle_output_file, zone_bundle_deployed):
    library.makedirs_catch_preexisting(os.path.dirname(os.path.abspath(zone_bundle_output_file)))
    with open(zone_bundle_output_file, 'w') as f:
        json.dump(zone_bundle_deployed, f, indent=4)

def configure_zone_bundle_networking(zone_bundle):
    servers = library.get_servers_from_zone_bundle(zone_bundle)
    for zone in zone_bundle['zones']:
        configure_zone_networking(zone, servers)

def configure_zone_networking(zone, servers):
    configure_zone_hosts_files(zone, servers)
    configure_zone_hostnames(zone)

def configure_zone_hosts_files(zone, servers):
    ip_address_to_hostnames_dict = {server['deployment_information']['ip_address']: [server['hostname']] for server in servers}
    ip_address_to_hostnames_dict['127.0.0.1'] = ['localhost']

    complex_args = {
        'ip_address_to_hostnames_dict': ip_address_to_hostnames_dict,
        'hosts_file': '/etc/hosts',
    }

    host_list = [server['deployment_information']['ip_address'] for server in servers]

    library.run_ansible(module_name='hosts_file', complex_args=complex_args, host_list=host_list, sudo=True)

    database_config = zone['icat_server']['database_config']
    if database_config['db_host'] != 'localhost':
        db_hostname = database_config['db_host']
        db_ip_address = database_config['deployment_information']['ip_address']
        complex_args = {
            'ip_address_to_hostnames_dict': {db_ip_address: [db_hostname]},
            'hosts_file': '/etc/hosts',
        }
        icat_ip_address = zone['icat_server']['deployment_information']['ip_address']
        library.run_ansible(module_name='hosts_file', complex_args=complex_args, host_list=[icat_ip_address], sudo=True)

def configure_zone_hostnames(zone):
    servers = library.get_servers_from_zone(zone)
    for server in servers:
        server_ip = server['deployment_information']['ip_address']
        library.run_ansible(module_name='hostname', module_args='name={0}'.format(server['hostname']), host_list=[server_ip], sudo=True)

def install_irods_on_zone_bundle(zone_bundle, version_to_packages_map):
    proc_pool = library.RecursiveMultiprocessingPool(len(zone_bundle['zones']))
    proc_pool_results = [proc_pool.apply_async(install_irods_on_zone,
                                               (zone, version_to_packages_map))
                         for zone in zone_bundle['zones']]
    [result.get() for result in proc_pool_results]

def install_irods_on_zone(zone, version_to_packages_map):
    install_irods_on_zone_icat_server(zone['icat_server'], version_to_packages_map)
    install_irods_on_zone_resource_servers(zone['resource_servers'], version_to_packages_map)

def install_irods_on_zone_icat_server(icat_server, version_to_packages_map):
    host_list = [icat_server['deployment_information']['ip_address']]
    complex_args = {
        'icat_server': icat_server,
        'irods_packages_root_directory': version_to_packages_map[icat_server['version']['irods_version']],
    }
    library.run_ansible(module_name='irods_installation_icat_server', complex_args=complex_args, host_list=host_list, sudo=True)

def install_irods_on_zone_resource_servers(resource_servers, version_to_packages_map):
    if len(resource_servers) > 0:
        host_list = [server['deployment_information']['ip_address'] for server in resource_servers]
        complex_args = {
            'icat_server_hostname': resource_servers[0]['server_config']['icat_host'],
            'irods_packages_root_directory': version_to_packages_map[resource_servers[0]['version']['irods_version']],
        }
        library.run_ansible(module_name='irods_installation_resource_server', complex_args=complex_args, host_list=host_list)

def configure_federation_on_zone_bundle(zone_bundle):
    for zone in zone_bundle['zones']:
        configure_federation_on_zone(zone)

def configure_federation_on_zone(zone):
    host_list = [zone['icat_server']['deployment_information']['ip_address']]
    complex_args = {
        'federation': zone['icat_server']['server_config']['federation']
    }
    library.run_ansible(module_name='irods_configuration_federation', complex_args=complex_args, host_list=host_list, sudo=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Interact with zone-bundles.json')
    parser.add_argument('--zone_bundle_input', type=str, required=True)
    parser.add_argument('--deployment_name', type=str, required=True)
    parser.add_argument('--version_to_packages_map', type=str, required=True, nargs='+')
    parser.add_argument('--zone_bundle_output', type=str)
    parser.add_argument('--leave-vm-on-failure', action='store_true')
    args = parser.parse_args()

    version_to_packages_map = {}
    for i in range(0, len(args.version_to_packages_map), 2):
        version_to_packages_map[args.version_to_packages_map[i]] = args.version_to_packages_map[i+1]

    if not args.zone_bundle_output:
        args.zone_bundle_output = os.path.abspath(args.deployment_name + '.json')

    with open(args.zone_bundle_input) as f:
        zone_bundle = json.load(f)

    library.register_log_handlers()
    library.convert_sigterm_to_exception()

    deploy(zone_bundle, args.deployment_name, version_to_packages_map, args.zone_bundle_output, not args.leave_vm_on_failure)
