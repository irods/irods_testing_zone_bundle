import argparse
import contextlib
import copy
import json
import multiprocessing
import os

import configuration
import library


@contextlib.contextmanager
def vm_manager(vm_names):
    try:
        yield
    finally:
        destroy_build_vms(vm_names)

def build(build_name, output_root_directory, git_repository, git_commitish, debug_build):
    os.makedirs(output_root_directory)
    vm_names, ip_addresses = deploy_build_vms_return_names_and_ips(build_name, output_root_directory)
    with vm_manager(vm_names):
        build_irods_on_vms(ip_addresses, output_root_directory, git_repository, git_commitish, debug_build)

def deploy_build_vms_return_names_and_ips(build_name, output_root_directory):
    def generate_vm_name(build_name, os_name, os_version):
        return '{0} :: {1}_{2}'.format(build_name, os_name, os_version)

    platform_targets = [('CentOS', '6'), ('CentOS', '7'), ('Ubuntu', '12'), ('Ubuntu', '14'), ('openSUSE ', '13')]
    vm_names = [generate_vm_name(build_name, os_name, os_version) for os_name, os_version in platform_targets]

    proc_pool = multiprocessing.Pool(len(platform_targets))
    proc_pool_results = [proc_pool.apply_async(library.deploy_vm_return_ip,
                                               (vm_name, (os_name, os_version)))
                      for (os_name, os_version), vm_name in zip(platform_targets, vm_names)]

    ip_addresses = [result.get() for result in proc_pool_results]
    return vm_names, ip_addresses

def build_irods_on_vms(ip_addresses, output_root_directory, git_repository, git_commitish, debug_build):
    complex_args = {
        'output_root_directory': output_root_directory,
        'git_repository': git_repository,
        'git_commitish': git_commitish,
        'debug_build': debug_build,
    }

    library.run_ansible(module_name='irods_building', complex_args=complex_args, host_list=ip_addresses)

def destroy_build_vms(vm_names):
    proc_pool = multiprocessing.Pool(len(vm_names))
    proc_pool_results = [proc_pool.apply_async(library.destroy_vm, (vm_name,))
                         for vm_name in vm_names]
    for result in proc_pool_results:
        result.get()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build iRODS packages')
    parser.add_argument('--build_name', type=str, required=True)
    parser.add_argument('--output_root_directory', type=str, required=True)
    parser.add_argument('--git_repository', type=str, required=True)
    parser.add_argument('--git_commitish', type=str, required=True)
    parser.add_argument('--debug_build', dest='debug_build', action='store_true', default=False)
    args = parser.parse_args()

    library.register_log_handlers()
    library.convert_sigterm_to_exception()

    build(args.build_name, args.output_root_directory, args.git_repository, args.git_commitish, args.debug_build)
