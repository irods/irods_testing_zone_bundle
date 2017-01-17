import argparse
import contextlib
import copy
import json
import multiprocessing

import library


def destroy_build_vms(vm_names):
    proc_pool = multiprocessing.Pool(len(vm_names))
    proc_pool_results = [proc_pool.apply_async(library.destroy_vm, (vm_name,))
                         for vm_name in vm_names]
    for result in proc_pool_results:
        result.get()

@contextlib.contextmanager
def vm_manager(vm_names):
    try:
        yield
    finally:
        destroy_build_vms(vm_names)

def run_build_hook_on_vms(build_name, git_repository, git_commitish, platform_targets, passthrough_arguments):
    vm_names, ip_addresses = deploy_build_vms_return_names_and_ips(build_name, platform_targets)
    with vm_manager(vm_names):
        build_plugin_on_vms(ip_addresses, git_repository, git_commitish, passthrough_arguments)

def deploy_build_vms_return_names_and_ips(build_name, platform_targets):
    def generate_vm_name(build_name, os_name, os_version):
        return '{0} :: {1}_{2}'.format(build_name, os_name, os_version)

    platform_targets = eval(platform_targets) # e.g.  platform_targets = [('CentOS', '6'), ('Ubuntu', '12'), ('Ubuntu', '14'), ('openSUSE ', '13')]
    vm_names = [generate_vm_name(build_name, os_name, os_version) for os_name, os_version in platform_targets]

    proc_pool = multiprocessing.Pool(len(platform_targets))
    proc_pool_results = [proc_pool.apply_async(library.deploy_vm_return_ip,
                                               (vm_name, (os_name, os_version)))
                         for (os_name, os_version), vm_name in zip(platform_targets, vm_names)]

    ip_addresses = [result.get() for result in proc_pool_results]
    return vm_names, ip_addresses

def build_plugin_on_vms(ip_addresses, git_repository, git_commitish, passthrough_arguments):
    complex_args = {
        'git_repository': git_repository,
        'git_commitish': git_commitish,
        'passthrough_arguments': passthrough_arguments,
    }

    library.run_ansible(module_name='irods_run_build_hook', complex_args=complex_args, host_list=ip_addresses)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build plugin packages')
    parser.add_argument('--build_name', type=str, required=True)
    parser.add_argument('--git_repository', type=str, required=True)
    parser.add_argument('--git_commitish', type=str, required=True)
    parser.add_argument('--platform_targets', type=str, required=True)
    parser.add_argument('--passthrough_arguments', default=[], nargs=argparse.REMAINDER)
    args = parser.parse_args()

    library.register_log_handlers()
    library.convert_sigterm_to_exception()

    run_build_hook_on_vms(args.build_name, args.git_repository, args.git_commitish, args.platform_targets, args.passthrough_arguments)
