import argparse
import copy
import json
import logging
import multiprocessing
import os

import configuration
import destroy
import library


def deploy(zone_bundle_input, deployment_name, packages_root_directory, zone_bundle_output_file=None):
    zone_bundle_deployed = deploy_zone_bundle(zone_bundle_input, deployment_name)
    with destroy.deployed_zone_bundle_manager(zone_bundle_deployed, only_on_exception=True):
        if zone_bundle_output_file:
            save_zone_bundle_deployed(zone_bundle_output_file, zone_bundle_deployed)

        configure_zone_bundle_networking(zone_bundle_deployed)
        install_irods_on_zone_bundle(zone_bundle_deployed, packages_root_directory)

    return zone_bundle_deployed

def deploy_zone_bundle(zone_bundle_input, deployment_name):
    zone_bundle = copy.deepcopy(zone_bundle_input)
    deploy_zone_set_server_ip(zone_bundle['zones'][0], deployment_name)
    return zone_bundle

def deploy_zone_set_server_ip(zone, deployment_name):
    logger = logging.getLogger(__name__)
    def generate_vm_name(server, deployment_name):
        zone_name = server['server_config']['zone_name']
        hostname = server['hostname']
        return '{0} :: {1} :: {2}'.format(deployment_name, zone_name, hostname)

    for server in library.get_servers_from_zone(zone):
        if 'deployment_information' not in server:
            server['deployment_information'] = {}
        server['deployment_information']['vm_name'] = generate_vm_name(server, deployment_name)

    servers = library.get_servers_from_zone(zone)
    proc_pool = multiprocessing.Pool(len(servers))
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

def save_zone_bundle_deployed(zone_bundle_output_file, zone_bundle_deployed):
    library.makedirs_catch_preexisting(os.path.dirname(os.path.abspath(zone_bundle_output_file)))
    with open(zone_bundle_output_file, 'w') as f:
        json.dump(zone_bundle_deployed, f, indent=4)

def configure_zone_bundle_networking(zone_bundle):
    configure_zone_networking(zone_bundle['zones'][0])

def configure_zone_networking(zone):
    configure_zone_hosts_files(zone)
    configure_zone_hostnames(zone)

def configure_zone_hosts_files(zone):
    servers = library.get_servers_from_zone(zone)

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
        host_list = [server['deployment_information']['ip_address']]
        library.run_ansible(module_name='hostname', module_args='name={0}'.format(server['hostname']), host_list=host_list, sudo=True)

def install_irods_on_zone_bundle(zone_bundle, packages_root_directory):
    install_irods_on_zone(zone_bundle['zones'][0], packages_root_directory)

def install_irods_on_zone(zone, packages_root_directory):
    install_irods_on_zone_icat_server(zone['icat_server'], packages_root_directory)
    install_irods_on_zone_resource_servers(zone['resource_servers'], packages_root_directory)

def install_irods_on_zone_icat_server(icat_server, packages_root_directory):
    host_list = [icat_server['deployment_information']['ip_address']]
    complex_args = {
        'icat_database_type': icat_server['database_config']['catalog_database_type'],
        'icat_database_hostname': icat_server['database_config']['db_host'],
        'irods_packages_root_directory': packages_root_directory,
    }
    library.run_ansible(module_name='irods_installation_icat_server', complex_args=complex_args, host_list=host_list)

def install_irods_on_zone_resource_servers(resource_servers, packages_root_directory):
    if len(resource_servers) > 0:
        host_list = [server['deployment_information']['ip_address'] for server in resource_servers]
        complex_args = {
            'icat_server_hostname': resource_servers[0]['server_config']['icat_host'],
            'irods_packages_root_directory': packages_root_directory,
        }
        library.run_ansible(module_name='irods_installation_resource_server', complex_args=complex_args, host_list=host_list)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Interact with zone-bundles.json')
    parser.add_argument('--zone_bundle_input', type=str, required=True)
    parser.add_argument('--deployment_name', type=str, required=True)
    parser.add_argument('--packages_root_directory', type=str, required=True)
    parser.add_argument('--zone_bundle_output', type=str)
    args = parser.parse_args()

    if not args.zone_bundle_output:
        args.zone_bundle_output = os.path.abspath(args.deployment_name + '.json')

    with open(args.zone_bundle_input) as f:
        zone_bundle = json.load(f)

    library.register_log_handlers()
    library.convert_sigterm_to_exception()

    deploy(zone_bundle, args.deployment_name, args.packages_root_directory, args.zone_bundle_output)
