import contextlib
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
ansible.constants.PARAMIKO_RECORD_HOST_KEYS = False
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

class IrodsAnsibleException(Exception):
    pass

def get_servers_from_zone_bundle(zone_bundle):
    servers = []
    for zone in zone_bundle['zones']:
        servers.extend(get_servers_from_zone(zone))
    return servers

def get_servers_from_zone(zone):
    return [zone['icat_server']] + zone['resource_servers']

def deploy_vm_return_ip(vm_name, template_identifier):
    return provisioner_lib.deploy_vm_return_ip(vm_name, template_identifier)

def deploy_vms_return_names_and_ips(run_name, platform_targets):
    def generate_vm_name(run_name, os_name, os_version):
        return '{0} :: {1}_{2}'.format(run_name, os_name, os_version)

    vm_names = [generate_vm_name(run_name, os_name, os_version) for os_name, os_version in platform_targets]

    proc_pool = multiprocessing.Pool(len(platform_targets))
    proc_pool_results = [proc_pool.apply_async(deploy_vm_return_ip,
                                               (vm_name, (os_name, os_version)))
                      for (os_name, os_version), vm_name in zip(platform_targets, vm_names)]

    ip_addresses = [result.get() for result in proc_pool_results]
    return vm_names, ip_addresses

def destroy_vm(vm_name):
    provisioner_lib.destroy_vm(vm_name)

def destroy_build_vms(vm_names):
    proc_pool = multiprocessing.Pool(len(vm_names))
    proc_pool_results = [proc_pool.apply_async(destroy_vm, (vm_name,))
                         for vm_name in vm_names]
    for result in proc_pool_results:
        result.get()

@contextlib.contextmanager
def vm_manager(vm_names, leak_vms):
    try:
        yield
    finally:
        if not leak_vms:
            destroy_build_vms(vm_names)

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
        raise IrodsAnsibleException('ansible failed')
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

def make_argparse_true_or_false(option):
    def argparse_true_or_false(command_line_option):
        if command_line_option == 'true':
            return True
        elif command_line_option == 'false':
            return False
        raise RuntimeError('Flag {} must be followed by either "true" or "false"'.format(option))
    return argparse_true_or_false
