import imp
import logging
import multiprocessing
import multiprocessing.pool
import os
import signal
import sys
import time
import yaml

import ansible.constants
ansible.constants.HOST_KEY_CHECKING = False
import ansible.inventory
import ansible.runner

import configuration

module_tuple = imp.find_module(configuration.provisioner_module_name, [configuration.provisioner_module_import_path])
imp.load_module('provisioner_lib', *module_tuple)
import provisioner_lib

# Allows recursive multiprocessing, from http://stackoverflow.com/a/8963618
class NoDaemonProcess(multiprocessing.Process):
    @property
    def daemon(self):
        return False
    @daemon.setter
    def daemon(self, value):
        pass

class RecursiveMultiprocessingPool(multiprocessing.pool.Pool):
    Process = NoDaemonProcess

def get_servers_from_zone_bundle(zone_bundle):
    servers = []
    for zone in zone_bundle['zones']:
        servers.extend(get_servers_from_zone(zone))
    return servers

def get_servers_from_zone(zone):
    return [zone['icat_server']] + zone['resource_servers']

def deploy_vm_return_ip(vm_name, template_identifier):
    return provisioner_lib.deploy_vm_return_ip(vm_name, template_identifier)

def destroy_vm(vm_name):
    provisioner_lib.destroy_vm(vm_name)

def get_ansible_modules_directory():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ansible_modules')

def format_ansible_output(ansible_dict):
    return yaml.safe_dump(ansible_dict, default_flow_style=False)

def makedirs_catch_preexisting(*args, **kwargs):
    try:
        os.makedirs(*args, **kwargs)
    except OSError as e:
        if e[0] != 17: # 17 == File exists
            raise

def ansible_run_failed(ansible_results):
    if len(ansible_results['dark']) > 0:
        return True

    for hostname, result in ansible_results['contacted'].items():
        if 'failed' in result:
            return True

def copy_file_to_zone(zone, file_src, file_dest, file_owner, file_group, file_mode):
    servers = get_servers_from_zone(zone)
    host_list = [server['deployment_information']['ip_address'] for server in servers]

    complex_args = {
        'src': file_src,
        'dest': file_dest,
        'owner': file_owner,
        'group': file_group,
        'mode': file_mode,
    }

    data = run_ansible(host_list=host_list, module_name='copy', complex_args=complex_args, sudo=True)
    return data

def run_ansible(host_list, additional_modules_directories=[], **kwargs):
    logger = logging.getLogger(__name__)
    inventory = ansible.inventory.Inventory(host_list)
    num_targets = len(host_list)
    module_path = os.pathsep.join([get_ansible_modules_directory()]+additional_modules_directories)
    r = ansible.runner.Runner(
        forks=num_targets,
        module_path=module_path,
        inventory=inventory,
        remote_user=configuration.remote_user,
        private_key_file=configuration.private_key_file,
        **kwargs
    )

    data = r.run()
    if ansible_run_failed(data):
        logger.error(format_ansible_output(data))
        raise RuntimeError('ansible failed')
    logger.info(format_ansible_output(data))
    return data

def register_log_handlers():
    logging.Formatter.converter = time.gmtime
    logger_root = logging.getLogger()
    logging_handler_stdout = logging.StreamHandler(sys.stdout)
    logging_handler_stdout.setFormatter(logging.Formatter('%(asctime)s - %(levelname)7s - %(pathname)s:%(lineno)4d\n%(message)s'))
    logger_root.addHandler(logging_handler_stdout)
    logger_root.setLevel(logging.INFO)

def convert_sigterm_to_exception():
    def sigterm_handler(_signo, _stack_frame):
        sys.exit(1)
    signal.signal(signal.SIGTERM, sigterm_handler)
